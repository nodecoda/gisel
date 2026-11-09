#!/usr/bin/env python3
"""The `.gisel` rule-body parser and compiler.

The file-level model is :class:`gisel.ast.Program`; this module owns only the
tokenizer, the statement parser and the lowering of one rule body to the
schema-0.4 normal form used by the C++/JSON backends.

    stmt := legal|lower|custom|unsupported|libcall <pred>
          | widen|narrow|more|fewer|bitcast ( <expr> , <expr> ) [ when <pred> ]
          | scalarize ( <expr> ) [ when <pred> ]
          | clamp_min ( INT , TYPE , <expr> )
          | clamp_max ( INT , TYPE , <expr> )        # lanes: int or select(...)
    pred := or of ( and of ( not | primary ) )
    primary := true | ( pred ) | feature ( STR ) | FEATURE_NAME
            | in ( expr , [TYPE,...] | TYPE )
            | expr ( ==|!=|<|<=|>|>= ) expr
    expr  := INT | TYPE | KIND | call ( ... )
          | select ( <expr> , <expr> , <expr> )        # int select
          | select_type ( <expr> , TYPE , TYPE )       # type select (in ty(...))

Static checks: J1 sort, J2b comparison sorts, J3a action table, J3b slot
bounds (arity from the bundled JSON table).
"""

import json
import os
import re

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
              "is_pow2": "isPow2", "is_fixed_vector": "isFixedVector",
              "replace": "replace", "pow2_ceil": "pow2Ceil",
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

def tokenize(text, line_map=None):
    toks = []
    lines = text.splitlines()
    # indentation -> INDENT/DEDENT, Python-style
    stack = [0]
    for ln, raw in enumerate(lines, 1):
        # line_map[k] is the .gisel line a snippet line came from
        sl = line_map[ln - 1] if line_map and ln - 1 < len(line_map) else ln
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent > stack[-1]:
            stack.append(indent); toks.append(Tok("INDENT", None, sl))
        while indent < stack[-1]:
            stack.pop(); toks.append(Tok("DEDENT", None, sl))
        i = 0
        line = raw.strip()
        n = len(line)
        while i < n:
            c = line[i]
            if c.isspace():
                i += 1; continue
            if line.startswith(("==", "!=", "<=", ">="), i):
                toks.append(Tok("OP", line[i:i+2], sl)); i += 2; continue
            if c in "<>":
                toks.append(Tok("OP", c, sl)); i += 1; continue
            if c in "(),[]:":
                toks.append(Tok(c, c, sl)); i += 1; continue
            if c == '"':
                j = i + 1
                buf = []
                while j < n and line[j] != '"':
                    if line[j] == "\\" and j + 1 < n:
                        buf.append(line[j + 1]); j += 2; continue
                    buf.append(line[j]); j += 1
                toks.append(Tok("STR", "".join(buf), sl)); i = j + 1; continue
            if c.isdigit():
                j = i
                while j < n and line[j].isdigit():
                    j += 1
                toks.append(Tok("INT", int(line[i:j]), sl)); i = j; continue
            if c.isalpha():
                m = TYPE_TOKEN_RE.match(line, i)
                if m and (m.end() == n or not (line[m.end()].isalnum()
                                               or line[m.end()] == "_")):
                    toks.append(Tok("TYPE", m.group(), sl)); i = m.end(); continue
            if c.isalpha() or c == "_":
                j = i
                while j < n and (line[j].isalnum() or line[j] == "_"):
                    j += 1
                toks.append(Tok("ID", line[i:j], sl)); i = j; continue
            raise ValueError(f"line {sl}: bad char {c!r}")
        toks.append(Tok("NEWLINE", None, sl))
    while len(stack) > 1:
        stack.pop(); toks.append(Tok("DEDENT", None, None))
    toks.append(Tok("EOF", None, None))
    return toks

# ---- parser ---------------------------------------------------------------

