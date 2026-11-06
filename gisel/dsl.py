#!/usr/bin/env python3
"""Spike: a free-form (C/Python-style) DSL for the GlobalISel legalizer core IR.

The point is not to add a second IR.  The DSL is *sugar over the existing
schema-0.4 normal form*: it parses statement/infix syntax and (a) compiles it to the same
schema-0.4 normal form `llvm-tblgen -gen-legalizer-core` emits, and (b) emits
a self-contained core-IR `.td` file that the existing backends consume, so both
paths can be diffed field-by-field after stripping the per-rule bookkeeping
keys (origin / rule_index / ruleset / schema / def).

Subset supported here (enough to re-derive real X86/AArch64 rules):
    rule <opcode>+ :
        <stmt>
        ...
    stmt := legal|lower|custom|unsupported|libcall <pred>
          | widen|narrow|more|fewer|bitcast ( <expr> , <expr> ) [ when <pred> ]
          | scalarize ( <expr> ) [ when <pred> ]
          | clamp_min ( INT , TYPE , <expr> )
          | clamp_max ( INT , TYPE , <expr> )        # lanes: int or select(...)
    pred := or of ( and of ( not | primary ) )
    primary := true | ( pred ) | feature ( STR ) | in ( expr , [TYPE,...] | TYPE )
            | expr ( ==|!=|<|<=|>|>= ) expr
    expr  := INT | TYPE | KIND | call ( ... )

Static checks: J1 sort, J2b comparison sorts, J3a action table, J3b slot
bounds (arity imported from GenericOpcodes.td via build_arity_manifest).
             | select ( <expr> , <expr> , <expr> )        # int select
             | select_type ( <expr> , TYPE , TYPE )       # type select (in ty(...))
"""

import json
import os
import re
import subprocess
import sys
import tempfile

# ---- normal-form node builders (schema 0.4) -------------------------------

def _node(kind, **extra):
    d = {"kind": kind}
    d.update(extra)
    return d

def slot(i):      return _node("slot", index=i)
def int_(v):      return _node("int", value=v)
def type_(v):     return _node("type", value=v)
def kind_(name):  return _node(name)
def leaf(name, args): return _node("leaf", name=name, args=args)
def call1(k, a):  return _node(k, args=[a])
def call2(k, a, b): return _node(k, args=[a, b])
def op1(k):       return _node(k)          # zero-arg constructor, e.g. pow2

KIND_TAGS = {"vector": "kindVector", "scalable_vector": "kindScalableVector",
             "scalar": "kindScalar", "pointer": "kindPointer",
             "pointer_vector": "kindPointerVector"}
ORDERING_TAGS = {"ordering_unordered": "orderingUnordered",
                 "ordering_monotonic": "orderingMonotonic",
                 "ordering_acquire": "orderingAcquire",
                 "ordering_release": "orderingRelease",
                 "ordering_acquire_release": "orderingAcquireRelease",
                 "ordering_sequentially_consistent": "orderingSequentiallyConsistent"}
ZERO_ARG = dict(KIND_TAGS, **ORDERING_TAGS)
ZERO_ARG["pow2"] = "pow2"

UNARY_CALL = {"elem_of": "elemOf", "scalar_of": "scalarOf", "sort_of": "sortOf",
              "num_elems": "numElems", "bits_of": "bitsOf", "size_of": "sizeOf",
              "size_in_bytes_of": "sizeInBytesOf", "is_byte_sized": "isByteSized",
              "addr_space": "addrSpace", "align_of": "alignOf",
              "mem_slot": "memSlot", "mem_ty": "memTy", "mem_ordering": "memOrdering",
              "mem_failure_ordering": "memFailureOrdering",
              "is_bfloat16": "isBFloat16", "is_float16": "isFloat16",
              "is_pow2": "isPow2", "replace": "replace", "pow2_ceil": "pow2Ceil",
              "multiple_of": "multipleOf", "same_as": "sameAs",
              "min_vector_size": "minVectorSize", "int_of_size": "intOfSize",
              "ty": "ty", "pow2_min": "pow2Min"}
BINARY_CALL = {"vec_of": "vecOf", "scalar_or_vec_of": "scalarOrVecOf",
               "elt_type_to": "eltTypeTo", "elt_size_to": "eltSizeTo",
               "div_lanes": "divLanes", "mul": "mul", "urem": "urem",
               "udiv": "udiv", "clamp": "clamp"}

# A canonical type literal: scalar (s8/i32/f16/bf16), pointer (p0:64/p0:*),
# fixed vector (v16s8, v2p0:*) or scalable vector (nxv16i8).
TYPE_TOKEN_RE = re.compile(
    r"(?:(?:nx)?v\d+)?(?:s\d+|i\d+|f\d+|bf16|p\d+:\d+|p\d+:\*)")

# ---- tokenizer ------------------------------------------------------------

class Tok:
    __slots__ = ("t", "v", "line")
    def __init__(self, t, v, line):
        self.t, self.v, self.line = t, v, line

def tokenize(text):
    toks = []
    lines = text.splitlines()
    # indentation -> INDENT/DEDENT, Python-style
    stack = [0]
    for ln, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent > stack[-1]:
            stack.append(indent); toks.append(Tok("INDENT", None, ln))
        while indent < stack[-1]:
            stack.pop(); toks.append(Tok("DEDENT", None, ln))
        i = 0
        line = raw.strip()
        n = len(line)
        while i < n:
            c = line[i]
            if c.isspace():
                i += 1; continue
            if line.startswith(("==", "!=", "<=", ">="), i):
                toks.append(Tok("OP", line[i:i+2], ln)); i += 2; continue
            if c in "<>":
                toks.append(Tok("OP", c, ln)); i += 1; continue
            if c in "(),[]:":
                toks.append(Tok(c, c, ln)); i += 1; continue
            if c == '"':
                j = i + 1
                while j < n and line[j] != '"':
                    j += 1
                toks.append(Tok("STR", line[i+1:j], ln)); i = j + 1; continue
            if c.isdigit():
                j = i
                while j < n and line[j].isdigit():
                    j += 1
                toks.append(Tok("INT", int(line[i:j]), ln)); i = j; continue
            if c.isalpha():
                m = TYPE_TOKEN_RE.match(line, i)
                if m and (m.end() == n or not (line[m.end()].isalnum()
                                               or line[m.end()] == "_")):
                    toks.append(Tok("TYPE", m.group(), ln)); i = m.end(); continue
            if c.isalpha() or c == "_":
                j = i
                while j < n and (line[j].isalnum() or line[j] == "_"):
                    j += 1
                toks.append(Tok("ID", line[i:j], ln)); i = j; continue
            raise ValueError(f"line {ln}: bad char {c!r}")
        toks.append(Tok("NEWLINE", None, ln))
    while len(stack) > 1:
        stack.pop(); toks.append(Tok("DEDENT", None, None))
    toks.append(Tok("EOF", None, None))
    return toks

# ---- parser ---------------------------------------------------------------

