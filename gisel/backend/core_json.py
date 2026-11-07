"""Emit the ``-gen-legalizer-core`` JSON from the schema-0.4 normal form.

Mirrors ``LegalizerInfoEmitter::runCore`` (LegalizerInfoEmitter.cpp:4816),
``coreTypeValue`` (:1361) and ``coreSetJson`` (:2820).

The rule body is already the normal form; three things are re-spelled on the
way out:

* a type is named by its LLT, not by its record (``Target_s8`` -> ``s8``), and a
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

from .. import ast as A

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




# ---- AST path ------------------------------------------------------------

class CoreJson:
    """The same normal form, read directly from ``gisel.ast.Program``."""

    def __init__(self, program):
        self.program = program

    # ---- values ----------------------------------------------------------

    def type_json(self, v):
        if isinstance(v, str):
            # parse_program only leaves a string here when no declaration
            # named the token; the record backend rejected it the same way.
            raise ValueError("unknown type name %r: rules name declared "
                             "`type`/`select`/`type_set` records, not LLT "
                             "literals" % v)
        if isinstance(v, (A.Scalar, A.Integer, A.Float, A.BFloat16,
                          A.Pointer, A.Vector)):
            return A.llt_text(v)
        if isinstance(v, A.SelectValue):
            expr = self.type_json(v.otherwise)
            for cond, then in reversed(v.arms):
                guard = self.legacy_dag(cond) if v.legacy_guard else self.node(cond)
                expr = {"select": {"cond": guard,
                                   "then": self.type_json(then),
                                   "else": expr}}
            return expr
        if isinstance(v, A.SetValue):
            if v.of == "Int":
                return {"kind": "set", "of": "Int", "arity": v.arity,
                        "elems": list(v.elems)}
            rows = []
            for e in v.elems:
                if isinstance(e, tuple):
                    rows.append([self.type_json(x) for x in e])
                else:
                    rows.append(self.type_json(e))
            out = {"kind": "set", "of": "Type"}
            if v.arity != 1:
                out["arity"] = v.arity
            out["elems"] = rows
            return out
        raise TypeError(v)

    def legacy_dag(self, node):
        """Rule-guard semantics in the predicate-dag spelling old core used."""
        k = node.get("kind")
        if k == "leaf":
            return dict(node)
        if k == "not":
            inner = node.get("arg") or node.get("args", [None])[0]
            return {"kind": "not", "arg": self.legacy_dag(inner)}
        if k in ("all", "any", "nary"):
            op = node.get("op", "all_of" if k == "all" else "any_of")
            return {"kind": "nary", "op": op,
                    "args": [self.legacy_dag(a) for a in node.get("args", [])]}
        return self.node(node)

    def node(self, n):
        if isinstance(n, list):
            return [self.node(v) for v in n]
        if not isinstance(n, dict):
            return n
        k = n.get("kind")
        if k == "type":
            v = n["value"]
            if isinstance(v, A.SetValue):
                return self.type_json(v)
            return {"kind": "type", "value": self.type_json(v)}
        if k == "set":
            out = dict(n)
            if n.get("of", "Type") == "Int":
                out["elems"] = list(n.get("elems", []))
            else:
                rows = []
                for e in n.get("elems", []):
                    if isinstance(e, list):
                        if len(e) == 4 and isinstance(e[3], int):
                            rows.append([self.type_json(x) for x in e[:3]] + [e[3]])
                        else:
                            rows.append([self.type_json(x) for x in e])
                    else:
                        rows.append(self.type_json(e))
                out["elems"] = rows
            return out
        return {key: self.node(v) for key, v in n.items()}

    # ---- document --------------------------------------------------------

    def imms(self):
        found = set()

        def walk(x):
            if isinstance(x, list):
                for v in x:
                    walk(v)
            elif isinstance(x, dict):
                if x.get("kind") == "imm":
                    found.add(x["index"])
                for v in x.values():
                    walk(v)

        for rs in self.program.rulesets:
            for rule in rs.rules:
                walk(rule.predicate)
                walk(rule.on)
                walk(rule.to)
        return sorted(found)

    def domain(self):
        types = []
        for d in self.program.decls:
            if not isinstance(d, A.NamedType):
                continue
            norm = A.llt_text(d.llt)
            if ":*" not in norm:
                types.append(norm)
        types.append("p0:%d" % POINTER_WIDTH)
        return sorted(set(types))

    def rule(self, rule, ruleset, index, origin):
        parts = ['"action":%s' % _string(rule.action),
                 '"type_idx":%d' % rule.type_idx,
                 '"predicate":%s' % _compact(self.node(rule.predicate)),
                 '"schema": "0.4"',
                 '"op": %s' % _string(rule.op)]
        if rule.on is not None:
            parts.append('"on": %s' % _compact(self.node(rule.on)))
        if rule.to is not None:
            parts.append('"to": %s' % _compact(self.node(rule.to)))
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
               '  "domain": {"types": [%s], "imms": [%s], "mems": [], '
               '"orderings": [], "q0": []},'
               % (", ".join(_string(t) for t in self.domain()),
                  ", ".join(str(i) for i in self.imms())),
               '  "rulesets": [']
        for si, rs in enumerate(self.program.rulesets):
            origin = {"source": source_name, "line": lines.get(rs.name, 0)}
            out.append('    {"def": %s, "origin": %s,'
                       % (_string(rs.name), _compact(origin)))
            out.append('     "opcodes": [%s],'
                       % ", ".join(_string(o) for o in rs.opcodes))
            out.append('     "rules": [')
            for ri, rule in enumerate(rs.rules):
                text = self.rule(rule, rs.name, ri, origin)
                out.append("        " + text + ("," if ri + 1 < len(rs.rules) else ""))
            out.append("     ]}" + ("," if si + 1 < len(self.program.rulesets) else ""))
        out += ["  ],", '  "escapes": []', "}"]
        return "\n".join(out) + "\n"


def emit_core(gs, source_name, source_text=None):
    if not isinstance(gs, A.Program):
        raise TypeError("emit_core needs the language AST, not a record model")
    lines = stage_lines(source_text) if source_text else {}
    return CoreJson(gs).emit(source_name, lines)