class Parser:
    def __init__(self, text, line_map=None, features=None):
        self.toks = tokenize(text, line_map)
        self.p = 0
        # Declared `feature NAME = ...` names usable as boolean primaries.
        # Maps NAME -> the C++ bool expression (`Feature.cxx`).
        self.features = dict(features or {})

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
        line = kw.line
        if k in ("legal", "lower", "custom", "unsupported", "libcall"):
            pred = self.parse_pred()
            return {"op": k, "pred": pred, "_line": line}
        if k in ("widen", "narrow", "more", "fewer", "bitcast"):
            self.expect("(")
            on = self.parse_expr()
            self.expect(",")
            to = self.parse_expr()
            self.expect(")")
            pred = None
            if self.peek() and self.peek().t == "ID" and self.peek().v == "when":
                self.next(); pred = self.parse_pred()
            return {"op": k, "on": on, "to": to, "pred": pred, "_line": line}
        if k == "scalarize":
            self.expect("(")
            on = self.parse_expr()
            self.expect(")")
            pred = None
            if self.peek() and self.peek().t == "ID" and self.peek().v == "when":
                self.next(); pred = self.parse_pred()
            return {"op": k, "on": on, "to": None, "pred": pred, "_line": line}
        if k in ("clamp_min", "clamp_max"):
            self.expect("(")
            idx = self.next().v; self.expect(",")
            elt = self.next().v; self.expect(",")
            lanes = self.parse_expr()
            self.expect(")")
            return {"op": k, "idx": idx, "elt": elt, "lanes": lanes,
                    "_line": line}
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
        # A host expression the corpus cannot evaluate: it is copied into the
        # generated C++ verbatim, inside the rule's `LegalityQuery` lambda.
        # `eval`/`cases` treat it as a hole (`opaque`), never as false.
        if self.peek() and self.peek().t == "ID" and self.peek().v == "opaque":
            self.next(); self.expect("(")
            tok = self.next()
            if tok.t != "STR":
                raise ValueError(
                    f"line {tok.line}: opaque( needs a C++ string, got {tok.v!r}")
            self.expect(")")
            return leaf("opaque", [tok.v])
        # A declared feature name (`HasAVX`) is a boolean primary, equivalent
        # to `feature("Subtarget.hasAVX()")` and resolving to the same node.
        if self.peek() and self.peek().t == "ID" \
                and self.peek().v in self.features:
            name = self.next().v
            return leaf("hasFeature", [self.features[name]])
        # explicit n-ary combinators (all_of/any_of) for arity-1 and readability
        if self.peek() and self.peek().t == "ID" and self.peek().v in (
                "in", "in_pairs", "in_triples", "in_mem_desc"):
            return self.parse_membership()
        if self.peek() and self.peek().t == "ID" and self.peek().v in (
                "all_of", "any_of"):
            return self.parse_combinator()
        # Bool-returning observers can stand alone as a predicate primary
        if self.peek() and self.peek().t == "ID" and self.peek().v in (
                "is_bfloat16", "is_float16", "is_byte_sized", "is_pow2",
                "is_fixed_vector"):
            return self.parse_expr()
        # comparison
        left = self.parse_expr()
        tok = self.next()
        if tok.t != "OP":
            raise ValueError(f"line {tok.line}: expected comparison, got {tok.v!r}")
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
        if self.peek().t == "INT":
            elems = []
            while True:
                elems.append(self.next().v)
                if not self.peek(","):
                    break
                self.next()
            self.expect("]")
            return _node("set", of="Int", arity=1, elems=elems)
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
            # A named type, select type or type set; the .gisel source spells
            # these by name and the C++ generator keeps the declared name.
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
        if name == "imm":
            i = self.next().v
            self.expect(")")
            return _node("imm", index=i)
        args = []
        if not self.peek(")"):
            while True:
                args.append(self.parse_expr())
                if not self.peek(","):
                    break
                self.next()
        self.expect(")")
        if name in UNARY_CALL:
            if len(args) != 1:
                raise ValueError(f"{name}: expects 1 argument, got {len(args)}")
            return call1(UNARY_CALL[name], args[0])
        if name in BINARY_CALL:
            if len(args) != 2:
                raise ValueError(f"{name}: expects 2 arguments, got {len(args)}")
            return call2(BINARY_CALL[name], args[0], args[1])
        raise ValueError(f"line {self.toks[self.p-2].line}: unknown constructor "
                         f"{name!r}")

# ---- compiler: AST -> normal form ----------------------------------------

def compile_rulesets(ast):
    """Return list of rule dicts in schema-0.4 normal form (semantic fields)."""
    out = []
    for rs in ast:
        for st in rs["stmts"]:
            rule = compile_stmt(st)
            if "_line" in st:
                rule["_line"] = st["_line"]
            out.append(rule)
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

