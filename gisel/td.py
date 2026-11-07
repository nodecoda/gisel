#!/usr/bin/env python3
"""Keep a target legalizer's .td generated from a free-form .gisel source.

The .gisel is the source of truth for the 1075 rules; the .td keeps the
TableGen scaffolding (feature / named-type / select-type / type-set records and
rule-set metadata) that the emitter turns into the C++ fragments.  The rule
bodies are rendered by `dsl_spike` (the same grammar the forward round-trip
uses), and the generator resolves the canonical type/feature names back to the
target's original record names, so the generated .td produces byte-identical
-gen-legalizer / -gen-legalizer-table / -gen-legalizer-check artifacts and a
-gen-legalizer-core normal form that differs only in origin/line.

    gisel_td.py bootstrap --td X.td --core X.core.json --out X.gisel
    gisel_td.py gen X.gisel --out X.td
    gisel_td.py check X.gisel --td X.td
"""

import argparse
import json
import re
import sys
from pathlib import Path

from . import ast as A
from . import dsl as D


# ---- TableGen scaffolding extraction (bootstrap only) ---------------------

SCAFFOLD_CLASSES = {"LegalizeFeature", "LegalizePredicateDag",
                    "LegalizeNamedType", "LegalizeSelectType",
                    "LegalizeCoreTypeSet", "LegalizeNamedTypeList"}


def _scan_def(text, start):
    """Return the index just past the `def`/`defm` statement at `start`."""
    i, depth, instr = start, 0, False
    while i < len(text):
        c = text[i]
        if instr:
            if c == '"' and text[i - 1] != "\\":
                instr = False
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = j if j >= 0 else len(text)
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i)
            i = j + 2 if j >= 0 else len(text)
            continue
        else:
            if c == '"':
                instr = True
            elif c in "<[({":
                depth += 1
            elif c in ">])}":
                depth -= 1
                if c == "}" and depth == 0:
                    j = i + 1
                    while j < len(text) and text[j] in " \t\r\n":
                        j += 1
                    if j < len(text) and text[j] == ";":
                        j += 1
                    return j
            elif c == ";" and depth == 0:
                return i + 1
        i += 1
    raise ValueError("unterminated def at %d" % start)


def _match_list(text, start):
    depth, i = 0, start
    while i < len(text):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValueError("unbalanced list at %d" % start)


def _def_string(body, cls):
    m = re.search(r"%s<\s*\"([^\"]*)\"\s*>" % cls, body, re.S)
    return m.group(1) if m else None


def parse_scaffolding(td_path):
    """Ordered scaffolding declarations and rule-set metadata from a .td."""
    text = Path(td_path).read_text()
    includes = [ln.strip() for ln in text.splitlines()
                if ln.strip().startswith("include ")]
    decls = []     # ordered [(kind, name, payload)]
    rulesets = []  # ordered [(name, opcodes, comments)]
    for m in re.finditer(r"(?m)^(def|defm)\s+([A-Za-z0-9_]+)\s*:\s*"
                         r"([A-Za-z0-9_]+)", text):
        kw, name, cls = m.group(1), m.group(2), m.group(3)
        end = _scan_def(text, m.start())
        body = text[m.start():end]
        if kw == "defm":
            rulesets.append(_defm_meta(name, body))
        elif cls in SCAFFOLD_CLASSES:
            decls.append(_scaffold_decl(cls, name, body))
        elif cls == "LegalizeRuleSet":
            rulesets.append(_ruleset_meta(name, body))
    return {"includes": includes, "decls": decls, "rulesets": rulesets}


def _scaffold_decl(cls, name, body):
    if cls == "LegalizeFeature":
        return ("feature", name, _def_string(body, cls))
    if cls == "LegalizeNamedType":
        return ("type", name, _def_string(body, cls))
    if cls == "LegalizePredicateDag":
        m = re.search(r"LegalizePredicateDag<\s*(.*?)\s*>\s*;", body, re.S)
        return ("pred", name, m.group(1).strip())
    if cls == "LegalizeSelectType":
        m = re.search(r"LegalizeSelectType<\s*(\[[^\]]*\])\s*,\s*"
                      r"(\[[^\]]*\])\s*,\s*([A-Za-z0-9_]+)\s*>", body, re.S)
        conds = re.findall(r"[A-Za-z0-9_]+", m.group(1))
        types = re.findall(r"[A-Za-z0-9_]+", m.group(2))
        return ("select", name, (conds, types, m.group(3)))
    if cls == "LegalizeNamedTypeList":
        m = re.search(r"LegalizeNamedTypeList<\s*(\[[^\]]*\])\s*>", body, re.S)
        return ("type_list", name, re.findall(r"[A-Za-z0-9_]+", m.group(1)))
    m = re.search(r"LegalizeCoreTypeSet<\s*(.+?)\s*>", body, re.S)
    inner = m.group(1)
    if inner.startswith("["):
        return ("type_set", name, re.findall(r"[A-Za-z0-9_]+", inner))
    ref = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.Elems", inner.strip())
    return ("type_set", name, ("ref", ref.group(1)))