class Parser:
    def __init__(self, text):
        self.toks = tokenize(text)
        self.p = 0

    def peek(self, t=None):
        tok = self.toks[self.p]
        if t is None or tok.t == t:
            return tok
        return None

    def next(self):
        tok = self.toks[self.p]
        self.p += 1
        return tok

    def expect(self, t):
        tok = self.next()
        if tok.t != t:
            raise ValueError(f"line {tok.line}: expected {t}, got {tok.t} ({tok.v!r})")
        return tok

    def parse(self):
        out = []
        while self.peek() and self.peek().t == "ID" and self.peek().v == "rule":
            out.append(self.parse_ruleset())
        return out

    def parse_ruleset(self):
        self.expect("ID")  # 'rule'
        opcodes = []
        while self.peek() and self.peek().t == "ID":
            opcodes.append(self.next().v)
        self.expect(":")
        self.expect("NEWLINE")
        self.expect("INDENT")
        stmts = []
        while self.peek() and self.peek().t != "DEDENT" and self.peek().t != "EOF":
            stmts.append(self.parse_stmt())
            self.expect("NEWLINE")
        self.expect("DEDENT")
        return {"opcodes": opcodes, "stmts": stmts}

    def parse_stmt(self):
        kw = self.next()
        assert kw.t == "ID", kw
        k = kw.v
        if k in ("legal", "lower", "custom", "unsupported", "libcall"):
            pred = self.parse_pred()
            return {"op": k, "pred": pred}
        if k in ("widen", "narrow", "more", "fewer", "bitcast"):
            self.expect("(")
            on = self.parse_expr()
            self.expect(",")
            to = self.parse_expr()
            self.expect(")")
            pred = None
            if self.peek() and self.peek().t == "ID" and self.peek().v == "when":
                self.next(); pred = self.parse_pred()
            return {"op": k, "on": on, "to": to, "pred": pred}
        if k == "scalarize":
            self.expect("(")
            on = self.parse_expr()
            self.expect(")")
            pred = None
            if self.peek() and self.peek().t == "ID" and self.peek().v == "when":
                self.next(); pred = self.parse_pred()
            return {"op": k, "on": on, "to": None, "pred": pred}
        if k in ("clamp_min", "clamp_max"):
            self.expect("(")
            idx = self.next().v; self.expect(",")
            elt = self.next().v; self.expect(",")
            lanes = self.parse_expr()
            self.expect(")")
            return {"op": k, "idx": idx, "elt": elt, "lanes": lanes}
        raise ValueError(f"line {kw.line}: unknown statement {k!r}")

    # predicate grammar: or -> and -> not -> primary
    def parse_pred(self):
        # or -> and -> not -> primary; n-ary (flat), matching CoreAny/CoreAll
        args = [self.parse_and()]
        while self.peek() and self.peek().t == "ID" and self.peek().v == "or":
            self.next(); args.append(self.parse_and())
        return args[0] if len(args) == 1 else _node("any", args=args)

    def parse_and(self):
        args = [self.parse_not()]
        while self.peek() and self.peek().t == "ID" and self.peek().v == "and":
            self.next(); args.append(self.parse_not())
        return args[0] if len(args) == 1 else _node("all", args=args)

    def parse_not(self):
        if self.peek() and self.peek().t == "ID" and self.peek().v == "not":
            self.next()
            return call1("not", self.parse_not())
        return self.parse_primary()

    def parse_primary(self):
        if self.peek() and self.peek().t == "ID" and self.peek().v == "true":
            self.next(); return leaf("true", [])
        if self.peek("("):
            self.next(); p = self.parse_pred(); self.expect(")"); return p
        if self.peek() and self.peek().t == "ID" and self.peek().v == "feature":
            self.next(); self.expect("("); st = self.next().v; self.expect(")")
            return leaf("hasFeature", [st])
        # explicit n-ary combinators (all_of/any_of) for arity-1 and readability
        if self.peek() and self.peek().t == "ID" and self.peek().v in (
                "in", "in_pairs", "in_triples", "in_mem_desc"):
            return self.parse_membership()
        if self.peek() and self.peek().t == "ID" and self.peek().v in (
                "all_of", "any_of"):
            return self.parse_combinator()
        # Bool-returning observers can stand alone as a predicate primary
        if self.peek() and self.peek().t == "ID" and self.peek().v in (
                "is_bfloat16", "is_float16", "is_byte_sized", "is_pow2"):
            return self.parse_expr()
        # comparison
        left = self.parse_expr()
        tok = self.next()
        assert tok.t == "OP", f"line {tok.line}: expected comparison, got {tok.v!r}"
        right = self.parse_expr()
        return call2({"==": "eq", "!=": "ne", "<": "lt", "<=": "le",
                      ">": "gt", ">=": "ge"}[tok.v], left, right)

    def parse_combinator(self):
        name = self.next().v
        self.expect("(")
        args = []
        while True:
            args.append(self.parse_pred())
            if not self.peek(","):
                break
            self.next()
        self.expect(")")
        return _node("all" if name == "all_of" else "any", args=args)

    def parse_membership(self):
        name = self.next().v
        self.expect("(")
        a = self.parse_expr()
        self.expect(",")
        if name == "in":
            rhs = self.parse_set_or_type()
            self.expect(")")
            return call2("in", a, rhs)
        b = self.parse_expr()
        self.expect(",")
        if name == "in_pairs":
            st = self.parse_set()
            self.expect(")")
            return _node("inPairs", args=[a, b, st])
        c = self.parse_expr()
        self.expect(",")
        st = self.parse_set()
        self.expect(")")
        if name == "in_triples":
            return _node("inTriples", args=[a, b, c, st])
        return _node("inMemDesc", args=[a, b, c, st])

    def parse_set_or_type(self):
        if self.peek("["):
            return self.parse_set()
        return type_(self.parse_type_value())

    def parse_set(self):
        self.expect("[")
        if self.peek("["):
            rows = []
            while True:
                self.expect("[")
                row = []
                while True:
                    row.append(self.parse_type_value())
                    if not self.peek(","):
                        break
                    self.next()
                self.expect("]")
                rows.append(row)
                if not self.peek(","):
                    break
                self.next()
            self.expect("]")
            return _node("set", of="Type", arity=len(rows[0]), elems=rows)
        if self.peek().t == "ID" and self.peek().v == "mem_desc":
            rows = []
            while True:
                self.next()  # mem_desc
                self.expect("(")
                t0 = self.parse_type_value(); self.expect(",")
                t1 = self.parse_type_value(); self.expect(",")
                t2 = self.parse_type_value(); self.expect(",")
                al = self.next().v; self.expect(")")
                rows.append([t0, t1, t2, al])
                if not self.peek(","):
                    break
                self.next()
            self.expect("]")
            return _node("set", of="Type", arity=2, elems=rows)
        elems = []
        while True:
            elems.append(self.parse_type_value())
            if not self.peek(","):
                break
            self.next()
        self.expect("]")
        if len(elems) == 1:
            return type_(elems[0])
        return _node("set", of="Type", elems=elems)

    def parse_type_value(self):
        if self.peek().t == "TYPE":
            return self.next().v
        if self.peek().t == "ID" and self.peek().v == "select_type":
            return self.parse_select_type()
        if self.peek().t == "ID" and self.peek().v[:1].isupper():
            # A named record from the target's scaffolding (a LegalizeNamedType,
            # LegalizeSelectType or LegalizeCoreTypeSet).  The .gisel source
            # spells these by name; the generator keeps the name in the .td.
            return self.next().v
        raise ValueError(f"line {self.peek().line}: expected a type, got "
                         f"{self.peek().t} {self.peek().v!r}")

    def parse_select_type(self):
        self.next()  # select_type
        self.expect("(")
        cond = self.parse_pred()
        self.expect(",")
        then = self.parse_type_value()
        self.expect(",")
        els = self.parse_type_value()
        self.expect(")")
        return {"select": {"cond": cond, "then": then, "else": els}}

    def parse_expr(self):
        tok = self.peek()
        if tok.t == "INT":
            self.next(); return int_(tok.v)
        if tok.t == "TYPE":
            self.next(); return type_(tok.v)
        if tok.t == "ID" and tok.v[:1].isupper():
            self.next(); return type_(tok.v)
        if tok.t == "ID":
            v = tok.v
            if v in ZERO_ARG:
                self.next(); return kind_(ZERO_ARG[v])
            return self.parse_call()
        raise ValueError(f"line {tok.line}: expected expr, got {tok.t} {tok.v!r}")

    def parse_call(self):
        name = self.next().v
        self.expect("(")
        if name == "feature":
            st = self.next().v
            self.expect(")")
            return leaf("hasFeature", [st])
        if name == "select":
            cond = self.parse_pred(); self.expect(",")
            a = self.parse_expr(); self.expect(",")
            b = self.parse_expr(); self.expect(")")
            return _node("select", args=[cond, a, b])
        if name == "select_type":
            cond = self.parse_pred(); self.expect(",")
            t = self.parse_type_value(); self.expect(",")
            e = self.parse_type_value(); self.expect(")")
            return type_({"select": {"cond": cond, "then": t, "else": e}})
        if name == "slot":
            i = self.next().v
            self.expect(")")
            return slot(i)
        args = []
        if not self.peek(")"):
            while True:
                args.append(self.parse_expr())
                if not self.peek(","):
                    break
                self.next()
        self.expect(")")
        if name in UNARY_CALL:
            assert len(args) == 1, (name, args)
            return call1(UNARY_CALL[name], args[0])
        if name in BINARY_CALL:
            assert len(args) == 2, (name, args)
            return call2(BINARY_CALL[name], args[0], args[1])
        raise ValueError(f"line {self.toks[self.p-2].line}: unknown constructor "
                         f"{name!r}")

