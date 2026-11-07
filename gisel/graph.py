"""Build a finite quotient graph for a schema-0.4 legalizer document.

The graph is deliberately built on the same normal form and evaluator as the
other gisel commands.  It is a static diagnostic: no MIR, TableGen or LLVM
runtime is involved.
"""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from . import cases as C
from . import domain as D
from . import dsl
from . import eval as E


TERMINAL = {"Legal", "Lower", "Libcall", "Custom", "Unsupported"}
_SENTINEL_TEXT = ("s3", "s7", "s24", "s33", "s63", "s65",
                  "v3s8", "v5s8", "v3s32", "v5s32")
_SENTINEL_RANK = {text: i for i, text in enumerate(_SENTINEL_TEXT)}


class GraphError(ValueError):
    pass


def _json_key(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      default=str)


def _type_text(t):
    return C.llt_text(t)


def _representative_key(t):
    return (_SENTINEL_RANK.get(_type_text(t), len(_SENTINEL_RANK)),
            _type_text(t))


def _node_text(node):
    opcode, classes, mem = node
    suffix = ",m%s" % mem if mem is not None else ""
    return "%s[%s%s]" % (opcode, ",".join(map(str, classes)), suffix)


def _walk_atoms(node, out):
    if not isinstance(node, dict):
        return
    kind = node.get("kind")
    if kind in ("all", "any", "not", "nary"):
        for value in node.get("args", []):
            _walk_atoms(value, out)
        if "arg" in node:
            _walk_atoms(node["arg"], out)
        return
    out.append(node)


def _atoms(ruleset):
    out, seen = [], set()
    for rule in ruleset["rules"]:
        found = []
        _walk_atoms(rule.get("predicate"), found)
        for atom in found:
            key = _json_key(atom)
            if key not in seen:
                seen.add(key)
                out.append(atom)
    return out


def _dependencies(node):
    slots, mem = set(), False

    def walk(value):
        nonlocal mem
        if isinstance(value, dict):
            if value.get("kind") == "slot":
                slots.add(value["index"])
            elif value.get("kind") == "memSlot":
                mem = True
            for child in value.values():
                walk(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child)

    walk(node)
    return slots, mem


def _collapse(t, extended):
    return t if extended else E.collapse_extended(t)


def _parse_type(text, extended):
    try:
        return _collapse(E.parse_case_llt(text), extended)
    except E.EvalError as exc:
        raise GraphError(str(exc)) from exc


def _mem_desc(mem, extended):
    if mem is None:
        return []
    text, align = mem
    return [E.MemDesc(_parse_type(text, extended), int(align))]


def _opcode_shape(opcode, slots, manifest):
    info = slots.get(opcode, {})
    arity = info.get("arity")
    if arity is None:
        arity = manifest.get(opcode)
    if arity is None:
        return None, set()
    return arity, set(info.get("ptype", ()))


def _declared_types(source, pointer_width, extended):
    types, _, _ = D.domain_axes(source, pointer_width)
    return {_parse_type(text, extended) for text in types}


def _memory_values(infos, domain_mems, pointer_width, extended, extra_mems=()):
    rows = list(C._mem_candidates(infos))
    if not rows:
        rows = [(mty, "", mty, align) for mty, _bits, align in domain_mems]
    out, seen = [], set()
    for _t0, _t1, mty, align in rows:
        mty = D._resolve(str(mty), pointer_width)
        value = (mty, int(align))
        parsed = (_parse_type(mty, extended), value[1])
        if parsed not in seen:
            seen.add(parsed)
            out.append(value)
    for mty, align in extra_mems:
        mty = D._resolve(str(mty), pointer_width)
        value = (mty, int(align))
        parsed = (_parse_type(mty, extended), value[1])
        if parsed not in seen:
            seen.add(parsed)
            out.append(value)
    return sorted(out, key=lambda x: (x[0], x[1]))


def _candidate_axes(infos, arity, ptypes, domain_types, extra_types, extended,
                    include_non_pointer=False):
    # Start with every declared value and add the deterministic cut points
    # that cases.py derives from the rules.  These are the finite observation
    # domain, and are also what lets the graph address the existing oracle's
    # boundary queries.  A mutation outside this set is reported as outside.
    base = C._candidates(infos, arity, 64, list(domain_types))
    axes = []
    for index in range(arity):
        values = list(domain_types) + list(base[index]) + list(extra_types)
        if index in ptypes and not include_non_pointer:
            values = [t for t in values if t[0] == "pointer"]
        unique = {}
        for value in values:
            unique[_type_text(value)] = value
        axes.append([unique[k] for k in sorted(unique)])
        if not axes[-1]:
            raise GraphError("opcode slot %d has no finite type candidates" % index)
    return axes