def _type_set_lists(decls):
    """name -> element list, resolving `X = Y.Elems` references."""
    raw = {n: p for k, n, p in decls if k in ("type_set", "type_list")}
    out = {}

    def resolve(name, stack=()):
        if name in out:
            return out[name]
        if name in stack or name not in raw:
            raise ValueError(f"unresolved type-set ref {name!r}")
        p = raw[name]
        out[name] = resolve(p[1], stack + (name,)) if isinstance(p, tuple) else p
        return out[name]

    for n in raw:
        resolve(n)
    return out


def _ruleset_meta(name, body):
    opcodes, comments, legacy = [], [], []
    m = re.search(r"LegalizeRuleSet<\s*\[([^\]]*)\]", body)
    if m:
        opcodes = re.findall(r'"([^"]*)"', m.group(1))
    cm = re.search(r"let\s+Comments\s*=\s*\[", body)
    if cm:
        raw = _match_list(body, cm.start() + cm.group(0).index("["))
        comments = re.findall(r'"([^"]*)"', raw)
    legacy = [int(x) for x in re.findall(r"ImmIdx<\s*(\d+)\s*>", body)]
    return (name, opcodes, comments, legacy)


def _defm_meta(name, body):
    opcodes, comments = [], []
    cm = re.search(r'"([^"]*)"\s*,\s*\[([^\]]*)\]', body)
    if cm:
        opcodes = [cm.group(1)]
        comments = re.findall(r'"([^"]*)"', cm.group(2))
    else:
        m2 = re.search(r'"([^"]*)"', body)
        if m2:
            opcodes = [m2.group(1)]
    legacy = [int(x) for x in re.findall(r"ImmIdx<\s*(\d+)\s*>", body)]
    return (name, opcodes, comments, legacy)


# ---- canonical type / predicate reconstruction ----------------------------

def _parse_pred_dag(dag, feat_names):
    """TableGen predicate dag -> legacy predicateJson node."""
    def walk(s):
        s = s.strip()
        if s.startswith("("):
            inner = s[1:-1].strip()
            op_m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", inner)
            op = op_m.group(1)
            rest = inner[op_m.end():].lstrip(",").strip()
            kids = _split_top(rest)
            if op == "not":
                return {"kind": "not", "arg": walk(kids[0])}
            return {"kind": "nary",
                    "op": "all_of" if op == "all_of" else "any_of",
                    "args": [walk(k) for k in kids]}
        if s in feat_names:
            return {"kind": "leaf", "name": "hasFeature", "args": [feat_names[s]]}
        raise ValueError("unknown predicate leaf %r" % s)
    return walk(dag.strip())


def _split_top(s):
    out, depth, cur = [], 0, []
    for c in s:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def _pred_dsl(node, feat_of):
    """predicateJson node -> free-form `A and not B` text (record names)."""
    k = node["kind"]
    if k == "leaf" and node["name"] == "hasFeature":
        return feat_of[node["args"][0]]
    if k == "not":
        inner = node["arg"] if "arg" in node else node["args"][0]
        return f"not {_pred_dsl(inner, feat_of)}"
    if k in ("nary", "all", "any"):
        op = node.get("op", "all_of" if k == "all" else "any_of")
        join = " and " if op == "all_of" else " or "
        return "(" + join.join(_pred_dsl(a, feat_of) for a in node["args"]) + ")"
    raise ValueError(f"unsupported predicate node {node!r}")


# ---- names for the bootstrap renderer ------------------------------------