# ---- compiler: AST -> normal form ----------------------------------------

def compile_rulesets(ast):
    """Return list of rule dicts in schema-0.4 normal form (semantic fields)."""
    out = []
    for rs in ast:
        for st in rs["stmts"]:
            out.append(compile_stmt(st))
    return out

def type_idx_of(on):
    """The type slot a rule mutates, from its observation (coreTypeIdxOf)."""
    if on["kind"] == "slot":
        return on["index"]
    if on["kind"] == "elemOf":
        return type_idx_of(on["args"][0])
    if on["kind"] == "int":
        return on["value"]
    return 0


def compile_stmt(st):
    op = st["op"]
    pred = st.get("pred")
    if op in ("legal", "lower", "custom", "unsupported", "libcall"):
        action = {"legal": "Legal", "lower": "Lower", "custom": "Custom",
                  "unsupported": "Unsupported", "libcall": "Libcall"}[op]
        return {"action": action, "type_idx": 0, "op": op,
                "predicate": pred if pred is not None else leaf("true", [])}
    if op in ("widen", "narrow", "more", "fewer", "bitcast"):
        action = {"widen": "WidenScalar", "narrow": "NarrowScalar",
                  "more": "MoreElements", "fewer": "FewerElements",
                  "bitcast": "Bitcast"}[op]
        return {"action": action, "type_idx": type_idx_of(st["on"]), "op": op,
                "on": st["on"], "to": st["to"],
                "predicate": pred if pred is not None else leaf("true", [])}
    if op == "scalarize":
        return {"action": "FewerElements", "type_idx": type_idx_of(st["on"]),
                "op": "scalarize", "on": st["on"],
                "predicate": pred if pred is not None else leaf("true", [])}
    if op in ("clamp_min", "clamp_max"):
        idx, elt, lanes = st["idx"], st["elt"], st["lanes"]
        if op == "clamp_min":
            to = call1("replace", call2("vecOf", lanes, call1("elemOf", slot(idx))))
            cmp = call2("lt", call1("numElems", slot(idx)), lanes)
            action = "MoreElements"; opname = "more"
        else:
            to = call1("replace", call2("scalarOrVecOf", lanes, call1("elemOf", slot(idx))))
            cmp = call2("gt", call1("numElems", slot(idx)), lanes)
            action = "FewerElements"; opname = "fewer"
        fixed = [
            call2("eq", call1("sortOf", slot(idx)), kind_("kindVector")),
            call1("not", call2("eq", call1("sortOf", slot(idx)), kind_("kindScalableVector"))),
            call2("eq", call1("elemOf", slot(idx)), call1("ty", type_(elt))),
            cmp,
        ]
        guard = _node("all", args=fixed)
        return {"action": action, "type_idx": int(idx), "op": opname,
                "on": slot(idx), "to": to, "predicate": guard}
    raise ValueError(f"unknown stmt {op!r}")

# ---- compare against real -gen-legalizer-core output ----------------------

STRIP_KEYS = {"schema", "ruleset", "rule_index", "origin", "def"}

def strip(rule):
    return {k: v for k, v in rule.items() if k not in STRIP_KEYS}

def _llt_leaf(name):
    """A non-vector canonical type name -> the LLT expression a
    LegalizeNamedType carries.  This is the direct inverse of
    normalizeLlt() in LegalizerInfoEmitter.cpp: any expression that
    normalizes back to `name` is faithful."""
    if re.fullmatch(r"s\d+", name):
        return f"LLT::scalar({name[1:]})"
    if re.fullmatch(r"i\d+", name):
        return f"LLT::integer({name[1:]})"
    kinds = {"f16": "float16", "f32": "float32", "f64": "float64",
             "f128": "float128", "bf16": "bfloat16"}
    if name in kinds:
        return f"LLT::{kinds[name]}()"
    m = re.fullmatch(r"p(\d+):(\d+)", name)
    if m:
        return f"LLT::pointer({m.group(1)}, {m.group(2)})"
    m = re.fullmatch(r"p(\d+):\*", name)
    if m:
        # A target-config-dependent pointer width.  normalizeLlt maps any
        # non-digit size back to `pN:*`, so this round-trips even though the
        # original expression was target-specific.
        return f"LLT::pointer({m.group(1)}, 0 ? 64 : 32)"
    raise ValueError(f"unsupported type name {name!r}")