def _atom_value(evaluator, atom, types, mem, config):
    try:
        value = evaluator.bool_value(atom, types, _mem_desc(mem, evaluator.extended(config)),
                                     config, ())
        if value is None:
            return None
        return bool(value)
    except (E.EvalError, IndexError, KeyError, TypeError, ValueError,
            AssertionError):
        return None


@dataclass
class AxisClasses:
    values: list
    class_of: dict
    members: dict
    signatures: dict


def _make_classes(values, axis, atoms, axes, mem_values, evaluator, config):
    baseline = [items[0] for items in axes]
    base_mem = mem_values[0] if mem_values else None
    signatures = {}
    for value in values:
        types = list(baseline)
        types[axis] = value
        signature = []
        for atom in atoms:
            slots, has_mem = _dependencies(atom)
            if (slots - {axis}) or has_mem:
                # A relation involving another slot cannot be represented by
                # a unary class without losing information.  Preserve the
                # concrete value; closure checking still audits the result.
                signature.append(["raw", _type_text(value)])
            else:
                signature.append(_atom_value(evaluator, atom, tuple(types),
                                              base_mem, config))
        signatures[value] = tuple(signature)

    groups = collections.defaultdict(list)
    for value, signature in signatures.items():
        groups[_json_key(signature)].append(value)
    class_of, members, ordered = {}, {}, []
    for cid, key in enumerate(sorted(groups)):
        group = sorted(groups[key], key=_representative_key)
        members[cid] = group
        ordered.append((cid, group, json.loads(key)))
        for value in group:
            class_of[value] = cid
    return AxisClasses(list(values), class_of, members,
                       {cid: sig for cid, _group, sig in ordered})


def _make_mem_classes(mem_values, atoms, axes, evaluator, config):
    baseline = [items[0] for items in axes]
    signatures = {}
    for value in mem_values:
        signature = []
        for atom in atoms:
            slots, has_mem = _dependencies(atom)
            if slots or not has_mem:
                signature.append(["raw", value])
            else:
                signature.append(_atom_value(evaluator, atom, tuple(baseline),
                                              value, config))
        signatures[value] = tuple(signature)
    groups = collections.defaultdict(list)
    for value, signature in signatures.items():
        groups[_json_key(signature)].append(value)
    class_of, members, ordered = {}, {}, []
    for cid, key in enumerate(sorted(groups)):
        group = sorted(groups[key], key=lambda x: (x[0], x[1]))
        members[cid] = group
        ordered.append((cid, group, json.loads(key)))
        for value in group:
            class_of[value] = cid
    return AxisClasses(list(mem_values), class_of, members,
                       {cid: sig for cid, _group, sig in ordered})


def _opaque(evaluator, atoms, types, mem, config):
    return any(_atom_value(evaluator, atom, types, mem, config) is None
               for atom in atoms)


def _find_cycles(edges):
    color, stack, position = {}, [], {}
    count, samples = 0, []

    def dfs(node):
        nonlocal count
        color[node] = 1
        position[node] = len(stack)
        stack.append(node)
        for target, _label in edges.get(node, []):
            if target not in edges:
                continue
            state = color.get(target, 0)
            if state == 1:
                count += 1
                if len(samples) < 5:
                    samples.append(stack[position[target]:] + [target])
            elif state == 0:
                dfs(target)
        stack.pop()
        position.pop(node, None)
        color[node] = 2

    for node in sorted(edges, key=_node_text):
        if color.get(node, 0) == 0:
            dfs(node)
    return count, samples


@dataclass
class Report:
    config: str
    states: dict
    edges: dict
    classes: int
    uncovered: list
    closure: dict
    injected_edge: dict | None = None
    member_index: dict | None = None

    def public(self):
        outcomes = collections.Counter(s["outcome"] for s in self.states.values())
        terminal = collections.Counter(
            s.get("action") for s in self.states.values()
            if s["outcome"] == "terminal")
        cycles, samples = _find_cycles(self.edges)
        return {
            "config": self.config,
            "states": len(self.states),
            "edges": sum(len(v) for v in self.edges.values()),
            "outcomes": dict(sorted(outcomes.items())),
            "terminal": dict(sorted(terminal.items())),
            "opaque": outcomes.get("opaque", 0),
            "outside": outcomes.get("outside", 0),
            "cycles": cycles,
            "cycle_samples": [[_node_text(x) for x in sample]
                              for sample in samples],
            "classes": self.classes,
            "uncovered": self.uncovered,
            "closure": self.closure,
            "injected_edge": self.injected_edge,
        }


