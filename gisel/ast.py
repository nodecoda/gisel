#!/usr/bin/env python3
"""The language AST for `.gisel`.

This is the front-end model: includes, declarations, rule sets and rules.
It is deliberately not TableGen-shaped:

* a type is a structured LLT (``Scalar(32)``, ``Pointer(0, None)``, ...);
* a rule's type positions hold semantic values, not record names;
* a rule-set is ``(name, opcodes, rules)``; ``def`` is only a rendering name.

The ``.td``/``.inc`` renderers still have to spell the target's record names
(``Target_s32``).  They build a renderer-local :class:`NameTable` at the exit;
nothing in this module treats a record name as a semantic value.

``to_record_model()`` is a test/oracle adapter: it downgrades a ``Program``
to the record-shaped dict the pre-AST front end returned, so the frozen
migration digests can still pin the AST's exact content.  No backend uses it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from . import dsl as D


# ---- LLT -----------------------------------------------------------------

WILDCARD = None  # Pointer(addrspace, None) is `p<as>:*`

@dataclass(frozen=True)
class Scalar:
    bits: int


@dataclass(frozen=True)
class Integer:
    bits: int


@dataclass(frozen=True)
class Float:
    bits: int


@dataclass(frozen=True)
class BFloat16:
    pass


@dataclass(frozen=True)
class Pointer:
    addrspace: int
    bits: int | None          # None is the wildcard: `p0:*`


@dataclass(frozen=True)
class Vector:
    lanes: int
    scalable: bool
    elem: "LLT"


LLT = Scalar | Integer | Float | BFloat16 | Pointer | Vector


def llt_text(t: LLT) -> str:
    """Canonical Core IR spelling: ``s32``, ``p0:*``, ``nxv4s32``."""
    if isinstance(t, Scalar):
        return "s%d" % t.bits
    if isinstance(t, Integer):
        return "i%d" % t.bits
    if isinstance(t, Float):
        return "f%d" % t.bits
    if isinstance(t, BFloat16):
        return "bf16"
    if isinstance(t, Pointer):
        return "p%d:%s" % (t.addrspace, "*" if t.bits is None else t.bits)
    if isinstance(t, Vector):
        return ("nxv" if t.scalable else "v") + str(t.lanes) + llt_text(t.elem)
    raise TypeError(t)


# ---- type values ---------------------------------------------------------

@dataclass(frozen=True)
class SelectValue:
    """``if C1 then T1 else if C2 then T2 else E``, in source order.

    ``legacy_guard`` records how the old core emitter serialized the guard:
    guards lifted from a `select` declaration / `pred` declaration went
    through the predicate-dag path (`nary`/`not(arg)`); an inline
    `select_type(...)` kept the core `all`/`any` shape.  It is serialization
    provenance, not semantics.
    """
    arms: tuple[tuple[Any, "TypeValue"], ...]   # Pred is a normal-form dict
    otherwise: "TypeValue"
    legacy_guard: bool = False


@dataclass(frozen=True)
class SetValue:
    of: str                 # "Type" or "Int"
    arity: int
    elems: tuple[Any, ...]


TypeValue = LLT | SelectValue | SetValue


def _pred_key(p: Any) -> str:
    return json.dumps(p, sort_keys=True, separators=(",", ":"))


def value_key(v: TypeValue) -> tuple:
    if isinstance(v, (Scalar, Integer, Float, BFloat16, Pointer, Vector)):
        return ("llt", llt_text(v))
    if isinstance(v, SelectValue):
        return ("select", v.legacy_guard,
                tuple((_pred_key(p), value_key(t)) for p, t in v.arms),
                value_key(v.otherwise))
    if isinstance(v, SetValue):
        def elem(e):
            if isinstance(e, tuple):
                return tuple(elem(x) for x in e)
            if isinstance(e, (Scalar, Integer, Float, BFloat16, Pointer,
                              Vector, SelectValue, SetValue)):
                return value_key(e)
            return e
        return ("set", v.of, v.arity, tuple(elem(e) for e in v.elems))
    raise TypeError(v)


# ---- declarations --------------------------------------------------------

@dataclass
class Include:
    path: str
    line: int


@dataclass
class Feature:
    name: str
    cxx: str
    line: int


@dataclass
class NamedType:
    name: str
    llt: LLT
    source: str             # the original C++ spelling, render-only
    line: int


@dataclass
class PredicateDecl:
    name: str
    pred: dict              # semantic all/any/not tree
    source: str             # original `A and not B` text, render-only
    line: int


@dataclass
class SelectType:
    name: str
    arms: tuple[tuple[str, str], ...]   # (condition record, then record)
    otherwise: str                      # else record
    value: SelectValue
    line: int


@dataclass
class TypeSet:
    name: str
    members: tuple[str, ...]            # source record names
    source_ref: str | None              # `X.Elems`, if written that way
    value: SetValue
    line: int


@dataclass
class TypeList:
    name: str
    members: tuple[str, ...]
    value: SetValue
    line: int


Decl = Include | Feature | NamedType | PredicateDecl | SelectType | TypeSet | TypeList


# ---- rules ---------------------------------------------------------------

@dataclass
class Rule:
    op: str
    action: str
    type_idx: int
    on: dict | None
    to: dict | None
    predicate: dict
    line: int

    # Backends still read a few keys positionally; keep that spelling local
    # to the renderers instead of reintroducing a dict model in the AST.
    def __getitem__(self, key):
        if key == "_line":
            return self.line
        return getattr(self, key)

    def get(self, key, default=None):
        if key == "_line":
            return self.line
        return getattr(self, key, default)


@dataclass
class RuleSet:
    name: str
    opcodes: list[str]
    rules: list[Rule]
    comments: list[str]
    coverage: list[int]
    line: int

    def __getitem__(self, key):
        if key == "def":
            return self.name
        if key == "legacy":
            return self.coverage
        return getattr(self, key)

    def get(self, key, default=None):
        if key == "def":
            return self.name
        if key == "legacy":
            return self.coverage
        return getattr(self, key, default)


@dataclass
class Program:
    includes: list[Include]
    decls: list[Decl]
    rulesets: list[RuleSet]
    features: dict[str, Feature] = field(default_factory=dict)
    preds: dict[str, PredicateDecl] = field(default_factory=dict)
    named_types: dict[str, NamedType] = field(default_factory=dict)
    selects: dict[str, SelectType] = field(default_factory=dict)
    setlike: dict[str, TypeSet | TypeList] = field(default_factory=dict)


# ---- LLT parser ----------------------------------------------------------

def _parse_llt(expr: str, type_sources: dict[str, str],
               resolve_named, stack: tuple[str, ...] = ()) -> LLT:
    """Parse one C++ LLT expression into a structured LLT.

    Named references are resolved through ``resolve_named`` (which walks the
    declaration table and reports cycles).  This is the only place in the
    front end that reads the C++ spelling.
    """
    t = expr.strip()
    if not any(c in t for c in "(){} \t\n") and t in type_sources:
        if t in stack:
            raise ValueError("cyclic LLT reference: %s" % " -> ".join(stack + (t,)))
        return resolve_named(t, stack + (t,))

    # `LLT::<kind>(args)`: the grammar's type-expression constructor.  This
    # is the front end's only reading of the C++ spelling; the backends never
    # see it.
    m = re.fullmatch(r"LLT::([A-Za-z_][A-Za-z0-9_]*)\((.*)\)", t, re.S)
    if m:
        kind, args = m.group(1), m.group(2).strip()
        if kind == "scalar" and args.isdigit():
            return Scalar(int(args))
        if kind == "integer" and args.isdigit():
            return Integer(int(args))
        floats = {"bfloat16": BFloat16,
                  "float16": lambda: Float(16), "float32": lambda: Float(32),
                  "float64": lambda: Float(64),
                  "float128": lambda: Float(128)}
        if kind in floats and not args:
            return floats[kind]()
        if kind == "pointer":
            parts = args.split(",", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                bits = parts[1].strip()
                return Pointer(int(parts[0]),
                               int(bits) if bits.isdigit() else WILDCARD)
        if kind in ("fixed_vector", "scalable_vector"):
            comma = args.find(",")
            if comma >= 0:
                lanes, elem = args[:comma].strip(), args[comma + 1:].strip()
                if lanes.isdigit():
                    e = (Scalar(int(elem)) if elem.isdigit()
                         else _parse_llt(elem, type_sources, resolve_named, stack))
                    return Vector(int(lanes), kind == "scalable_vector", e)
    raise ValueError("cannot normalize LLT expression %r" % expr)


# ---- predicate text (pred declarations and select guards) ----------------

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


def _bool_tree(text):
    p = _BoolParser(text)
    node = p.parse_or()
    if p.peek() is not None:
        raise ValueError(f"trailing tokens in predicate {text!r}")
    return node


def _tree_to_pred(node, feature_of, pred_of, stack=()):
    """Bool tree -> semantic all/any/not tree with feature leaves."""
    if node[0] == "name":
        name = node[1]
        if name in feature_of:
            return {"kind": "leaf", "name": "hasFeature",
                    "args": [feature_of[name]]}
        if name in pred_of:
            if name in stack:
                raise ValueError("cyclic predicate reference: %s"
                                 % " -> ".join(stack + (name,)))
            return _tree_to_pred(_bool_tree(pred_of[name]), feature_of,
                                 pred_of, stack + (name,))
        raise ValueError("unknown predicate leaf %r" % name)
    if node[0] == "not":
        return {"kind": "not", "args": [_tree_to_pred(node[1], feature_of,
                                                       pred_of, stack)]}
    return {"kind": "all" if node[0] == "and" else "any",
            "args": [_tree_to_pred(a, feature_of, pred_of, stack)
                     for a in node[1:]]}


def _parse_select_chain(text):
    """`if C then A else if D then B else E` -> ([(C, A), (D, B)], E)."""
    p = _BoolParser(text)
    arms = []
    while p.peek() == "if":
        p.take()
        cond = p.parse_or()
        p.take("then")
        then = p.parse_or()
        p.take("else")
        if cond[0] != "name" or then[0] != "name":
            raise ValueError(f"select needs record names: {text!r}")
        arms.append((cond[1], then[1]))
    els = p.parse_unary()
    if els[0] != "name" or p.peek() is not None:
        raise ValueError(f"select: bad tail {els!r} in {text!r}")
    return tuple(arms), els[1]


# ---- rules ---------------------------------------------------------------

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


DECL_RE = re.compile(r"^(feature|pred|type|select|type_set|type_list)\s+"
                     r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
RULESET_RE = re.compile(r"^ruleset\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")
NOTE_RE = re.compile(r'^note\s+"(.*)"$')
IMM_RE = re.compile(r"^imm_idx\(\s*(\d+)\s*\)$")


def _convert_type_value(v, resolve_name):
    if isinstance(v, str):
        try:
            return resolve_name(v)
        except ValueError as e:
            # A rule may spell a canonical LLT literal (`s8`) or an unknown
            # record name.  The old front end kept it verbatim so `lint`
            # could point at that line; `gen` still rejects it.  Resolved
            # names always become structured values, so a bare string here
            # means exactly "undeclared name".
            if str(e).startswith("unknown type name"):
                return v
            raise
    if isinstance(v, dict) and "select" in v:
        sel = v["select"]
        arms = tuple((sel["cond"], _convert_type_value(sel["then"], resolve_name)),)
        return SelectValue(arms, _convert_type_value(sel["else"], resolve_name),
                           legacy_guard=False)
    raise ValueError("bad type value %r" % (v,))


def _convert_node(node, resolve_name):
    if isinstance(node, list):
        return [_convert_node(v, resolve_name) for v in node]
    if not isinstance(node, dict):
        return node
    k = node.get("kind")
    if k == "type":
        return {"kind": "type",
                "value": _convert_type_value(node["value"], resolve_name)}
    if k == "set":
        out = dict(node)
        if node.get("of", "Type") == "Type":
            rows = []
            for e in node.get("elems", []):
                if isinstance(e, list):
                    if len(e) == 4 and isinstance(e[3], int):
                        # mem_desc(type0, type1, memty, align)
                        rows.append([_convert_type_value(x, resolve_name)
                                     for x in e[:3]] + [e[3]])
                    else:
                        rows.append([_convert_type_value(x, resolve_name)
                                     for x in e])
                else:
                    rows.append(_convert_type_value(e, resolve_name))
            out["elems"] = rows
        return out
    return {key: _convert_node(v, resolve_name) for key, v in node.items()}


# ---- program parser ------------------------------------------------------

def parse_program(text: str) -> Program:
    includes, raw_decls, raw_rulesets = [], [], []
    decl_lines = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        i += 1
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("include "):
            m = re.fullmatch(r'include\s+"(.*)"', s)
            if not m:
                raise ValueError(f"line {i}: bad include {s!r}")
            includes.append(Include(m.group(1), i))
            continue
        m = DECL_RE.match(s)
        if m:
            kind, name, body = m.group(1), m.group(2), m.group(3).strip()
            decl_lines[name] = i
            if kind == "select":
                arms, otherwise = _parse_select_chain(body)
                raw_decls.append(("select", name, (arms, otherwise), body, i))
            elif kind == "type_list":
                raw_decls.append(("type_list", name,
                                  re.findall(r"[A-Za-z0-9_]+", body), body, i))
            elif kind == "type_set":
                ref = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.Elems", body)
                if ref:
                    raw_decls.append(("type_set", name, ("ref", ref.group(1)),
                                      body, i))
                else:
                    raw_decls.append(("type_set", name,
                                      re.findall(r"[A-Za-z0-9_]+", body),
                                      body, i))
            else:
                raw_decls.append((kind, name, body, body, i))
            continue
        m = RULESET_RE.match(s)
        if not m:
            raise ValueError(f"line {i}: unrecognized source line {s!r}")
        name, opcodes = m.group(1), m.group(2).split()
        ruleset_line = i
        comments, body, coverage, raw_body = [], [], [], []
        while i < len(lines):
            raw = lines[i]
            if raw.strip() and not raw.startswith((" ", "\t")):
                break
            i += 1
            st = raw.strip()
            if not st or st.startswith("//"):
                continue
            raw_body.append((i, raw))
        for ln, st in _join_continuations(raw_body):
            nm = NOTE_RE.match(st)
            im = IMM_RE.match(st)
            if nm:
                comments.append(nm.group(1))
            elif im:
                coverage.append(int(im.group(1)))
            else:
                body.append((ln, st))
        snippet = ["rule " + " ".join(opcodes) + ":"]
        snippet += ["  " + b.strip() for _, b in body]
        line_map = [ruleset_line] + [ln for ln, _ in body]
        tree = D.Parser("\n".join(snippet), line_map=line_map).parse()
        compiled = D.compile_rulesets(tree)
        raw_rulesets.append((name, opcodes, comments, coverage, ruleset_line,
                             compiled))

    # First build the declaration tables; resolution below is two-pass so
    # forward references in `type X = ... Y ...` work like they did before.
    features = {n: Feature(n, p, ln) for k, n, p, _src, ln in raw_decls
                if k == "feature"}
    pred_src = {n: (p, ln) for k, n, p, _src, ln in raw_decls if k == "pred"}
    type_src = {n: (p, ln) for k, n, p, _src, ln in raw_decls if k == "type"}
    raw_selects = {n: (p, ln) for k, n, p, _src, ln in raw_decls
                   if k == "select"}
    raw_setlike = {n: (k, p, ln) for k, n, p, _src, ln in raw_decls
                   if k in ("type_set", "type_list")}

    named_types: dict[str, NamedType] = {}
    select_types: dict[str, SelectType] = {}
    setlike: dict[str, TypeSet | TypeList] = {}
    preds: dict[str, PredicateDecl] = {}
    feature_of = {n: f.cxx for n, f in features.items()}

    def resolve_type(name, stack=()):
        if name in named_types:
            return named_types[name].llt
        if name not in type_src:
            raise ValueError("unknown type name %r" % name)
        expr, ln = type_src[name]
        try:
            llt = _parse_llt(expr, {n: v[0] for n, v in type_src.items()},
                             lambda n, st: resolve_type(n, st), stack)
        except (ValueError, RecursionError) as e:
            raise ValueError(f"line {ln}: cannot normalize LLT expression "
                             f"for {name}: {expr!r} (expected an LLT "
                             f"scalar/integer/pointer/fixed_vector/"
                             f"scalable_vector/float constructor)") from e
        named_types[name] = NamedType(name, llt, expr, ln)
        return llt

    def resolve_pred(name, stack=()):
        if name in preds:
            return preds[name].pred
        if name not in pred_src:
            raise ValueError("unknown predicate %r" % name)
        source, ln = pred_src[name]
        try:
            pred = _tree_to_pred(_bool_tree(source),
                                 feature_of,
                                 {n: v[0] for n, v in pred_src.items()},
                                 stack)
        except ValueError as e:
            raise ValueError(f"line {ln}: {e}") from e
        preds[name] = PredicateDecl(name, pred, source, ln)
        return pred

    def resolve_name(name, stack=()):
        if name in type_src:
            return resolve_type(name, stack)
        if name in raw_selects:
            return resolve_select(name, stack)
        if name in raw_setlike:
            return resolve_setlike(name, stack)
        raise ValueError("unknown type name %r: rules name declared "
                         "`type`/`select`/`type_set` records" % name)

    def resolve_select(name, stack=()):
        if name in select_types:
            return select_types[name].value
        if name in stack:
            raise ValueError("cyclic select reference: %s" % " -> ".join(stack + (name,)))
        (arms, otherwise), ln = raw_selects[name]
        out_arms = []
        for cond_name, type_name in arms:
            if cond_name in features:
                cond = {"kind": "leaf", "name": "hasFeature",
                        "args": [features[cond_name].cxx]}
            elif cond_name in pred_src:
                cond = resolve_pred(cond_name)
            else:
                raise ValueError(f"line {ln}: unknown select guard {cond_name!r}")
            out_arms.append((cond, resolve_name(type_name, stack + (name,))))
        value = SelectValue(tuple(out_arms), resolve_name(otherwise, stack + (name,)),
                            legacy_guard=True)
        select_types[name] = SelectType(name, arms, otherwise, value, ln)
        return value

    def resolve_setlike(name, stack=()):
        if name in setlike:
            return setlike[name].value
        if name in stack:
            raise ValueError("cyclic type-set reference: %s" % " -> ".join(stack + (name,)))
        kind, payload, ln = raw_setlike[name]
        if kind == "type_set" and isinstance(payload, tuple) and payload[0] == "ref":
            ref = payload[1]
            base = resolve_setlike(ref, stack + (name,))
            members = ()
            source_ref = ref
        else:
            members = tuple(payload)
            source_ref = None
            base = None
        if base is None:
            elems = tuple(resolve_name(m, stack + (name,)) for m in members)
            value = SetValue("Type", 1, elems)
        else:
            value = base
        if kind == "type_set":
            setlike[name] = TypeSet(name, members, source_ref, value, ln)
        else:
            setlike[name] = TypeList(name, members, value, ln)
        return value

    # Resolve in source order.  The helpers memoize, so forward references
    # are resolved on demand and cycles are rejected.
    decls: list[Decl] = []
    for kind, name, payload, source, ln in raw_decls:
        if kind == "feature":
            decls.append(features[name])
        elif kind == "pred":
            resolve_pred(name)
            decls.append(preds[name])
        elif kind == "type":
            resolve_type(name)
            decls.append(named_types[name])
        elif kind == "select":
            resolve_select(name)
            decls.append(select_types[name])
        elif kind in ("type_set", "type_list"):
            resolve_setlike(name)
            decls.append(setlike[name])
        else:
            raise AssertionError(kind)

    rulesets: list[RuleSet] = []
    for name, opcodes, comments, coverage, ln, compiled in raw_rulesets:
        rules = []
        for r in compiled:
            rules.append(Rule(
                op=r["op"], action=r["action"], type_idx=r["type_idx"],
                on=_convert_node(r.get("on"), resolve_name),
                to=_convert_node(r.get("to"), resolve_name),
                predicate=_convert_node(r["predicate"], resolve_name),
                line=r.get("_line", ln)))
        rulesets.append(RuleSet(name, opcodes, rules, comments, coverage, ln))

    return Program(includes, decls, rulesets, features, preds, named_types,
                   select_types, setlike)


def undeclared_features(program: Program) -> list[tuple[int, str, str]]:
    """[(line, ruleset, expr)] for every feature() with no declaration."""
    declared = {d.cxx for d in program.decls if isinstance(d, Feature)}
    out = []

    def walk(node, line, ruleset):
        if isinstance(node, dict):
            if node.get("kind") == "leaf" and node.get("name") == "hasFeature":
                expr = node.get("args", [None])[0]
                if expr not in declared:
                    out.append((line, ruleset, expr))
            for value in node.values():
                walk(value, line, ruleset)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value, line, ruleset)

    for rs in program.rulesets:
        for rule in rs.rules:
            walk(rule.predicate, rule.line, rs.name)
            walk(rule.on, rule.line, rs.name)
            walk(rule.to, rule.line, rs.name)
    return out


# ---- renderer-local names ------------------------------------------------

class NameTable:
    """Semantic value -> the target's spelling, computed at the renderer exit.

    This is the replacement for the old global ``td.build_names``.  It is
    deliberately built by the .td/.inc renderers only; core/check/table never
    see record names.
    """

    def __init__(self, program: Program):
        self.feature: dict[str, str] = {}
        self.type: dict[LLT, str] = {}
        self.select: dict[tuple, str] = {}
        self.set_all: dict[tuple, str] = {}
        self.set_td: dict[tuple, str] = {}
        self.records: set[str] = set()
        for d in program.decls:
            self.records.add(d.name)
            if isinstance(d, Feature):
                self.feature[d.cxx] = d.name
            elif isinstance(d, NamedType):
                self.type[d.llt] = d.name
            elif isinstance(d, SelectType):
                self.select[value_key(d.value)] = d.name
            elif isinstance(d, TypeSet):
                key = value_key(d.value)
                self.set_all[key] = d.name
                if all(isinstance(e, (Scalar, Integer, Float, BFloat16,
                                      Pointer, Vector)) for e in d.value.elems):
                    self.set_td[tuple(value_key(e) for e in d.value.elems)] = d.name
            elif isinstance(d, TypeList):
                self.set_all[value_key(d.value)] = d.name

    def value_name(self, v: TypeValue) -> str:
        if isinstance(v, str):
            raise ValueError("unknown type name %r: rules name declared "
                             "`type`/`select`/`type_set` records, not LLT "
                             "literals" % v)
        if isinstance(v, SetValue):
            name = self.set_all.get(value_key(v))
            if name is not None:
                return name
            raise ValueError("no declared type set for %r" % (v,))
        if isinstance(v, SelectValue):
            name = self.select.get(value_key(v))
            if name is not None:
                return name
            raise ValueError("no declared select type for %r" % (v,))
        name = self.type.get(v)
        if name is None:
            raise ValueError("no declared type for %r" % (llt_text(v),))
        return name

    def set_name_td(self, members) -> str | None:
        return self.set_td.get(tuple(value_key(e) for e in members))

    def feature_name(self, cxx: str) -> str:
        return self.feature[cxx]

    # Legacy-shaped rule view for the .td/.inc renderers only.  The type
    # positions are named here; this is the exit computation, not a model.
    def rule_view(self, rule: Rule, legacy_dag: bool = False) -> dict:
        out = {"action": rule.action, "type_idx": rule.type_idx,
               "op": rule.op,
               "predicate": self.node_view(rule.predicate),
               "_line": rule.line}
        if rule.on is not None:
            out["on"] = self.node_view(rule.on)
        if rule.to is not None:
            out["to"] = self.node_view(rule.to)
        return out

    def node_view(self, node):
        if isinstance(node, list):
            return [self.node_view(v) for v in node]
        if not isinstance(node, dict):
            return node
        k = node.get("kind")
        if k == "type":
            v = node["value"]
            if isinstance(v, str):
                # An undeclared spelling (the old front end kept it verbatim
                # so lint/gen could name it).  The adapter preserves it too.
                return {"kind": "type", "value": v}
            if isinstance(v, SelectValue):
                name = self.select.get(value_key(v))
                if name is not None:
                    return {"kind": "type", "value": name}
                return {"kind": "type", "value": self.select_view(v)}
            return {"kind": "type", "value": self.value_name(v)}
        if k == "set":
            out = dict(node)
            if node.get("of", "Type") == "Type":
                rows = []
                for e in node.get("elems", []):
                    if isinstance(e, list):
                        if len(e) == 4 and isinstance(e[3], int):
                            rows.append([self.value_name(x) for x in e[:3]] + [e[3]])
                        else:
                            rows.append([self.value_name(x) for x in e])
                    elif isinstance(e, str):
                        rows.append(e)
                    else:
                        rows.append(self.value_name(e))
                out["elems"] = rows
            return out
        return {key: self.node_view(v) for key, v in node.items()}

    def select_view(self, value: SelectValue):
        expr = self.value_name(value.otherwise)
        for cond, then in reversed(value.arms):
            expr = {"select": {"cond": cond, "then": self.value_name(then),
                               "else": expr}}
        return expr


# ---- Phase-1 compatibility adapter ---------------------------------------

def _select_decl_payload(d: SelectType):
    return (list(x[0] for x in d.arms), list(x[1] for x in d.arms), d.otherwise)


def to_record_model(program: Program) -> dict:
    """Downgrade a Program to the pre-AST record dict (tests/oracle only)."""
    names = NameTable(program)
    includes = ['include "%s"' % inc.path for inc in program.includes]
    decls = []
    for d in program.decls:
        if isinstance(d, Feature):
            decls.append(("feature", d.name, d.cxx))
        elif isinstance(d, PredicateDecl):
            decls.append(("pred", d.name, d.source))
        elif isinstance(d, NamedType):
            decls.append(("type", d.name, d.source))
        elif isinstance(d, SelectType):
            decls.append(("select", d.name, _select_decl_payload(d)))
        elif isinstance(d, TypeSet):
            payload = ("ref", d.source_ref) if d.source_ref else list(d.members)
            decls.append(("type_set", d.name, payload))
        elif isinstance(d, TypeList):
            decls.append(("type_list", d.name, list(d.members)))
        else:
            raise AssertionError(d)

    rulesets = []
    for rs in program.rulesets:
        rulesets.append({
            "def": rs.name, "opcodes": list(rs.opcodes),
            "comments": list(rs.comments), "legacy": list(rs.coverage),
            "rules": [names.rule_view(r) for r in rs.rules],
        })
    return {"includes": includes, "decls": decls, "rulesets": rulesets}


# ---- AST-level canonicalisation ------------------------------------------

def canonicalize_rulesets(rulesets: list[RuleSet]) -> list[RuleSet]:
    """One rule set per opcode: a medium constraint, not a language rule.

    A ``LegalizeRuleSet`` record is ``(opcodes, rules)`` and llvm-tblgen
    rejects an opcode covered twice.  The C++ builder, by contrast, appends a
    table per call and takes the first match.  Concatenating an opcode's
    tables in document order preserves that answer.

    This is exactly the transform the record model performed, including two
    details that look accidental but are part of the artifact contract: the
    rule key contains the source line (two textually identical rules written
    on different lines stay in different groups), and the copied metadata
    (comments / ImmIdx coverage) comes from the last source block.  Keep both
    until the corpus can be regenerated as a whole.
    """
    seen = {}
    for rs in rulesets:
        for op in rs.opcodes:
            seen[op] = seen.get(op, 0) + 1
    if all(n == 1 for n in seen.values()):
        # Nothing to consolidate; keep the artifact byte-identical.
        return list(rulesets)
    seq, first = {}, {}
    for rs in rulesets:
        for op in rs.opcodes:
            first.setdefault(op, rs.name)
            seq.setdefault(op, []).extend(rs.rules)
    last = rulesets[-1]
    groups, order = {}, []
    for op, rules in seq.items():
        key = json.dumps([_rule_key(r) for r in rules], sort_keys=True)
        if key not in groups:
            groups[key] = RuleSet(first[op], [], list(rules),
                                  list(last.comments), sorted(last.coverage),
                                  last.line)
            order.append(key)
        g = groups[key]
        g.opcodes.append(op)
        g.coverage = sorted(set(g.coverage) | set(last.coverage))
    out, used = [], set()
    for key in order:
        g = groups[key]
        name, n = g.name, 2
        while name in used:
            name = "%s_%d" % (g.name, n)
            n += 1
        used.add(name)
        g.name = name
        out.append(g)
    return out


def _rule_key(rule: Rule):
    """Structural identity of one rule, matching the old JSON rule key.

    The old key serialised the record-shaped rule, `_line` included.  The
    semantic fields are the same; the line is kept because it is how the old
    transform distinguished otherwise identical rules from different blocks.
    """
    def freeze(x):
        if isinstance(x, dict):
            return {k: freeze(v) for k, v in x.items()}
        if isinstance(x, list):
            return [freeze(v) for v in x]
        if isinstance(x, tuple):
            return [freeze(v) for v in x]
        if isinstance(x, (Scalar, Integer, Float, BFloat16, Pointer, Vector)):
            return llt_text(x)
        if isinstance(x, SelectValue):
            return {"select": [(freeze(p), freeze(t)) for p, t in x.arms],
                    "else": freeze(x.otherwise),
                    "legacy_guard": x.legacy_guard}
        if isinstance(x, SetValue):
            return {"set": x.of, "arity": x.arity,
                    "elems": freeze(list(x.elems))}
        return x
    return {"op": rule.op, "action": rule.action, "type_idx": rule.type_idx,
            "on": freeze(rule.on), "to": freeze(rule.to),
            "predicate": freeze(rule.predicate), "_line": rule.line}