def _type_set_lists(decls):
    """name -> element list, resolving `X = Y.Elems` references."""
    raw = {n: p for k, n, p in decls if k in ("type_set", "type_list")}
    out = {}

    def resolve(name, stack=()):
        if name in out:
            return out[name]
        if name in stack or name not in raw:
            raise ValueError(f"unresolved type-set ref {name!r}")
        p = raw[name]
        out[name] = resolve(p[1], stack + (name,)) if isinstance(p, tuple) else p
        return out[name]

    for n in raw:
        resolve(n)
    return out


class _ScaffoldNames:
    """Renderer-local names for `bootstrap`: canonical value -> record name.

    `bootstrap` reads a hand-written .td and a core JSON document and has to
    spell the core rules back with the target's record names.  This is the
    reverse renderer's exit computation, not a front-end model: the normal
    front end never builds one.
    """

    def __init__(self, decls):
        self.type = {}       # canonical LLT -> record name
        self.select = {}     # canonical select JSON -> record name
        self.type_set = {}   # member record-name tuple -> set record name
        self.records = {name for _, name, _ in decls}
        type_expr = {n: p for k, n, p in decls if k == "type"}
        feat_of = {n: p for k, n, p in decls if k == "feature"}
        dag_node = {n: _parse_pred_dag(p, feat_of) for k, n, p in decls
                    if k == "pred"}

        def parse(name, stack=()):
            return A._parse_llt(type_expr[name], type_expr, parse, stack)

        canon_of = {}
        for name, expr in type_expr.items():
            canon = A.llt_text(A._parse_llt(expr, type_expr, parse))
            self.type[canon] = name
            canon_of[name] = canon

        def cond_node(rec):
            if rec in feat_of:
                return {"kind": "leaf", "name": "hasFeature",
                        "args": [feat_of[rec]]}
            if rec in dag_node:
                return dag_node[rec]
            raise ValueError("unknown select cond %r" % rec)

        for k, name, payload in decls:
            if k != "select":
                continue
            conds, types, otherwise = payload
            acc = canon_of[otherwise]
            for i in range(len(conds) - 1, -1, -1):
                acc = {"select": {"cond": cond_node(conds[i]),
                                  "then": canon_of[types[i]], "else": acc}}
            self.select[json.dumps(acc, sort_keys=True)] = name

        resolved = _type_set_lists(decls)
        for k, name, payload in decls:
            if k == "type_set":
                self.type_set[tuple(resolved[name])] = name

    def select_value(self, value):
        return self.select.get(json.dumps(value, sort_keys=True))


# ---- .gisel: parse --------------------------------------------------------