def _llt(name):
    """Canonical type name -> LLT string, vectors included."""
    m = re.fullmatch(r"((?:nx)?v)(\d+)(.+)", name)
    if m:
        head = ("LLT::scalable_vector" if m.group(1) == "nxv"
                else "LLT::fixed_vector")
        return f"{head}({m.group(2)}, {_llt_leaf(m.group(3))})"
    return _llt_leaf(name)


class TdEmitter:
    """Emit a self-contained core-IR .td file from schema-0.4 normal form.

    Covers the whole vocabulary the X86/AArch64 corpora exercise, including the
    tuple/memdesc membership sets and the legacy `nary` predicate-dag that a
    LegalizeSelectType cond can still carry (predicateJson's escape path).
    """

    _OPS = {"legal": "CoreLegal", "lower": "CoreLower", "custom": "CoreCustom",
            "unsupported": "CoreUnsupported", "libcall": "CoreLibcall"}
    _ALWAYS = {"legal": "CoreAlwaysLegal", "lower": "CoreAlwaysLower",
               "custom": "CoreAlwaysCustom",
               "unsupported": "CoreAlwaysUnsupported",
               "libcall": "CoreAlwaysLibcall"}
    _LATTICE = {"widen": "CoreWiden", "narrow": "CoreNarrow", "more": "CoreMore",
                "fewer": "CoreFewer", "bitcast": "CoreBitcast"}
    _KIND = {"kindVector": "KindVector", "kindScalableVector": "KindScalableVector",
             "kindScalar": "KindScalar", "kindPointer": "KindPointer",
             "kindPointerVector": "KindPointerVector"}
    _ORDERING = {"orderingUnordered": "OrderingUnordered",
                 "orderingMonotonic": "OrderingMonotonic",
                 "orderingAcquire": "OrderingAcquire",
                 "orderingRelease": "OrderingRelease",
                 "orderingAcquireRelease": "OrderingAcquireRelease",
                 "orderingSequentiallyConsistent": "OrderingSequentiallyConsistent"}
    _CMP = {"eq": "CoreEq", "ne": "CoreNe", "lt": "CoreLt", "le": "CoreLe",
            "gt": "CoreGt", "ge": "CoreGe"}
    _UNARY = {"elemOf": "ElemOf", "scalarOf": "ScalarOf", "sortOf": "SortOf",
              "numElems": "NumElems", "bitsOf": "BitsOf", "sizeOf": "SizeOf",
              "sizeInBytesOf": "SizeInBytesOf", "isByteSized": "IsByteSized",
              "addrSpace": "AddrSpace", "alignOf": "AlignOf",
              "memSlot": "MemSlot", "memTy": "MemTy", "memOrdering": "MemOrdering",
              "memFailureOrdering": "MemFailureOrdering",
              "isBFloat16": "IsBFloat16", "isFloat16": "IsFloat16",
              "isPow2": "CoreIsPow2", "replace": "Replace",
              "pow2Ceil": "Pow2Ceil", "multipleOf": "MultipleOf",
              "sameAs": "SameAs", "minVectorSize": "MinVectorSize",
              "intOfSize": "IntOfSize"}
    _BINARY = {"eltTypeTo": "EltTypeTo", "eltSizeTo": "EltSizeTo",
               "divLanes": "DivLanes", "mul": "CoreMul", "urem": "CoreURem",
               "udiv": "CoreUDiv"}

    def __init__(self, rulesets):
        # rulesets: [{"def": str, "opcodes": [str], "rules": [rule, ...]}, ...]
        self.rulesets = rulesets
        self.features = {}   # cond string -> record name
        self.pred_dags = {}  # reconstructed dag text -> record name
        self.types = {}      # canonical type name -> record name
        self.selects = {}    # (cond, then, else) -> record name (children first)

    def _feat(self, s):
        if s not in self.features:
            self.features[s] = f"F_{len(self.features)}"
        return self.features[s]

    def _type(self, name):
        if name not in self.types:
            self.types[name] = f"T_{len(self.types)}"
        return self.types[name]

    def _type_value(self, v):
        """A type value (str or nested select dict) -> a record name."""
        if isinstance(v, str):
            return self._type(v)
        sel = v["select"]
        cond = self._select_cond(sel["cond"])
        then = self._type_value(sel["then"])
        els = self._type_value(sel["else"])
        key = (cond, then, els)
        if key not in self.selects:
            self.selects[key] = f"ST_{len(self.selects)}"
        return self.selects[key]

    def _select_cond(self, cond):
        """A select-type guard -> a LegalizeBoolPredicate record name."""
        k = cond["kind"]
        if k == "leaf" and cond["name"] == "hasFeature":
            return self._feat(cond["args"][0])
        if k == "nary":
            return self._pred_dag(cond)
        raise ValueError(f"unsupported select cond {cond!r}")

    def _pred_dag(self, node):
        text = self._pred_dag_text(node)
        if text not in self.pred_dags:
            self.pred_dags[text] = f"PD_{len(self.pred_dags)}"
        return self.pred_dags[text]

    def _pred_dag_text(self, node):
        k = node["kind"]
        if k == "leaf" and node["name"] == "hasFeature":
            return self._feat(node["args"][0])
        if k == "nary":
            return (f"({node['op']} "
                    + ", ".join(self._pred_dag_text(a) for a in node["args"])
                    + ")")
        if k == "not":
            # legacy singular form used by the nary escape path
            return f"(not {self._pred_dag_text(node['arg'])})"
        raise ValueError(f"unsupported predicate-dag node {node!r}")

    def _set(self, n):
        arity = n.get("arity", 1)
        elems = n["elems"]
        if not elems:
            raise ValueError("empty set literal")
        if arity == 1:
            return "[" + ", ".join(self._type_value(e) for e in elems) + "]"
        # memdesc: {Type0, Type1, MemTy, Align}; arity counts the type slots (2).
        if arity == 2 and len(elems[0]) == 4:
            return ("[" + ", ".join(
                f"LegalizeMemDesc<{self._type_value(e[0])}, {self._type_value(e[1])}, "
                f"{self._type_value(e[2])}, {e[3]}>" for e in elems) + "]")
        # pair (arity 2) or triple (arity 3): a list of lists
        return ("[" + ", ".join(
            "[" + ", ".join(self._type_value(x) for x in e) + "]" for e in elems) + "]")

    def dag(self, n):
        k = n["kind"]
        if k == "int":
            return str(n["value"])
        if k == "slot":
            return f"(Slot {n['index']})"
        if k == "type":
            return self._type_value(n["value"])
        if k in self._KIND:
            return self._KIND[k]
        if k in self._ORDERING:
            return self._ORDERING[k]
        if k == "leaf":
            if n["name"] == "true":
                return "(CoreTrue)"
            if n["name"] == "hasFeature":
                return self._feat(n["args"][0])
            raise ValueError(n)
        if k == "set":
            return self._set(n)
        if k == "ty":
            return f"(Ty {self.dag(n['args'][0])})"
        if k in self._UNARY:
            return f"({self._UNARY[k]} {self.dag(n['args'][0])})"
        if k in self._BINARY:
            return (f"({self._BINARY[k]} {self.dag(n['args'][0])}, "
                    f"{self.dag(n['args'][1])})")
        if k == "vecOf":
            return f"(VecOf {self.dag(n['args'][0])}, {self.dag(n['args'][1])})"
        if k == "scalarOrVecOf":
            return f"(ScalarOrVecOf {self.dag(n['args'][0])}, {self.dag(n['args'][1])})"
        if k == "pow2":
            return "(Pow2)"
        if k == "pow2Min":
            return f"(Pow2Min {self.dag(n['args'][0])})"
        if k == "clamp":
            return f"(Clamp {self.dag(n['args'][0])}, {self.dag(n['args'][1])})"
        if k in self._CMP:
            return f"({self._CMP[k]} {self.dag(n['args'][0])}, {self.dag(n['args'][1])})"
        if k == "not":
            return f"(CoreNot {self.dag(n['args'][0])})"
        if k in ("all", "any"):
            c = "CoreAll" if k == "all" else "CoreAny"
            return f"({c} " + ", ".join(self.dag(a) for a in n["args"]) + ")"
        if k == "in":
            return f"(CoreIn {self.dag(n['args'][0])}, {self.dag(n['args'][1])})"
        if k == "inPairs":
            a = n["args"]
            return f"(CoreInPairs {self.dag(a[0])}, {self.dag(a[1])}, {self.dag(a[2])})"
        if k == "inTriples":
            a = n["args"]
            return (f"(CoreInTriples {self.dag(a[0])}, {self.dag(a[1])}, "
                    f"{self.dag(a[2])}, {self.dag(a[3])})")
        if k == "inMemDesc":
            a = n["args"]
            return (f"(CoreInMemDesc {self.dag(a[0])}, {self.dag(a[1])}, "
                    f"{self.dag(a[2])}, {self.dag(a[3])})")
        if k == "select":
            return (f"(CoreSelect {self.dag(n['args'][0])}, "
                    f"{self.dag(n['args'][1])}, {self.dag(n['args'][2])})")
        if k == "nary":
            return self._pred_dag(n)
        raise ValueError(f"unknown node kind {k!r}")

    def rule(self, r):
        op, pred = r["op"], r["predicate"]
        is_true = (pred.get("kind") == "leaf" and pred.get("name") == "true")
        if op in self._OPS:
            # An unconditional terminal is the `CoreAlways*` def: the schema
            # serializes an unset guard as the true leaf, while
            # `CoreLibcall<(CoreTrue)>` would serialize as {"kind":"true"}.
            return self._ALWAYS[op] if is_true else f"{self._OPS[op]}<{self.dag(pred)}>"
        if op in self._LATTICE:
            if op == "widen" and r["to"].get("kind") == "int":
                # dag params cannot take a bare int; the schema gives widen one
                # dedicated class for the int target (CoreWidenPow2OrMinSize).
                return (f"CoreWidenPow2OrMinSize<{self.dag(r['on'])}, "
                        f"{r['to']['value']}>")
            c = self._LATTICE[op]
            on, to = self.dag(r["on"]), self.dag(r["to"])
            if is_true:
                return f"{c}<{on}, {to}>"
            return f"{c}If<{on}, {to}, {self.dag(pred)}>"
        if op == "scalarize":
            on = self.dag(r["on"])
            if is_true:
                return f"CoreScalarize<{on}>"
            return f"CoreScalarizeIf<{on}, {self.dag(pred)}>"
        raise ValueError(r)

    def emit(self):
        rendered = [(rs, [self.rule(r) for r in rs["rules"]])
                    for rs in self.rulesets]
        lines = ['include "llvm/Target/LegalizerInfo.td"',
                 'include "llvm/Target/Target.td"', ""]
        for s, name in self.features.items():
            lines.append(f'def {name} : LegalizeFeature<"{s}">;')
        for text, name in self.pred_dags.items():
            lines.append(f'def {name} : LegalizePredicateDag<{text}>;')
        for tname, name in self.types.items():
            lines.append(f'def {name} : LegalizeNamedType<"{_llt(tname)}">;')
        for (cond, then, els), name in self.selects.items():
            lines.append(f'def {name} : LegalizeSelectType<[{cond}], [{then}], {els}>;')
        lines.append("")
        for rs, texts in rendered:
            op = ", ".join(f'"{o}"' for o in rs["opcodes"])
            lines.append(f'def {rs["def"]} : LegalizeRuleSet<[{op}]> {{')
            lines.append("  let Rules = [")
            for t in texts:
                lines.append(f"    {t},")
            lines.append("  ];")
            lines.append("}")
            lines.append("")
        return "\n".join(lines) + "\n"