def _state_key(opcode, type_classes, mem_class):
    return (opcode, tuple(type_classes), mem_class)


def build(source, config, features, *, pointer_width=64, slots=None,
          inject_edge=False, check_closure=False, extra_types=(),
          extra_mems=(), arity_overrides=None):
    """Build one configuration's graph and return a :class:`Report`."""
    doc = C.document(source)
    evaluator = E.Evaluator(doc, features)
    slots = slots or D.load_opcode_slots()
    arity_manifest = dsl.load_arity_manifest()
    extended = evaluator.extended(config)
    declared = _declared_types(source, pointer_width, extended)
    domain_mems = D.domain_axes(source, pointer_width)[1]
    states = {}
    member_index = {}
    edges = collections.defaultdict(list)
    uncovered = []
    total_classes = 0

    for rs_idx, rs in enumerate(doc["rulesets"]):
        nslots, infos = C.inspect_ruleset(rs)
        atoms = _atoms(rs)
        for opcode in rs["opcodes"]:
            arity, ptypes = _opcode_shape(opcode, slots, arity_manifest)
            if arity_overrides and opcode in arity_overrides:
                arity = arity_overrides[opcode]
            if arity is None:
                uncovered.append(opcode)
                continue
            if arity != nslots:
                n = max(arity, nslots)
            else:
                n = arity
            domain_types = sorted(declared, key=_type_text)
            axes = _candidate_axes(infos, n, ptypes, domain_types,
                                   extra_types, extended,
                                   include_non_pointer=bool(extra_types))
            mem_values = _memory_values(infos, domain_mems, pointer_width,
                                        extended, extra_mems)
            mem_values = mem_values if any(info.uses_mem for info in infos) else [None]
            type_classes = [_make_classes(axes[i], i, atoms, axes,
                                          mem_values if mem_values != [None] else [],
                                          evaluator, config)
                            for i in range(n)]
            mem_classes = (_make_mem_classes(mem_values, atoms, axes,
                                             evaluator, config)
                           if mem_values != [None] else None)
            total_classes += sum(len(x.members) for x in type_classes)
            for types in itertools.product(*axes):
                for mem in mem_values:
                    tc = tuple(type_classes[i].class_of[types[i]]
                               for i in range(n))
                    mc = mem_classes.class_of[mem] if mem_classes else None
                    key = _state_key(opcode, tc, mc)
                    representative = tuple(type_classes[i].members[tc[i]][0]
                                           for i in range(n))
                    representative_mem = (mem_classes.members[mc][0]
                                          if mem_classes else None)
                    state = states.setdefault(key, {
                        "key": key, "members": [], "types": representative,
                        "mem": representative_mem, "outcome": None, "action": None,
                        "type_idx": 0, "rule": None,
                    })
                    member = (tuple(types), mem)
                    if member not in state["members"]:
                        state["members"].append(member)
                    member_index[(opcode, tuple(types), mem)] = key

    for key, state in states.items():
        opcode, _classes, _mem_class = key
        types, mem = state["types"], state["mem"]
        # Re-find the ruleset atoms for this opcode.  Canonical gisel files
        # have one ruleset per opcode; the fallback keeps duplicate-opcode
        # fixtures safe by taking the union of their atoms.
        rses = [rs for rs in doc["rulesets"] if opcode in rs["opcodes"]]
        atoms = []
        seen = set()
        for rs in rses:
            for atom in _atoms(rs):
                k = _json_key(atom)
                if k not in seen:
                    seen.add(k); atoms.append(atom)
        if _opaque(evaluator, atoms, types, mem, config):
            state["outcome"] = "opaque"
            continue
        try:
            action, type_idx, new_type, rule = E.evaluate_with_rule(
                evaluator, config, opcode, list(types), _mem_desc(mem, extended))
        except (E.EvalError, IndexError, KeyError, TypeError, ValueError,
                AssertionError):
            state["outcome"] = "opaque"
            continue
        state.update({"action": action, "type_idx": type_idx, "rule": rule})
        if rule is None:
            state["outcome"] = "no-rule"
            continue
        if action in TERMINAL:
            state["outcome"] = "terminal"
            continue
        if type_idx >= len(types) or new_type == types[type_idx]:
            state["outcome"] = "stuck"
            continue
        if new_type not in declared:
            state["outcome"] = "outside"
            continue
        target = list(types)
        target[type_idx] = new_type
        target_key = _lookup_key(member_index, opcode, tuple(target), mem)
        if target_key is None:
            state["outcome"] = "outside"
            continue
        state["outcome"] = "moves"
        edges[key].append((target_key, {
            "action": action, "type_idx": type_idx, "rule": rule,
        }))

    closure = {"checked": bool(check_closure), "ok": True,
               "violations": []}
    if check_closure:
        for key, state in states.items():
            if state["outcome"] == "outside":
                closure["ok"] = False
                closure["violations"].append({
                    "state": _node_text(key), "reason": "outside",
                    "member": [_type_text(x) for x in state["types"]],
                })
                continue
            if state["outcome"] != "moves":
                continue
            targets = set()
            for types, mem in state["members"]:
                try:
                    action, type_idx, new_type, rule = E.evaluate_with_rule(
                        evaluator, config, key[0], list(types),
                        _mem_desc(mem, extended))
                except Exception as exc:
                    closure["ok"] = False
                    closure["violations"].append({
                        "state": _node_text(key), "member": [_type_text(x) for x in types],
                        "reason": "opaque: %s" % exc,
                    })
                    continue
                if rule != state["rule"] or action != state["action"]:
                    closure["ok"] = False
                    closure["violations"].append({
                        "state": _node_text(key),
                        "member": [_type_text(x) for x in types],
                        "reason": "different rule",
                        "rule": rule, "representative_rule": state["rule"],
                    })
                    continue
                target = list(types)
                if type_idx >= len(target) or new_type == target[type_idx]:
                    closure["ok"] = False
                    closure["violations"].append({
                        "state": _node_text(key), "member": [_type_text(x) for x in types],
                        "reason": "stuck mutation",
                    })
                    continue
                target[type_idx] = new_type
                target_key = _lookup_key(member_index, key[0], tuple(target), mem)
                if target_key is None:
                    closure["ok"] = False
                    closure["violations"].append({
                        "state": _node_text(key), "member": [_type_text(x) for x in types],
                        "reason": "outside", "mutation": _type_text(new_type),
                    })
                    continue
                targets.add(target_key)
            if len(targets) > 1:
                closure["ok"] = False
                closure["violations"].append({
                    "state": _node_text(key),
                    "reason": "multiple target classes",
                    "targets": [_node_text(x) for x in sorted(targets, key=_node_text)],
                })
            if len(closure["violations"]) >= 20:
                break

    injected = None
    if inject_edge:
        choices = [(source, target) for source in sorted(edges, key=_node_text)
                   for target, _label in edges[source]
                   if source != target]
        if not choices:
            choices = [(source, target) for source in sorted(edges, key=_node_text)
                       for target, _label in edges[source]]
        if not choices:
            raise GraphError("cannot inject edge: graph has no edges")
        source_node, target_node = choices[0]
        label = {"injected": True}
        edges[target_node].append((source_node, label))
        injected = {"from": _node_text(target_node),
                    "to": _node_text(source_node)}

    return Report(config, states, dict(edges), total_classes, uncovered,
                  closure, injected, member_index)


