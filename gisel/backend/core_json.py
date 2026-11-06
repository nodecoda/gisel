"""Emit the ``-gen-legalizer-core`` JSON from the schema-0.4 normal form.

Mirrors ``LegalizerInfoEmitter::runCore`` (LegalizerInfoEmitter.cpp:4816),
``coreTypeValue`` (:1361) and ``coreSetJson`` (:2820).

The rule body is already the normal form; three things are re-spelled on the
way out:

* a type is named by its LLT, not by its record (``X86_s8`` -> ``s8``), and a
  pointer whose width the configuration decides is written as a wildcard
  (``p0:*``) inside a set but with its width (``p0:64``) in the domain;
* a select type becomes a nested ``{"select": {...}}`` value, because the
  branch is a property of the subtarget, not of the document;
* the domain is the set of normalised named types with the wildcards dropped,
  plus ``p0:<width>``, sorted and deduplicated (:4856).

``origin`` points at the ``.gisel`` source, not at the generated ``.td``, so
the gate compares documents after dropping it (plan AC5).
"""

import json
import re

from .. import td as T

SCHEMA = "legalizer-spec-core"
VERSION = "0.4"
POINTER_WIDTH = 64


_ORIGIN_RE = re.compile(r'"origin": \{[^{}]*\}')


def strip_origin(text):
    """Drop the per-rule ``origin`` values, keeping the key.

    ``origin`` names the source file and line; ours point at ``.gisel`` and the
    baseline at the generated ``.td``, so it is provenance, not semantics
    (plan AC5).  Both the golden test and ``gisel check --emit=core`` compare
    documents with the values erased.
    """
    return _ORIGIN_RE.sub('"origin": {}', text)


def _compact(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _string(s):
    return json.dumps(s, ensure_ascii=False)


class CoreJson:
    def __init__(self, gs):
        self.gs = gs
        self.exprs = {n: p for k, n, p in gs["decls"] if k == "type"}
        self.selects = {n: p for k, n, p in gs["decls"] if k == "select"}
        self.sets = T.collect_named_sets(gs["decls"])

    # ---- types -----------------------------------------------------------

    def type_name(self, name):
        """A record name -> its canonical LLT spelling (``s8``, ``p0:*``)."""
        expr = self.exprs.get(name)
        if expr is None:
            raise KeyError("not a named type: %r" % name)
        norm = T.normalize_llt(expr, self.exprs)
        if not norm:
            raise ValueError("cannot normalise type %r" % name)
        return norm

    def type_value(self, name):
        """A value in a rule: a string, or a nested select object."""
        if name in self.selects:
            return self.select_json(name)
        return self.type_name(name)

    def select_json(self, name):
        conds, types, otherwise = self.selects[name]
        value = self.type_value(otherwise)
        for i in range(len(conds) - 1, -1, -1):
            cond = self.pred_name(conds[i])
            value = {"select": {"cond": cond, "then": self.type_value(types[i]),
                                "else": value}}
        return value

    def pred_name(self, name):
        """A select guard: a feature leaf, or an inline predicate dag."""
        feats = {n: p for k, n, p in self.gs["decls"] if k == "feature"}
        if name in feats:
            return {"kind": "leaf", "name": "hasFeature", "args": [feats[name]]}
        preds = {n: p for k, n, p in self.gs["decls"] if k == "pred"}
        if name in preds:
            return T._bool_node(T.parse_bool(preds[name]), feats)
        raise KeyError("unknown select guard %r" % name)

    # ---- nodes -----------------------------------------------------------

    def node(self, n):
        if isinstance(n, list):
            return [self.node(v) for v in n]
        if not isinstance(n, dict):
            return n
        out = {}
        for k, v in n.items():
            if k == "value" and n.get("kind") == "type" and isinstance(v, str) \
                    and v in self.sets:
                # A named set stays one object, expanded: one spelling, one
                # normal form.
                return {"kind": "set", "of": "Type",
                        "elems": [self.type_value(m) for m in self.sets[v]]}
            if k == "value" and n.get("kind") == "type":
                out[k] = self.type_value(v) if isinstance(v, str) else self.node(v)
            elif k == "elems" and n.get("kind") == "set":
                out[k] = [self.type_value(row) if isinstance(row, str)
                          else [self.type_value(x) if isinstance(x, str) else x
                                for x in row]
                          for row in v]
            else:
                out[k] = self.node(v)
        return out

    # ---- document --------------------------------------------------------

    def domain(self):
        types = []
        for k, name, expr in self.gs["decls"]:
            if k != "type":
                continue
            norm = T.normalize_llt(expr, self.exprs)
            if norm and ":*" not in norm:
                types.append(norm)
        types.append("p0:%d" % POINTER_WIDTH)
        return sorted(set(types))

    def rule(self, rule, ruleset, index, origin):
        parts = ['"action":%s' % _string(rule["action"]),
                 '"type_idx":%d' % rule["type_idx"],
                 '"predicate":%s' % _compact(self.node(rule["predicate"])),
                 '"schema": "0.4"',
                 '"op": %s' % _string(rule["op"])]
        if rule.get("on") is not None:
            parts.append('"on": %s' % _compact(self.node(rule["on"])))
        if rule.get("to") is not None:
            parts.append('"to": %s' % _compact(self.node(rule["to"])))
        parts += ['"ruleset": %s' % _string(ruleset),
                  '"rule_index": %d' % index,
                  '"origin": %s' % _compact(origin)]
        return "{" + ", ".join(parts) + "}"

    def emit(self, source_name, lines=None):
        lines = lines or {}
        out = ["{",
               '  "schema": %s,' % _string(SCHEMA),
               '  "version": %s,' % _string(VERSION),
               '  "config": {"triple": "unspecified", "cpu": "unspecified", '
               '"features": [], "pointer_width": %d},' % POINTER_WIDTH,
               '  "domain": {"types": [%s], "imms": [], "mems": [], '
               '"orderings": [], "q0": []},'
               % ", ".join(_string(t) for t in self.domain()),
               '  "rulesets": [']
        for si, rs in enumerate(self.gs["rulesets"]):
            origin = {"source": source_name,
                      "line": lines.get(rs["def"], 0)}
            out.append('    {"def": %s, "origin": %s,'
                       % (_string(rs["def"]), _compact(origin)))
            out.append('     "opcodes": [%s],'
                       % ", ".join(_string(o) for o in rs["opcodes"]))
            out.append('     "rules": [')
            for ri, rule in enumerate(rs["rules"]):
                text = self.rule(rule, rs["def"], ri, origin)
                out.append("        " + text + ("," if ri + 1 < len(rs["rules"]) else ""))
            out.append("     ]}" + ("," if si + 1 < len(self.gs["rulesets"]) else ""))
        out += ["  ],", '  "escapes": []', "}"]
        return "\n".join(out) + "\n"


def stage_lines(text):
    """`ruleset Name:` -> line number, for origin.  Cheap and side-effect free."""
    out = {}
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("ruleset "):
            rest = s[len("ruleset "):]
            name = rest.split(":", 1)[0].strip()
            out.setdefault(name, i)
    return out


def emit_core(gs, source_name, source_text=None):
    lines = stage_lines(source_text) if source_text else {}
    return CoreJson(gs).emit(source_name, lines)