# ---- static checks (J1 sort / J2b compare / J3a action / J3b slot bound) --

COMPARE_SORTS = {"Int", "Kind", "Ordering", "Type"}
# admissible target sorts per lattice operator (action table, J3a)
TARGET_SORTS = {"widen": {"Type", "Int"}, "narrow": {"Type", "Int"},
                "more": {"Int", "Type"}, "fewer": {"Int", "Type"},
                "bitcast": {"Type"}}

def _tc(node, arity, errs):
    """Type-check one normal-form node, return its sort (J1 / J2b)."""
    k = node["kind"]
    args = node.get("args", [])

    def need(i, sort):
        got = _tc(args[i], arity, errs)
        if got != sort:
            errs.append(f"{k}: arg {i} sort mismatch (got {got}, want {sort})")
        return got

    if k == "int":
        return "Int"
    if k == "slot":
        if node["index"] >= arity:
            errs.append(f"(Slot {node['index']}) out of range: opcode has {arity} slot(s)")
        return "Type"
    if k == "type":
        return "Type"
    if k in ("kindVector", "kindScalableVector", "kindScalar", "kindPointer"):
        return "Kind"
    if k == "leaf":
        return "Bool"
    if k == "set":
        return "Set"
    if k in ("elemOf", "scalarOf", "replace", "ty"):
        need(0, "Type")
        return "Type"
    if k == "sortOf":
        need(0, "Type")
        return "Kind"
    if k in ("numElems", "bitsOf"):
        need(0, "Type")
        return "Int"
    if k in ("vecOf", "scalarOrVecOf"):
        need(0, "Int"); need(1, "Type")
        return "Type"
    if k == "pow2":
        return "Int"
    if k == "pow2Min":
        need(0, "Int")
        return "Int"
    if k == "select":
        need(0, "Bool"); need(1, "Int"); need(2, "Int")
        return "Int"
    if k == "not":
        need(0, "Bool")
        return "Bool"
    if k in ("all", "any"):
        if len(args) < 1:
            errs.append(f"{k}: variadic needs >=1 arg")
        for a in args:
            _tc(a, arity, errs)
        return "Bool"
    if k in ("eq", "ne", "lt", "le", "gt", "ge"):
        a = _tc(args[0], arity, errs); b = _tc(args[1], arity, errs)
        if a != b:
            errs.append(f"{k}: operand sorts differ ({a} vs {b})")
        elif a not in COMPARE_SORTS:
            errs.append(f"{k}: comparison over unsupported sort {a}")
        return "Bool"
    if k == "in":
        if _tc(args[0], arity, errs) != "Type":
            errs.append(f"in: left operand must be Type")
        return "Bool"
    raise ValueError(f"typecheck: unknown node kind {k!r}")