def _lookup_key(member_index, opcode, types, mem):
    return member_index.get((opcode, types, mem))


def oracle_check(report, oracle_path, evaluator, extended):
    result = {"total": 0, "matched": 0, "agree": 0, "disagree": 0,
              "uncovered": 0, "errors": 0, "first": None}
    with open(oracle_path) as stream:
        for line in stream:
            if not line.strip():
                continue
            query = json.loads(line)
            if query.get("config") != report.config:
                continue
            result["total"] += 1
            types = tuple(_parse_type(x, extended) for x in query["types"])
            mem = None
            if query.get("mem") is not None:
                mem = (query["mem"][0], int(query["mem"][1]))
            key = _lookup_key(report.member_index or {}, query["name"], types, mem)
            if key is None:
                result["uncovered"] += 1
                continue
            result["matched"] += 1
            try:
                action, type_idx, new_type = E.evaluate(
                    evaluator, report.config, query["name"], list(types),
                    _mem_desc(mem, extended))
                want = query.get("new_type", "LLT_invalid")
                got = "LLT_invalid" if new_type == ("invalid",) else _type_text(new_type)
                if (action, type_idx, got) == (query.get("action"),
                                               query.get("type_idx", 0), want):
                    result["agree"] += 1
                else:
                    result["disagree"] += 1
                    if result["first"] is None:
                        result["first"] = {"query": query, "got": [action, type_idx, got]}
            except Exception as exc:
                result["errors"] += 1
                if result["first"] is None:
                    result["first"] = {"query": query, "error": str(exc)}
    return result