DECL_RE = re.compile(r"^(feature|pred|type|select|type_set|type_list)\s+"
                     r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
RULESET_RE = re.compile(r"^ruleset\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")
NOTE_RE = re.compile(r'^note\s+"(.*)"$')
IMM_RE = re.compile(r"^imm_idx\(\s*(\d+)\s*\)$")


def _bool_tokens(text):
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[()]", text)


class _BoolParser:
    def __init__(self, text):
        self.toks = _bool_tokens(text)
        self.text = text
        self.pos = 0

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def take(self, want=None):
        t = self.peek()
        if t is None or (want is not None and t != want):
            raise ValueError(f"expected {want!r}, got {t!r} in {self.text!r}")
        self.pos += 1
        return t

    def parse_or(self):
        left = self.parse_and()
        while self.peek() == "or":
            self.take()
            left = ("or", left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_unary()
        while self.peek() == "and":
            self.take()
            left = ("and", left, self.parse_unary())
        return left

    def parse_unary(self):
        if self.peek() == "not":
            self.take()
            return ("not", self.parse_unary())
        if self.peek() == "(":
            self.take()
            node = self.parse_or()
            self.take(")")
            return node
        return ("name", self.take())


def parse_bool(text):
    p = _BoolParser(text)
    node = p.parse_or()
    if p.peek() is not None:
        raise ValueError(f"trailing tokens in predicate {text!r}")
    return node


def _parse_sel(text):
    """`if C then A else B` chain -> (conds, types, otherwise)."""
    p = _BoolParser(text)
    conds, types = [], []
    while p.peek() == "if":
        p.take()
        cond = p.parse_or()
        p.take("then")
        then = p.parse_or()
        p.take("else")
        if cond[0] != "name" or then[0] != "name":
            raise ValueError(f"select needs record names: {text!r}")
        conds.append(cond[1])
        types.append(then[1])
    els = p.parse_unary()
    if els[0] != "name" or p.peek() is not None:
        raise ValueError(f"select: bad tail {els!r} in {text!r}")
    return conds, types, els[1]


def _bool_dag_text(node):
    if node[0] == "name":
        return node[1]
    if node[0] == "not":
        return f"(not {_bool_dag_text(node[1])})"
    if node[0] == "and":
        return f"(all_of {_bool_dag_text(node[1])}, {_bool_dag_text(node[2])})"
    if node[0] == "or":
        return f"(any_of {_bool_dag_text(node[1])}, {_bool_dag_text(node[2])})"
    raise ValueError(node)


def _bool_node(node, feat_of):
    if node[0] == "name":
        return {"kind": "leaf", "name": "hasFeature", "args": [feat_of[node[1]]]}
    if node[0] == "not":
        return {"kind": "not", "arg": _bool_node(node[1], feat_of)}
    return {"kind": "nary",
            "op": "all_of" if node[0] == "and" else "any_of",
            "args": [_bool_node(a, feat_of) for a in node[1:]]}


def _bracket_depth(text):
    depth = 0
    instr = False
    prev = ""
    for c in text:
        if instr:
            if c == '"' and prev != "\\":
                instr = False
        elif c == '"':
            instr = True
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        prev = c
    return depth


def _join_continuations(lines):
    """Join a statement that a human wrapped inside brackets (free format).

    `lines` are (source line, raw text); the result keeps the line the
    statement started on, so a parse error inside a wrapped rule still points
    at the first physical line of that rule.
    """
    out, buf, start = [], None, None
    for ln, raw in lines:
        st = raw.strip()
        if buf is None:
            buf, start = st, ln
        else:
            buf += " " + st
        if _bracket_depth(buf) <= 0:
            out.append((start, buf))
            buf = None
    if buf is not None:
        out.append((start, buf))
    return out


def _wrap_statement(text, width=88, indent=8):
    """Greedy wrap at `, ` for a long rule; the parser joins it back."""
    if len(text) <= width:
        return [text]
    out, cur = [], ""
    for part in re.split(r"(?<=, )", text):
        if cur and len(cur) + len(part) > width:
            out.append(cur.rstrip())
            cur = " " * indent
        cur += part
    out.append(cur.rstrip())
    return out


GISE_HEADER = """\
//===- {target}LegalizerInfo.gisel - free-form legalizer rules --*- gisel -*-===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// Source of truth for {target}LegalizerInfo.td.  That .td is generated; do not
// edit it.  Regenerate and check with:
//
//   llvm-dev/tools/gisel_td.py gen <this file> --out {target}LegalizerInfo.td
//   llvm-dev/tools/gisel_td.py check <this file> --td {target}LegalizerInfo.td
//
// The rule body is one statement per line; the indentation after `ruleset`
// groups statements into one rule set.  The vocabulary is the core IR:
//
//   legal <pred>                            terminal: legal
//   lower/custom/unsupported/libcall <pred>
//   widen|narrow|more|fewer|bitcast(<obs>, <target>) [when <pred>]
//   scalarize(<obs>) [when <pred>]
//   clamp_min(<idx>, <elt>, <lanes>) / clamp_max(<idx>, <elt>, <lanes>)
//   imm_idx(<n>)                            coverage marker, not a core rule
//
// Observations: slot(i), elem_of, scalar_of, sort_of, num_elems, bits_of,
// size_of, size_in_bytes_of, is_byte_sized, addr_space, align_of, mem_slot,
// mem_ty, mem_ordering, mem_failure_ordering, is_pow2, is_bfloat16, is_float16.
// Constructors: pow2, pow2_min(n), multiple_of(n), pow2_ceil(n), clamp(l,h),
// ty(t), same_as(k), min_vector_size(n), int_of_size(n), elt_type_to(t,t),
// elt_size_to(t,n), div_lanes(t,n), vec_of(n,t), scalar_or_vec_of(n,t),
// replace(t), select(p,a,b), mul(a,b), urem(a,b), udiv(a,b).
// Predicates: feature("<C++ bool expression>"), true, A and B, A or B, not A,
// a == b (and !=, <, <=, >, >=), in(slot(t)|[t,...]), in_pairs, in_triples,
// in_mem_desc.
//
// The declarations below are the TableGen scaffolding the rules name: the
// feature booleans (whose record names become the C++ `bool`s), the named LLT
// constants, the select types that cache a subtarget choice, and the type
// lists/sets a rule can use as one operand.  A rule body never spells the
// target prefix; the generator resolves `s8`, `v2s64`, ... to the named
// records.
//
//===----------------------------------------------------------------------===//

"""


# ---- .gisel: bootstrap from a hand-written .td + core JSON ----------------

def bootstrap(td_path, core_path, title=None):
    scaf = parse_scaffolding(td_path)
    if title is None:
        # The hand-written .td names its records X86_ADD, AArch64_ADD, ...
        # Prefer that prefix over the file stem (`x86.td` is lowercase).
        title = next((name.split("_", 1)[0] for name, *_ in scaf["rulesets"]
                      if "_" in name), None)
        if title is None:
            stem = Path(td_path).stem
            title = (stem[:-len("LegalizerInfo")]
                     if stem.endswith("LegalizerInfo") else stem)
    core = json.loads(Path(core_path).read_text())
    meta = {name: (opcodes, comments, legacy)
            for name, opcodes, comments, legacy in scaf["rulesets"]}
    out = GISE_HEADER.format(target=title).rstrip("\n").splitlines()
    out += scaf["includes"]
    out.append("")
    feat_of = {n: p for k, n, p in scaf["decls"] if k == "feature"}
    rec_of = {p: n for n, p in feat_of.items()}
    gdecls = []
    for kind, name, payload in scaf["decls"]:
        if kind == "pred":
            payload = _pred_dsl(_parse_pred_dag(payload, feat_of), rec_of)
        gdecls.append((kind, name, payload))
    for kind, name, payload in gdecls:
        if kind == "feature":
            out.append(f"feature {name} = {payload}")
        elif kind == "pred":
            out.append(f"pred {name} = {payload}")
        elif kind == "type":
            out.append(f"type {name} = {payload}")
        elif kind == "select":
            conds, types, els = payload
            expr = els
            for c, t in zip(reversed(conds), reversed(types)):
                expr = f"if {c} then {t} else {expr}"
            out.append(f"select {name} = {expr}")
        elif kind == "type_list":
            out.append(f"type_list {name} = [" + ", ".join(payload) + "]")
        elif isinstance(payload, tuple):
            out.append(f"type_set {name} = {payload[1]}.Elems")
        else:
            out.append(f"type_set {name} = [" + ", ".join(payload) + "]")
    out.append("")
    names = _ScaffoldNames(scaf["decls"])
    _orig_type_value = D.render_type_value
    _orig_set = D.render_set

    def _type_value(v):
        if isinstance(v, str):
            return names.type.get(v, v)
        named = names.select_value(v)
        return named if named is not None else _orig_type_value(v)

    def _set(n):
        if n.get("arity", 1) == 1:
            recs = tuple(names.type.get(e, e) for e in n["elems"])
            if recs in names.type_set:
                return names.type_set[recs]
        return _orig_set(n)

    def _rule(r):
        sugar = _clamp_sugar(r)
        return sugar if sugar is not None else D.render_rule(r)

    D.render_type_value = _type_value
    D.render_set = _set
    for rs in core["rulesets"]:
        opcodes, comments, legacy = meta[rs["def"]]
        assert opcodes == rs["opcodes"], (rs["def"], opcodes, rs["opcodes"])
        out.append(f"ruleset {rs['def']}: " + " ".join(opcodes))
        for c in comments:
            out.append(f"    note {json.dumps(c)}")
        for r in rs["rules"]:
            out += ["    " + ln for ln in _wrap_statement(_rule(r))]
        for idx in legacy:
            out.append(f"    imm_idx({idx})")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


_STRIP_KEYS = {"schema", "ruleset", "rule_index", "origin", "def", "_line"}


def _strip_normal(rule):
    """Rule equality without the per-rule bookkeeping keys."""
    return {k: v for k, v in rule.items() if k not in _STRIP_KEYS}


def _clamp_sugar(r):
    """Render a clamp_min/clamp_max rule as the sugar it was written as.

    Only fires when the rule is exactly what the clamp class expands to, so a
    hand-written `more(replace(vec_of(...)))` is never silently rewritten.
    """
    if r["op"] not in ("more", "fewer"):
        return None
    to = r.get("to") or {}
    if to.get("kind") != "replace" or len(to.get("args", [])) != 1:
        return None
    ctor = to["args"][0]
    want = "vecOf" if r["op"] == "more" else "scalarOrVecOf"
    if ctor.get("kind") != want or len(ctor.get("args", [])) != 2:
        return None
    lanes, elem = ctor["args"]
    if lanes.get("kind") not in ("numElems", "int"):
        return None
    if elem.get("kind") != "elemOf":
        return None
    if lanes["kind"] == "numElems":
        ty = lanes["args"][0]
        if ty.get("kind") != "ty":
            return None
    sl = elem["args"][0]
    if sl.get("kind") != "slot":
        return None
    guard = r.get("predicate") or {}
    if guard.get("kind") != "all" or len(guard.get("args", [])) != 4:
        return None
    elem_eq = guard["args"][2]
    if elem_eq.get("kind") != "eq" or len(elem_eq.get("args", [])) != 2:
        return None
    elt = elem_eq["args"][1]
    if elt.get("kind") != "ty" or elt["args"][0].get("kind") != "type":
        return None
    idx = sl["index"]
    op = "clamp_min" if r["op"] == "more" else "clamp_max"
    expected = D.compile_stmt({"op": op, "idx": idx,
                              "elt": elt["args"][0]["value"], "lanes": lanes})
    if _strip_normal(expected) != _strip_normal(r):
        return None
    return (f"{op}({idx}, {D.render_type_value(elt['args'][0]['value'])}, "
            f"{D.render_expr(lanes)})")


# ---- .gitd: emit ----------------------------------------------------------

class NamedTdEmitter(D.TdEmitter):
    """TdEmitter that reuses the target's original record names.

    With an ``ast.NameTable`` the type positions arrive as structured values
    and are named here, at the renderer's exit.  The legacy ``Names`` path
    stays for the bootstrap/dev harness until Phase 3 removes it.
    """

    def __init__(self, names):
        self.names = names

    def _feat(self, s):
        if isinstance(self.names, A.NameTable):
            return self.names.feature_name(s)
        return self.names.feature[s]

    def _type(self, name):
        if isinstance(self.names, A.NameTable):
            if name in self.names.records:
                return name
            raise ValueError(f"unknown type name {name!r}: rules name declared "
                             f"`type`/`select`/`type_set` records, not LLT literals")
        if name in self.names.type:
            return self.names.type[name]
        if name in self.names.records:
            return name
        raise ValueError(f"unknown type name {name!r}: rules name declared "
                     f"`type`/`select`/`type_set` records, not LLT literals")

    def _type_value(self, v):
        if isinstance(self.names, A.NameTable):
            if isinstance(v, str):
                return self._type(v)
            return self.names.value_name(v)
        if isinstance(v, str):
            return self._type(v)
        name = self.names.select_value(v)
        if name is None:
            raise KeyError(f"no named select for {json.dumps(v, sort_keys=True)}")
        return name

    def _select_cond(self, cond):
        raise AssertionError("select conditions are resolved by _type_value")

    def _set(self, n):
        arity = n.get("arity", 1)
        elems = n["elems"]
        if n.get("of") == "Int":
            # An immediate set is integer literals, not named types.
            return "[" + ", ".join(str(e) for e in elems) + "]"
        if arity == 1:
            recs = [self._type_value(e) for e in elems]
            # A named type set keeps the .td readable; the emitter expands it
            # either way, so the artifact is the same.
            if isinstance(self.names, A.NameTable):
                named = self.names.set_name_td(elems)
            else:
                named = self.names.type_set.get(tuple(recs))
            if named is not None:
                return named
            return "[" + ", ".join(recs) + "]"
        if arity == 2 and len(elems[0]) == 4:
            return ("[" + ", ".join(
                f"LegalizeMemDesc<{self._type_value(e[0])}, "
                f"{self._type_value(e[1])}, {self._type_value(e[2])}, {e[3]}>"
                for e in elems) + "]")
        return ("[" + ", ".join(
            "[" + ", ".join(self._type_value(x) for x in e) + "]"
            for e in elems) + "]")


def _emit_ast_decl(d):
    """AST declaration -> the same TableGen line the record payload produced."""
    if isinstance(d, A.Feature):
        return f'def {d.name} : LegalizeFeature<"{d.cxx}">;'
    if isinstance(d, A.PredicateDecl):
        dag = _bool_dag_text(parse_bool(d.source))
        return f"def {d.name} : LegalizePredicateDag<{dag}>;"
    if isinstance(d, A.NamedType):
        return f'def {d.name} : LegalizeNamedType<"{d.source}">;'
    if isinstance(d, A.TypeList):
        return f"def {d.name} : LegalizeNamedTypeList<[{', '.join(d.members)}]>;"
    if isinstance(d, A.SelectType):
        conds = [c for c, _ in d.arms]
        types = [t for _, t in d.arms]
        return (f"def {d.name} : LegalizeSelectType<"
                f"[{', '.join(conds)}], [{', '.join(types)}], {d.otherwise}>;")
    if isinstance(d, A.TypeSet):
        if d.source_ref:
            return f"def {d.name} : LegalizeCoreTypeSet<{d.source_ref}.Elems>;"
        return f"def {d.name} : LegalizeCoreTypeSet<[{', '.join(d.members)}]>;"
    raise TypeError(d)


def _rule_sets_view(gs):
    """The renderer's rule-set view (comments/coverage/rules)."""
    return [{"def": rs.name, "opcodes": rs.opcodes,
             "comments": rs.comments, "legacy": rs.coverage,
             "rules": rs.rules} for rs in gs.rulesets]


def target_name(gs, source_name):
    """The target a source belongs to: the first rule set's def prefix.

    Deriving it from the rule sets rather than the file name keeps generated
    artifacts identical when a source is renamed or copied, and lets `check`
    work on a scratch copy.  `Tgt_IMPLICIT_DEF` -> `Tgt`.
    """
    for rs in gs.rulesets:
        if "_" in rs.name:
            return rs.name.split("_", 1)[0]
    return Path(source_name).stem


def emit_td(gs, source_name):
    if not isinstance(gs, A.Program):
        raise TypeError("emit_td needs the language AST, not a record model")
    names = A.NameTable(gs)
    decls = [_emit_ast_decl(d) for d in gs.decls]
    includes = ['include "%s"' % i.path for i in gs.includes]
    rulesets = _rule_sets_view(gs)
    emitter = NamedTdEmitter(names)
    target = target_name(gs, source_name)
    out = ["//===- " + target + "LegalizerInfo.td - generated legalizer rules "
           "-*- tablegen -*-===//",
           "//",
           "// Part of the LLVM Project, under the Apache License v2.0 with LLVM",
           "// Exceptions. See https://llvm.org/LICENSE.txt for license information.",
           "// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception",
           "//",
           "//===----------------------------------------------------------------------===//",
           "//",
           f"// Generated from {target}LegalizerInfo.gisel by llvm-dev/tools/gisel_td.py.",
           "// Do not edit: edit the source and re-run the generator.",
           "",
           "//===----------------------------------------------------------------------===//"]
    out += includes
    out += ["//===----------------------------------------------------------------------===//", ""]
    out += decls
    out.append("")
    for rs in rulesets:
        opcodes = ", ".join(json.dumps(o) for o in rs["opcodes"])
        out.append(f"def {rs['def']} : LegalizeRuleSet<[{opcodes}]> {{")
        if rs["comments"]:
            out.append("  let Comments = [")
            out += [f"    {json.dumps(c)}," for c in rs["comments"]]
            out.append("  ];")
        out.append("  let Rules = [")
        rendered = [emitter.rule(r) for r in rs["rules"]]
        rendered += [f"ImmIdx<{i}>" for i in rs.get("legacy", [])]
        out += [f"    {t}," for t in rendered]
        out.append("  ];")
        out.append("}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---- CLI ------------------------------------------------------------------

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap")
    b.add_argument("--td", required=True)
    b.add_argument("--core", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--title", default=None)
    g = sub.add_parser("gen")
    g.add_argument("gisel")
    g.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("gisel")
    c.add_argument("--td", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "bootstrap":
        text = bootstrap(args.td, args.core, args.title)
        Path(args.out).write_text(text)
        print(f"{args.out}: {len(text.splitlines())} lines")
        return 0
    if args.cmd == "gen":
        gs = A.parse_program(Path(args.gisel).read_text())
        Path(args.out).write_text(emit_td(gs, args.gisel))
        print(f"{args.out}: {len(gs.rulesets)} rule sets, "
              f"{sum(len(r.rules) for r in gs.rulesets)} rules")
        return 0
    gs = A.parse_program(Path(args.gisel).read_text())
    got = emit_td(gs, args.gisel)
    want = Path(args.td).read_text()
    if got == want:
        print(f"{args.td}: up to date")
        return 0
    import difflib
    sys.stderr.writelines(difflib.unified_diff(
        want.splitlines(True), got.splitlines(True), args.td, "<generated>"))
    print(f"{args.td}: STALE (re-run `gisel_td.py gen`)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