def check_rule(rule, arity, errs):
    op = rule["op"]
    if op in ("legal", "lower", "custom", "unsupported", "libcall"):
        if _tc(rule["predicate"], arity, errs) != "Bool":
            errs.append(f"{op}: guard must be Bool")
    elif op in TARGET_SORTS:
        _tc(rule["on"], arity, errs)
        ts = _tc(rule["to"], arity, errs)
        if ts not in TARGET_SORTS[op]:
            errs.append(f"{op}: target sort {ts} not in action table")
        _tc(rule["predicate"], arity, errs)
    elif op == "scalarize":
        _tc(rule["on"], arity, errs)
    else:
        errs.append(f"unknown op {op!r}")

def build_arity_manifest(generic_td_path):
    """Per-opcode type-slot count from GenericOpcodes.td (inline typeN/ptypeN).

    Handles `def G_X : GenericInstruction { ... }` with the operand lists
    written inline.  Opcodes whose lists are inherited through a class leave
    no typeN in the body and are recorded as None (cannot check J3b).
    """
    text = open(generic_td_path).read()
    manifest = {}
    for m in re.finditer(r"def\s+(G_\w+)\s*:[^{]*\{", text):
        name = m.group(1)
        i = m.end() - 1
        depth, j = 0, i
        while j < len(text):
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = text[i:j + 1]
        maxn = max((int(t.group(1))
                    for t in re.finditer(r"\b(?:type|ptype)(\d+)\b", body)),
                   default=-1)
        manifest[name] = maxn + 1 if maxn >= 0 else None
    return manifest

def check_rules(compiled, opcodes, manifest, errs):
    arities = [manifest.get(o) for o in opcodes]
    known = [a for a in arities if a is not None]
    arity = min(known) if known else None   # multi-opcode takes the minimum (J3b)
    for r in compiled:
        check_rule(r, arity if arity is not None else 10**9, errs)
    return arity


TBLGEN = "/home/ubuntu/llvm/builds/explore/bin/llvm-tblgen"
INC = ["-I/home/ubuntu/llvm/trees/explore/llvm/include",
       "-I/home/ubuntu/llvm/builds/explore/include",
       "-I/home/ubuntu/llvm/trees/explore/llvm/lib/Target"]