def _oracle_inputs(path, configs, extended):
    """Read optional oracle points only to make their states addressable."""
    types, mems, arities = set(), set(), {}
    wanted = set(configs)
    with open(path) as stream:
        for line in stream:
            if not line.strip():
                continue
            query = json.loads(line)
            if query.get("config") not in wanted:
                continue
            arities[query["name"]] = max(arities.get(query["name"], 0),
                                          len(query.get("types", ())))
            for text in query.get("types", ()):
                types.add(_parse_type(text, extended))
            if query.get("mem") is not None:
                mems.add((query["mem"][0], int(query["mem"][1])))
    return (sorted(types, key=_type_text), sorted(mems), arities)


def _features(doc, path, configs):
    table = C.derive_features(doc, path, configs)
    if not table.table:
        raise GraphError("no configurations selected")
    return table


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gisel graph",
                                     description="find cycles in the legalizer quotient graph")
    parser.add_argument("source")
    parser.add_argument("--emit", default="core", choices=("core",),
                        help="graph input normal form (only core is supported)")
    parser.add_argument("--features")
    parser.add_argument("--config", action="append", dest="configs")
    parser.add_argument("--pointer-width", type=int, default=64)
    parser.add_argument("--oracle", help="check matching points in an oracle JSONL")
    parser.add_argument("--inject-edge", action="store_true")
    parser.add_argument("--check-closure", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        doc = C.document(args.source)
        features = _features(doc, args.features, args.configs)
        oracle_types = oracle_mems = ()
        oracle_arities = {}
        if args.oracle:
            # The oracle is not semantic input.  Its points only extend the
            # finite observation domain so the alignment check can address
            # every dumped boundary query.
            oracle_types, oracle_mems, oracle_arities = _oracle_inputs(
                args.oracle, features.table, True)
        reports = []
        for config in sorted(features.table):
            extended = E.Evaluator(doc, features).extended(config)
            config_oracle_types = []
            for value in oracle_types:
                config_oracle_types.append(value if extended
                                           else E.collapse_extended(value))
            report = build(args.source, config, features,
                           pointer_width=args.pointer_width,
                           inject_edge=args.inject_edge,
                           check_closure=args.check_closure,
                           extra_types=config_oracle_types,
                           extra_mems=oracle_mems,
                           arity_overrides=oracle_arities)
            if args.oracle:
                evaluator = E.Evaluator(doc, features)
                report.oracle = oracle_check(report, args.oracle, evaluator,
                                             evaluator.extended(config))
            reports.append(report)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, GraphError) as exc:
        print("gisel graph: %s" % exc, file=sys.stderr)
        return 2

    public = [r.public() for r in reports]
    for report, output in zip(reports, public):
        if args.oracle:
            output["oracle"] = getattr(report, "oracle")
        if args.json:
            continue
        print("config      : %s" % output["config"])
        print("states      : %d" % output["states"])
        print("edges       : %d" % output["edges"])
        print("outcomes    : %s" % output["outcomes"])
        print("terminal    : %s" % output["terminal"])
        print("opaque      : %d" % output["opaque"])
        print("outside     : %d" % output["outside"])
        print("cycles      : %d" % output["cycles"])
        if output["uncovered"]:
            print("uncovered   : %s" % sorted(set(output["uncovered"])))
        if output["closure"]["checked"]:
            print("closure     : %s" % ("ok" if output["closure"]["ok"] else "FAILED"))
            for violation in output["closure"]["violations"][:3]:
                print("  closure: %s" % violation)
        if args.oracle:
            print("oracle      : %s" % output["oracle"])
        for cycle in output["cycle_samples"]:
            print("   %s" % " -> ".join(cycle[:6]))
        print()
    if args.json:
        print(json.dumps({"reports": public}, indent=1, sort_keys=True))
    bad = any(r.public()["cycles"] for r in reports)
    bad = bad or any(not r.closure["ok"] for r in reports)
    if args.oracle:
        bad = bad or any(getattr(r, "oracle")["disagree"] or
                         getattr(r, "oracle")["errors"] or
                         getattr(r, "oracle")["uncovered"] for r in reports)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