# ---- static checks (J1 sort / J2b compare / J3a action / J3b slot bound) --

COMPARE_SORTS = {"Int", "Kind", "Ordering", "Type"}
KIND_ORDERING = {"orderingUnordered", "orderingMonotonic", "orderingAcquire",
                 "orderingRelease", "orderingAcquireRelease",
                 "orderingSequentiallyConsistent"}
# admissible target sorts per lattice operator (action table, J3a)
TARGET_SORTS = {"widen": {"Type", "Int"}, "narrow": {"Type", "Int"},
                "more": {"Int", "Type"}, "fewer": {"Int", "Type"},
                "bitcast": {"Type"}}

def _check_name(name, names, errs):
    """A type leaf must name a declared record.  None disables the check."""
    if names is None or not isinstance(name, str):
        return
    if name not in names:
        errs.append(f"unknown type name {name!r}: no `type`, `select` or "
                    f"`type_set` declares it")


def _tc(node, arity, errs, names=None):
    """Type-check one normal-form node, return its sort (J1 / J2b).

    The sorts are the ones the evaluator distinguishes at run time
    (gisel/eval.py value()/bool_value()); MemDesc is the only one that never
    reaches a comparison.

    `names` is the set of declared `type`/`select`/`type_set` records.  When
    it is given, a type leaf that names nothing is reported here.  Without it
    this check used to pass silently and the first reader to notice was
    `core_json.type_name`, which raised a KeyError out of `gisel gen` -- a
    traceback where the contract promises `path:line: message`.  None keeps
    the old behaviour for callers that only have a rule node.
    """
    k = node["kind"]
    args = node.get("args", [])

    def tc(n):
        return _tc(n, arity, errs, names)

    def need(i, sort):
        got = tc(args[i])
        if got != sort:
            errs.append(f"{k}: arg {i} sort mismatch (got {got}, want {sort})")
        return got

    def need_any(i, sorts):
        got = tc(args[i])
        if got not in sorts:
            errs.append(f"{k}: arg {i} sort mismatch (got {got}, want {sorts})")
        return got

    if k == "int":
        return "Int"
    if k == "true":
        return "Bool"
    if k == "slot":
        if node["index"] >= arity:
            errs.append(f"(Slot {node['index']}) out of range: opcode has {arity} slot(s)")
        return "Type"
    if k == "type":
        _check_name(node.get("value"), names, errs)
        return "Type"
    if k == "set":
        # `in(slot(0), [a, b])` keeps its members as plain strings; they are
        # the other place a type name is spelled, and skipping them is how
        # `[s8]` reached the core backend unchecked.
        if node.get("of", "Type") == "Type":
            for name in node.get("elems", []):
                _check_name(name, names, errs)
        return "Set"
    if k == "imm":
        # There is no per-opcode immediate count to check against: the
        # GenericOpcodes table describes type slots only.
        return "Int"
    if k == "leaf":
        return "Bool"
    if k in ("kindVector", "kindScalableVector", "kindScalar", "kindPointer",
             "kindPointerVector"):
        return "Kind"
    if k in KIND_ORDERING:
        return "Ordering"
    if k == "memSlot":
        need(0, "Int")
        return "MemDesc"
    if k == "sameAs":
        need(0, "Int")
        return "Type"
    if k in ("elemOf", "scalarOf", "replace", "ty"):
        need(0, "Type")
        return "Type"
    if k == "sortOf":
        need(0, "Type")
        return "Kind"
    if k in ("numElems", "bitsOf"):
        need(0, "Type")
        return "Int"
    if k == "sizeOf":
        need_any(0, {"Type", "MemDesc"})
        return "Int"
    if k == "sizeInBytesOf":
        need(0, "Type")
        return "Int"
    if k == "alignOf":
        need(0, "MemDesc")
        return "Int"
    if k == "addrSpace":
        need(0, "Type")
        return "Int"
    if k == "memTy":
        need(0, "MemDesc")
        return "Type"
    if k in ("memOrdering", "memFailureOrdering"):
        need(0, "MemDesc")
        return "Ordering"
    if k in ("mul", "urem", "udiv"):
        need(0, "Int"); need(1, "Int")
        return "Int"
    if k == "pow2Ceil":
        need(0, "Int")
        return "Int"
    if k == "intOfSize":
        need(0, "Int")
        return "Type"
    if k == "minVectorSize":
        need(0, "Int")
        return "Int"
    if k in ("vecOf", "scalarOrVecOf"):
        need(0, "Int"); need(1, "Type")
        return "Type"
    if k == "eltTypeTo":
        need(0, "Type"); need(1, "Type")
        return "Type"
    if k in ("eltSizeTo", "divLanes"):
        need(0, "Type"); need(1, "Int")
        return "Type"
    if k == "pow2":
        return "Int"
    if k == "pow2Min":
        need(0, "Int")
        return "Int"
    if k == "select":
        need(0, "Bool")
        a, b = tc(args[1]), tc(args[2])
        if a != b:
            errs.append(f"select: branch sorts differ ({a} vs {b})")
        elif a not in ("Int", "Type"):
            errs.append(f"select: unsupported branch sort {a}")
        return a
    if k == "not":
        sub = node.get("arg", args[0] if args else None)
        if sub is None:
            errs.append("not: missing operand")
        elif tc(sub) != "Bool":
            errs.append("not: operand must be Bool")
        return "Bool"
    if k in ("all", "any", "nary"):
        if k == "nary" and node.get("op") not in ("all_of", "any_of"):
            errs.append(f"nary: unknown op {node.get('op')!r}")
        for i in range(len(args)):
            need(i, "Bool")
        return "Bool"
    if k in ("eq", "ne", "lt", "le", "gt", "ge"):
        a = tc(args[0]); b = tc(args[1])
        if a != b:
            errs.append(f"{k}: operand sorts differ ({a} vs {b})")
        elif a not in COMPARE_SORTS:
            errs.append(f"{k}: comparison over unsupported sort {a}")
        return "Bool"
    if k == "in":
        lhs = tc(args[0])
        rhs = args[1] if len(args) > 1 else {}
        # The right-hand side was never visited: a single named type
        # (`in(slot(0), Target_Vec128)`) and a set's members are only reachable
        # through here, so `[s8]` with no `type s8 = ...` used to lint clean.
        if isinstance(rhs, dict) and rhs.get("kind") in ("type", "set"):
            tc(rhs)
        of = rhs.get("of", "Type") if isinstance(rhs, dict) else "Type"
        want = "Int" if of == "Int" else "Type"
        if lhs != want:
            errs.append(f"in: {of} set cannot test {lhs} "
                        f"(element sort mismatch)")
        return "Bool"
    if k == "inPairs":
        need(0, "Type"); need(1, "Type"); need(2, "Set")
        return "Bool"
    if k == "inTriples":
        for i in range(3):
            need(i, "Type")
        need(3, "Set")
        return "Bool"
    if k == "inMemDesc":
        need(0, "Type"); need(1, "Type"); need(2, "MemDesc"); need(3, "Set")
        return "Bool"
    if k in ("isPow2", "isBFloat16", "isFloat16", "isByteSized"):
        # A type predicate: isBFloat16 takes a type, isPow2 a byte count.
        need_any(0, {"Type", "Int"})
        return "Bool"
    if k == "isFixedVector":
        need(0, "Type")
        return "Bool"
    raise ValueError(f"typecheck: unknown node kind {k!r}")

def check_rule(rule, arity, errs, names=None):
    op = rule["op"]
    if op in ("legal", "lower", "custom", "unsupported", "libcall"):
        if _tc(rule["predicate"], arity, errs, names) != "Bool":
            errs.append(f"{op}: guard must be Bool")
    elif op in TARGET_SORTS:
        _tc(rule["on"], arity, errs, names)
        ts = _tc(rule["to"], arity, errs, names)
        if ts not in TARGET_SORTS[op]:
            errs.append(f"{op}: target sort {ts} not in action table")
        _tc(rule["predicate"], arity, errs, names)
    elif op == "scalarize":
        _tc(rule["on"], arity, errs, names)
    else:
        errs.append(f"unknown op {op!r}")

def load_arity_manifest():
    """The bundled opcode table: lint works without an LLVM source tree."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "generic_opcodes.json")
    with open(path) as f:
        return json.load(f)["opcodes"]


def check_rules(compiled, opcodes, manifest, errs):
    arities = [manifest.get(o) for o in opcodes]
    known = [a for a in arities if a is not None]
    arity = min(known) if known else None   # multi-opcode takes the minimum (J3b)
    for r in compiled:
        check_rule(r, arity if arity is not None else 10**9, errs)
    return arity