def roundtrip_corpus(name, core_json_path, target_dir):
    """baseline core.json -> reverse-emit .td -> tblgen -> normal form diff."""
    baseline = json.load(open(core_json_path))
    rulesets = [{"def": rs["def"], "opcodes": rs["opcodes"], "rules": rs["rules"]}
                for rs in baseline["rulesets"]]
    td = TdEmitter(rulesets).emit()
    d = tempfile.mkdtemp(prefix="dsl-rt-")
    path = os.path.join(d, "ReverseLegalizerInfo.td")
    with open(path, "w") as f:
        f.write(td)
    out = os.path.join(d, "out.core.json")
    inc = INC + [f"-I/home/ubuntu/llvm/trees/explore/llvm/lib/Target/{target_dir}"]
    r = subprocess.run([TBLGEN, "-gen-legalizer-core", *inc, path, "-o", out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"({name}) tblgen failed:\n{r.stderr}")
        print("emitted .td head:\n" + "\n".join(td.splitlines()[:40]))
        return 10**9
    gen = json.load(open(out))
    brs = {rs["def"]: rs for rs in baseline["rulesets"]}
    grs = {rs["def"]: rs for rs in gen["rulesets"]}
    total = diff = 0
    for defn, br in brs.items():
        if defn not in grs:
            print(f"  {name}: missing ruleset {defn}")
            diff += 1
            continue
        gr = grs[defn]
        if br["opcodes"] != gr["opcodes"]:
            print(f"  {name}:{defn} opcodes differ {br['opcodes']} vs {gr['opcodes']}")
            diff += 1
        brr, grr = br["rules"], gr["rules"]
        total += len(brr)
        if len(brr) != len(grr):
            print(f"  {name}:{defn} rule count {len(brr)} vs {len(grr)}")
            diff += 1
            continue
        for i, (e, g) in enumerate(zip(brr, grr)):
            if strip(e) != strip(g):
                if diff < 3:
                    print(f"  {name}:{defn}#{i} DIFF")
                    print("    oracle:", json.dumps(strip(e), sort_keys=True)[:400])
                    print("    gen   :", json.dumps(strip(g), sort_keys=True)[:400])
                diff += 1
    print(f"({name}) round-trip: {total} rules, {diff} diffs "
          f"{'ALL MATCH' if diff == 0 else 'SOME DIFF'}")
    return diff



# ---- free-form DSL source renderer (normal form -> DSL text) --------------

KIND_FROM = {"kindVector": "vector", "kindScalableVector": "scalable_vector",
             "kindScalar": "scalar", "kindPointer": "pointer",
             "kindPointerVector": "pointer_vector"}
ORDERING_FROM = {"orderingUnordered": "ordering_unordered",
                 "orderingMonotonic": "ordering_monotonic",
                 "orderingAcquire": "ordering_acquire",
                 "orderingRelease": "ordering_release",
                 "orderingAcquireRelease": "ordering_acquire_release",
                 "orderingSequentiallyConsistent": "ordering_sequentially_consistent"}
UNARY_FROM = {"elemOf": "elem_of", "scalarOf": "scalar_of", "sortOf": "sort_of",
              "numElems": "num_elems", "bitsOf": "bits_of", "sizeOf": "size_of",
              "sizeInBytesOf": "size_in_bytes_of", "isByteSized": "is_byte_sized",
              "addrSpace": "addr_space", "alignOf": "align_of",
              "memSlot": "mem_slot", "memTy": "mem_ty", "memOrdering": "mem_ordering",
              "memFailureOrdering": "mem_failure_ordering",
              "isBFloat16": "is_bfloat16", "isFloat16": "is_float16",
              "isPow2": "is_pow2", "replace": "replace", "pow2Ceil": "pow2_ceil",
              "multipleOf": "multiple_of", "sameAs": "same_as",
              "minVectorSize": "min_vector_size", "intOfSize": "int_of_size",
              "ty": "ty", "pow2Min": "pow2_min"}
BINARY_FROM = {"vecOf": "vec_of", "scalarOrVecOf": "scalar_or_vec_of",
               "eltTypeTo": "elt_type_to", "eltSizeTo": "elt_size_to",
               "divLanes": "div_lanes", "mul": "mul", "urem": "urem",
               "udiv": "udiv", "clamp": "clamp"}
CMP_OPS = {"eq": "==", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}


def render_type_value(v):
    if isinstance(v, str):
        return v
    sel = v["select"]
    return (f"select_type({render_pred(sel['cond'])}, "
            f"{render_type_value(sel['then'])}, "
            f"{render_type_value(sel['else'])})")


def render_set(n):
    arity = n.get("arity", 1)
    elems = n["elems"]
    if arity == 1:
        return "[" + ", ".join(render_type_value(e) for e in elems) + "]"
    if arity == 2 and len(elems[0]) == 4:
        return ("[" + ", ".join(
            f"mem_desc({render_type_value(e[0])}, {render_type_value(e[1])}, "
            f"{render_type_value(e[2])}, {e[3]})" for e in elems) + "]")
    return ("[" + ", ".join(
        "[" + ", ".join(render_type_value(x) for x in e) + "]"
        for e in elems) + "]")


def render_expr(n):
    k = n["kind"]
    if k == "int":
        return str(n["value"])
    if k == "slot":
        return f"slot({n['index']})"
    if k == "type":
        return render_type_value(n["value"])
    if k in KIND_FROM:
        return KIND_FROM[k]
    if k in ORDERING_FROM:
        return ORDERING_FROM[k]
    if k == "pow2":
        return "pow2"
    if k in UNARY_FROM:
        return f"{UNARY_FROM[k]}({render_expr(n['args'][0])})"
    if k in BINARY_FROM:
        return (f"{BINARY_FROM[k]}({render_expr(n['args'][0])}, "
                f"{render_expr(n['args'][1])})")
    if k == "select":
        return (f"select({render_pred(n['args'][0])}, "
                f"{render_expr(n['args'][1])}, {render_expr(n['args'][2])})")
    raise ValueError(f"cannot render expr kind {k!r}")


def render_pred(n):
    k = n["kind"]
    if k == "leaf":
        if n["name"] == "true":
            return "true"
        if n["name"] == "hasFeature":
            return f'feature("{n["args"][0]}")'
        raise ValueError(n)
    if k == "all":
        if len(n["args"]) == 1:
            return "all_of(" + render_pred(n["args"][0]) + ")"
        return "(" + " and ".join(render_pred(a) for a in n["args"]) + ")"
    if k == "any":
        if len(n["args"]) == 1:
            return "any_of(" + render_pred(n["args"][0]) + ")"
        return "(" + " or ".join(render_pred(a) for a in n["args"]) + ")"
    if k == "not":
        return "not " + render_pred(n["args"][0])
    if k in CMP_OPS:
        return (f"{render_expr(n['args'][0])} {CMP_OPS[k]} "
                f"{render_expr(n['args'][1])}")
    if k == "in":
        return (f"in({render_expr(n['args'][0])}, "
                f"{render_set_or_type(n['args'][1])})")
    if k == "inPairs":
        a = n["args"]
        return (f"in_pairs({render_expr(a[0])}, {render_expr(a[1])}, "
                f"{render_set(a[2])})")
    if k == "inTriples":
        a = n["args"]
        return (f"in_triples({render_expr(a[0])}, {render_expr(a[1])}, "
                f"{render_expr(a[2])}, {render_set(a[3])})")
    if k == "inMemDesc":
        a = n["args"]
        return (f"in_mem_desc({render_expr(a[0])}, {render_expr(a[1])}, "
                f"{render_expr(a[2])}, {render_set(a[3])})")
    if k == "nary":
        # legacy all_of/any_of predicate-dag -> core and/or (same meaning)
        op = n["op"]
        parts = [render_pred_legacy(a) for a in n["args"]]
        join = " and " if op == "all_of" else " or "
        return "(" + join.join(parts) + ")"
    if k in UNARY_FROM:
        return render_expr(n)
    raise ValueError(f"cannot render pred kind {k!r}")


def render_pred_legacy(n):
    k = n["kind"]
    if k == "leaf":
        return render_pred(n)
    if k == "not":
        return "not " + render_pred_legacy(n["arg"])
    if k == "nary":
        op = n["op"]
        join = " and " if op == "all_of" else " or "
        return "(" + join.join(render_pred_legacy(a) for a in n["args"]) + ")"
    raise ValueError(n)


def render_set_or_type(n):
    if n["kind"] == "type":
        return render_type_value(n["value"])
    return render_set(n)


def render_rule(r):
    op = r["op"]
    pred = r["predicate"]
    is_true = pred.get("kind") == "leaf" and pred.get("name") == "true"
    if op in ("legal", "lower", "custom", "unsupported", "libcall"):
        return f"{op} {render_pred(pred)}"
    if op in ("widen", "narrow", "more", "fewer", "bitcast"):
        text = f"{op}({render_expr(r['on'])}, {render_expr(r['to'])})"
        if not is_true:
            text += f" when {render_pred(pred)}"
        return text
    if op == "scalarize":
        text = f"scalarize({render_expr(r['on'])})"
        if not is_true:
            text += f" when {render_pred(pred)}"
        return text
    raise ValueError(r)


def render_ruleset(rs):
    lines = [f"rule {' '.join(rs['opcodes'])}:"]
    for r in rs["rules"]:
        lines.append(f"    {render_rule(r)}")
    return "\n".join(lines)


def normalize_nary(n):
    """Legacy nary/not(arg) predicate-dag -> core all/any/not(args) form."""
    if isinstance(n, dict):
        k = n.get("kind")
        if k == "nary":
            return _node("all" if n["op"] == "all_of" else "any",
                         args=[normalize_nary(a) for a in n["args"]])
        if k == "not" and "arg" in n and "args" not in n:
            return _node("not", args=[normalize_nary(n["arg"])])
        return {kk: normalize_nary(vv) for kk, vv in n.items()}
    if isinstance(n, list):
        return [normalize_nary(x) for x in n]
    return n


def forward_roundtrip(name, core_json_path):
    """baseline core.json -> free-form DSL source -> parse -> normal form diff."""
    baseline = json.load(open(core_json_path))
    total = diff = 0
    src_parts = []
    for rs in baseline["rulesets"]:
        src_parts.append(render_ruleset(rs))
    src = "\n\n".join(src_parts) + "\n"
    ast = Parser(src).parse()
    compiled = [normalize_nary(r) for r in compile_rulesets(ast)]
    expect = [normalize_nary(r) for rs in baseline["rulesets"]
              for r in rs["rules"]]
    total = len(expect)
    if len(compiled) != len(expect):
        print(f"({name}) forward: rule count {len(compiled)} vs {len(expect)}")
        diff += abs(len(compiled) - len(expect))
    for i, (e, g) in enumerate(zip(expect, compiled)):
        if strip(e) != strip(g):
            if diff < 3:
                print(f"({name}) forward #{i} DIFF")
                print("  oracle:", json.dumps(strip(e), sort_keys=True)[:400])
                print("  gen   :", json.dumps(strip(g), sort_keys=True)[:400])
            diff += 1
    print(f"({name}) forward round-trip: {total} rules, {diff} diffs "
          f"{'ALL MATCH' if diff == 0 else 'SOME DIFF'}")
    return diff



def main():
    src = r'''
rule G_ADD G_SUB:
    legal in(slot(0), [s8, s16, s32])
    legal feature("Subtarget.is64Bit()") and in(slot(0), s64)
    legal feature("Subtarget.hasSSE2()") and in(slot(0), [v16s8, v8s16, v4s32, v2s64])
    legal feature("Subtarget.hasAVX2()") and in(slot(0), [v32s8, v16s16, v8s32, v4s64])
    legal feature("Subtarget.hasAVX512()") and in(slot(0), [v16s32, v8s64])
    legal feature("Subtarget.hasAVX512() && Subtarget.hasBWI()") and in(slot(0), [v64s8, v32s16])
    clamp_min(0, s8, 16)
    clamp_min(0, s16, 8)
    clamp_min(0, s32, 4)
    clamp_min(0, s64, 2)
    clamp_max(0, s8, select(feature("Subtarget.hasAVX512() && Subtarget.hasBWI()"), 64, select(feature("Subtarget.hasAVX2()"), 32, 16)))
    clamp_max(0, s16, select(feature("Subtarget.hasAVX512() && Subtarget.hasBWI()"), 32, select(feature("Subtarget.hasAVX2()"), 16, 8)))
    clamp_max(0, s32, select(feature("Subtarget.hasAVX512()"), 16, select(feature("Subtarget.hasAVX2()"), 8, 4)))
    clamp_max(0, s64, select(feature("Subtarget.hasAVX512()"), 8, select(feature("Subtarget.hasAVX2()"), 4, 2)))
    widen(slot(0), pow2_min(32))
    widen(slot(0), ty(s8))
    narrow(slot(0), ty(select_type(feature("Subtarget.is64Bit()"), s64, s32)))
    scalarize(slot(0))
'''
    ast = Parser(src).parse()
    compiled = compile_rulesets(ast)

    x86 = json.load(open("/home/ubuntu/legalizer-baseline/x86.core.json"))
    oracle = next(r for r in x86["rulesets"] if r["def"] == "X86_ADD")["rules"]
    assert len(compiled) == len(oracle), (len(compiled), len(oracle))

    # (a) direct compile -> normal form, vs baseline
    ok1 = all(strip(e) == g for e, g in zip(oracle, compiled))
    print(f"(a) direct compile: {len(compiled)} rules "
          f"{'ALL MATCH' if ok1 else 'SOME DIFF'}")

    # (b) free-form -> .td -> llvm-tblgen -gen-legalizer-core -> normal form
    td = TdEmitter([{"def": "X86_ADD", "opcodes": ["G_ADD", "G_SUB"],
                  "rules": compiled}]).emit()
    d = tempfile.mkdtemp(prefix="dsl-td-")
    path = os.path.join(d, "X86LegalizerInfo.td")
    with open(path, "w") as f:
        f.write(td)
    out = os.path.join(d, "out.core.json")
    tblgen = "/home/ubuntu/llvm/builds/explore/bin/llvm-tblgen"
    inc = ["-I/home/ubuntu/llvm/trees/explore/llvm/lib/Target/X86",
           "-I/home/ubuntu/llvm/builds/explore/include",
           "-I/home/ubuntu/llvm/trees/explore/llvm/include",
           "-I/home/ubuntu/llvm/trees/explore/llvm/lib/Target"]
    r = subprocess.run([tblgen, "-gen-legalizer-core", *inc, path, "-o", out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("tblgen failed:\n" + r.stderr)
        print("emitted .td:\n" + td)
        return 1
    gen = json.load(open(out))
    gen_rules = next(x for x in gen["rulesets"] if x["def"] == "X86_ADD")["rules"]
    assert len(gen_rules) == len(oracle), (len(gen_rules), len(oracle))
    ok2 = all(strip(e) == strip(g) for e, g in zip(oracle, gen_rules))
    print(f"(b) .td round-trip: {len(gen_rules)} rules "
          f"{'ALL MATCH' if ok2 else 'SOME DIFF'}")
    if not ok2:
        for i, (e, g) in enumerate(zip(oracle, gen_rules)):
            if strip(e) != strip(g):
                print(f"  #{i} oracle:", json.dumps(strip(e), sort_keys=True))
                print(f"  #{i} gen   :", json.dumps(strip(g), sort_keys=True))
                break
    # (c) static checks: positive (X86_ADD) + negative (sort / slot-bound)
    manifest = build_arity_manifest(
        "/home/ubuntu/llvm/trees/explore/llvm/include/llvm/Target/GenericOpcodes.td")
    errs = []
    arity = check_rules(compiled, ["G_ADD", "G_SUB"], manifest, errs)
    print(f"(c) static checks: X86_ADD arity={arity} errors={len(errs)}")
    ok3 = (len(errs) == 0 and arity == 1)

    neg = [
        ("sort mismatch", "rule G_ADD:\n    legal slot(0) == pow2"),
        ("slot out of range", "rule G_ADD:\n    legal in(slot(1), s8)"),
    ]
    ok4 = True
    for label, src in neg:
        ncomp = compile_rulesets(Parser(src).parse())
        nerrs = []
        check_rules(ncomp, ["G_ADD"], manifest, nerrs)
        got_err = len(nerrs) > 0
        ok4 &= got_err
        print(f"    negative [{label}]: {'rejected' if got_err else 'MISSED'} -> {nerrs[:1]}")

    print("static checks: " + ("ALL PASS" if (ok3 and ok4) else "FAIL"))

    # (d) full-corpus reverse round-trip
    d1 = roundtrip_corpus("X86", "/home/ubuntu/legalizer-baseline/x86.core.json", "X86")
    d2 = roundtrip_corpus("AArch64",
                          "/home/ubuntu/legalizer-baseline/aarch64.core.json",
                          "AArch64")
    ok5 = (d1 == 0 and d2 == 0)
    print("full corpus: " + ("ALL PASS" if ok5 else "FAIL"))

    # (e) forward: baseline core.json -> free-form DSL -> parse -> normal form
    e1 = forward_roundtrip("X86", "/home/ubuntu/legalizer-baseline/x86.core.json")
    e2 = forward_roundtrip("AArch64",
                           "/home/ubuntu/legalizer-baseline/aarch64.core.json")
    ok6 = (e1 == 0 and e2 == 0)
    print("forward DSL: " + ("ALL PASS" if ok6 else "FAIL"))
    return 0 if (ok1 and ok2 and ok3 and ok4 and ok5 and ok6) else 1


if __name__ == "__main__":
    sys.exit(main())
