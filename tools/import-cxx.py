#!/usr/bin/env python3
"""One-shot transcriber: three upstream legalizer constructors -> `.gisel`.

This is deliberately **not** a reusable C++ importer.  It knows exactly the
three constructors this repository ships a corpus for, hardcodes their quirks
and pins the rule counts it produced last time.  A fourth target, or a
different upstream revision, is a new tool -- not a flag on this one.

    tools/import-cxx.py X86 .../X86LegalizerInfo.cpp --out ...
    tools/import-cxx.py --all --llvm-src /path/to/llvm --out-dir tests/corpus
    tools/import-cxx.py --all --llvm-src /path/to/llvm --check

The input is not C++ in general: it is the subset these three constructors are
written in -- `getActionDefinitionsBuilder(...)` chains, `auto &X = ...` with
later extension, `if`/`else`, `for` over opcode lists, `const LLT` constants
and a handful of `LegalityPredicate` lambdas.

Anything outside that subset is **refused with a line number**, never dropped:
a transcription that silently loses a rule is worse than no transcription.

Exit codes: 0 imported, 1 refused or drifted from the pinned counts,
2 usage/parse error.
"""

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PREFIX = None  # set from the target name: RISCV -> "R_"
CURRENT_TARGET = None
USED_RENAMES = {"select": set(), "feature": set()}


def _norm(text):
    """Whitespace-insensitive key for the reviewed rename tables."""
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# Reviewed names for the generated declarations
#
# The transcriber names anonymous ternaries `selN`/`condN`, which is accurate
# but unreadable.  The tables below are the reviewed replacement: the key is
# the C++ expression with the target prefix removed, the value is
# (select name, predicate name).  A `None` predicate means the condition is a
# bare feature name and is used directly in the `select`, so no alias record
# is emitted.  Every key must still match, or the import fails: an upstream
# edit must not silently reintroduce generated names.
# ---------------------------------------------------------------------------

SELECT_NAMES = {
    "X86": {
        "Subtarget.is64Bit() ? s64 : s32": ("sMaxScalar", None),
        "HasAVX512 ? v64s8 : HasAVX ? v32s8 : v16s8": ("s8MaxVector", None),
        "HasAVX ? v32s8 : v16s8": ("s8MaxVectorNoAVX512", None),
        "HasAVX512 ? v32s16 : HasAVX ? v16s16 : v8s16": ("s16MaxVector", None),
        "HasAVX ? v16s16 : v8s16": ("s16MaxVectorNoAVX512", None),
        "HasAVX512 ? v16s32 : HasAVX ? v8s32 : v4s32": ("s32MaxVector", None),
        "HasAVX ? v8s32 : v4s32": ("s32MaxVectorNoAVX512", None),
        "HasAVX512 ? v8s64 : HasAVX ? v4s64 : v2s64": ("s64MaxVector", None),
        "HasAVX ? v4s64 : v2s64": ("s64MaxVectorNoAVX512", None),
        "HasSSE2 ? s64 : s32": ("sse2MaxScalar", None),
        "(UseX87 && !HasSSE1) ? s16 : s32": ("x87MinScalar", "useX87NoSSE1"),
        "HasCMOV ? s16 : s8": ("cmovMinScalar", None),
    },
    "AArch64": {},
    "RISCV": {
        "(XLen == 64 || ST.hasStdExtD()) ? s64 : s32":
            ("maxScalar", "has64BitScalar"),
    },
}

# C++ feature text -> name suffix.  Without these the receiver is part of the
# slug (`ST_hasNEON`), which reads like a different namespace.
FEATURE_NAMES = {
    "X86": {},
    "AArch64": {
        "ST.hasBF16()": "hasBF16",
        "ST.hasFPARMv8()": "hasFPARMv8",
        "ST.hasMOPS()": "hasMOPS",
        "ST.hasNEON()": "hasNEON",
    },
    "RISCV": {
        "ST.enableUnalignedScalarMem()": "enableUnalignedScalarMem",
        "ST.getELen() == 64": "getELen_64",
        "ST.hasStdExtA()": "hasStdExtA",
        "ST.hasStdExtD()": "hasStdExtD",
        "ST.hasStdExtF()": "hasStdExtF",
        "ST.hasStdExtM()": "hasStdExtM",
        "ST.hasStdExtP()": "hasStdExtP",
        "ST.hasStdExtZbb()": "hasStdExtZbb",
        "ST.hasStdExtZbc()": "hasStdExtZbc",
        "ST.hasStdExtZbkb()": "hasStdExtZbkb",
        "ST.hasStdExtZbkc()": "hasStdExtZbkc",
        "ST.hasStdExtZfa()": "hasStdExtZfa",
        "ST.hasStdExtZfh()": "hasStdExtZfh",
        "ST.hasStdExtZfhmin()": "hasStdExtZfhmin",
        "ST.hasStdExtZilsd()": "hasStdExtZilsd",
        "ST.hasStdExtZmmul()": "hasStdExtZmmul",
        "ST.hasVInstructions()": "hasVInstructions",
        "ST.hasVInstructionsF64()": "hasVInstructionsF64",
        "ST.hasVInstructionsI64()": "hasVInstructionsI64",
        "ST.hasVendorXTHeadBb()": "hasVendorXTHeadBb",
        "ST.is64Bit()": "is64Bit",
        "STI.hasStdExtZbb()": "subtargetInfoHasZbb",
        "XLen <= ST.getELen()": "XLen_le_ELen",
    },
}


# ---------------------------------------------------------------------------
# Lexing helpers
# ---------------------------------------------------------------------------

def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return [re.sub(r"//.*$", "", line) for line in text.splitlines()]


def split_ternary(text):
    """Split a top-level `C ? A : B`; None when the `?` is nested."""
    depth = 0
    for i, c in enumerate(text):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "?" and depth == 0:
            depth = 0
            for j in range(i + 1, len(text)):
                d = text[j]
                if d in "([{":
                    depth += 1
                elif d in ")]}":
                    depth -= 1
                elif d == ":" and depth == 0:
                    return text[:i], text[i + 1:j], text[j + 1:]
            return None
    return None


def split_top(text, sep=","):
    """Split at top level, honouring (), [], {} and string literals."""
    parts, depth, cur, instr = [], 0, [], False
    for c in text:
        if instr:
            cur.append(c)
            if c == '"':
                instr = False
        elif c == '"':
            instr = True
            cur.append(c)
        elif c in "([{":
            depth += 1
            cur.append(c)
        elif c in ")]}":
            depth -= 1
            cur.append(c)
        elif c == sep and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def take_call(text, i):
    """`name(...)` starting at i; returns (name, args, end) or None."""
    m = re.match(r"([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\(", text[i:])
    if not m:
        return None
    name = m.group(1)
    j = i + m.end()
    depth, start = 1, j
    while j < len(text) and depth:
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
        j += 1
    return name, text[start:j - 1], j


# ---------------------------------------------------------------------------
# LLT expressions  ->  `type` declarations
# ---------------------------------------------------------------------------

BUILTIN_LLT = {
    "LLT::scalar": "s", "LLT::integer": "i",
    "LLT::bfloat16()": "bf16", "LLT::float16()": "f16",
    "LLT::float32()": "f32", "LLT::float64()": "f64",
}


class Types:
    """C++ LLT constants found in the constructor."""

    def __init__(self):
        self.decl = []          # [(cpp name, emitted name, rhs text)]
        self.sets = {}          # cpp name -> [cpp type names]
        self.by_cpp = {}        # cpp name -> emitted name
        self.refused = []

    def name(self, cpp):
        if cpp in self.by_cpp:
            return self.by_cpp[cpp]
        canon = "?" + _norm(cpp).replace(PREFIX, "")
        if canon in self.by_cpp:
            return self.by_cpp[canon]
        m = re.fullmatch(r"LLT::scalar\(\s*(\d+)\s*\)", cpp.strip())
        if m and "s%s" % m.group(1) in self.by_cpp:
            return self.by_cpp["s%s" % m.group(1)]
        m = re.fullmatch(r"LLT::fixed_vector\(\s*(\d+)\s*,\s*LLT::scalar"
                         r"\(\s*(\d+)\s*\)\s*\)", cpp.strip())
        if m and "v%ss%s" % (m.group(1), m.group(2)) in self.by_cpp:
            return self.by_cpp["v%ss%s" % (m.group(1), m.group(2))]
        m = split_ternary(cpp.strip())
        if m:
            # `(cond) ? T : F` -> a named `select` declaration (the backends
            # resolve type values through names, not inline expressions).
            self.anon = getattr(self, "anon", [])
            self.preds = getattr(self, "preds", [])
            key = _norm(cpp).replace(PREFIX, "")
            named = SELECT_NAMES.get(CURRENT_TARGET, {}).get(key)
            cond = self.cond_fn(m[0].strip())
            cond = re.sub(r'feature\("((?:[^"\\]|\\.)*)"\)',
                          lambda k: self.feat_name(k.group(1)), cond)
            if named:
                USED_RENAMES["select"].add(key)
                sel_suffix, pred_suffix = named
                name = PREFIX + sel_suffix
            else:
                self.unnamed = getattr(self, "unnamed", 0) + 1
                sel_suffix = pred_suffix = None
                name = PREFIX + "sel%d" % getattr(self, "sel_n", 0)
                self.sel_n = getattr(self, "sel_n", 0) + 1
            lo = self.name(m[1].strip())
            hi = self.name(m[2].strip())
            # A bare condition is already a feature/pred name; the `select`
            # grammar accepts it directly, so no `pred` alias is needed.
            if re.fullmatch(r"[A-Za-z_]\w*", cond):
                self.anon.append((name, cond, lo, hi))
            else:
                pname = PREFIX + pred_suffix if pred_suffix \
                    else PREFIX + "cond%d" % len(self.preds)
                self.preds.append((pname, cond))
                self.anon.append((name, pname, lo, hi))
            self.by_cpp[cpp.strip()] = name
            self.by_cpp[canon] = name
            return name
        return cpp

    def elem_of(self, cpp):
        """Element type of a vector LLT constant -> its `.gisel` type name."""
        name = self.name(cpp)
        for pat, repl in ((r"(?:nxv|v)(\d+)(s|i|f)(\d+)", r"\2\3"),
                          (r"(?:nxv|v)(\d+)p0", "p0"),
                          (r"(?:nxv|v)(\d+)bf16", "bf16")):
            m = re.fullmatch(re.escape(PREFIX) + pat, name)
            if m:
                return PREFIX + re.sub(r"\\(\d)", lambda k: m.group(
                    int(k.group(1))), repl)
        raise Refuse("element type of %r" % cpp)

    def translate_refs(self, expr):
        """Rewrite C++ local type names to their `.gisel` names."""
        def sub(m):
            word = m.group(0)
            return self.by_cpp.get(word, word)
        return re.sub(r"\b[A-Za-z_]\w*\b", sub, expr)

    def add(self, cpp_name, rhs, line):
        emitted = PREFIX + cpp_name
        text = self.translate_refs(rhs)
        if split_ternary(text.strip()):
            # `cond ? A : B` -> a named `select` (same as a reference site).
            self.by_cpp[cpp_name] = self.name(text)
            return
        # LLT::scalar(XLen) / 2*XLen: a feature-dependent width.  The named
        # form is a select over the two legal values.
        m = re.fullmatch(r"LLT::(?:scalar|integer)\(\s*(.+?)\s*\)", text, re.S)
        if m:
            inner = m.group(1)
            if re.fullmatch(r"\d+", inner):
                pass
            else:
                pick = self._width_select(inner)
                if pick is None:
                    self.refused.append((line, "type %s: cannot normalize %r"
                                         % (cpp_name, rhs)))
                    return
                lo, hi = pick
                kind = "scalar" if text.startswith("LLT::scalar") else "integer"
                self._declare_pair(cpp_name, kind, lo, hi)
                return
        self.by_cpp[cpp_name] = emitted
        self.decl.append((cpp_name, emitted, text))

    def _width_select(self, expr):
        """`XLen`, `2 * XLen` -> the (rv32, rv64) literal pair."""
        e = expr.replace(" ", "")
        if e == "XLen":
            return 32, 64
        if e in ("2*XLen", "XLen*2"):
            return 64, 128
        return None

    def _declare_pair(self, cpp_name, kind, lo, hi):
        emitted = PREFIX + cpp_name
        base = PREFIX + "sel" + cpp_name
        self.by_cpp["__lo_" + cpp_name] = "%s_lo" % emitted
        self.by_cpp["__hi_" + cpp_name] = "%s_hi" % emitted
        self.decl.append((None, "%s_lo" % emitted, "LLT::%s(%d)" % (kind, lo)))
        self.decl.append((None, "%s_hi" % emitted, "LLT::%s(%d)" % (kind, hi)))
        self.by_cpp[cpp_name] = emitted
        self.selects = getattr(self, "selects", [])
        self.selects.append((emitted, emitted + "_lo", emitted + "_hi"))


# ---------------------------------------------------------------------------
# Predicates and value expressions
# ---------------------------------------------------------------------------

ORDERINGS = {"Unordered": "ordering_unordered",
             "Monotonic": "ordering_monotonic",
             "Acquire": "ordering_acquire",
             "Release": "ordering_release",
             "AcquireRelease": "ordering_acquire_release",
             "SequentiallyConsistent": "ordering_sequentially_consistent"}


def _fold_pow2ceil(text):
    """`1u << Log2_32_Ceil(x)` -> `pow2_ceil(x)` (balanced args)."""
    out, i = [], 0
    while True:
        j = text.find("Log2_32_Ceil(", i)
        if j < 0:
            out.append(text[i:])
            return "".join(out)
        k = j + len("Log2_32_Ceil")
        end = match_paren(text, k)
        prefix, arg = text[i:j], text[k + 1:end - 1]
        m = re.search(r"1u?\s*<<\s*$", prefix)
        if not m:
            out.append(text[i:end])
        else:
            out.append(prefix[:m.start()])
            out.append("pow2_ceil(%s)" % arg)
        i = end


def _binop_at(text, ops):
    depth = 0
    for i, c in enumerate(text):
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif depth == 0 and c in ops:
            return i, c
    return -1, None


def _arith(text):
    """C++ integer arithmetic the DSL spells as `mul`/`urem`/`pow2_ceil`."""
    text = re.sub(r"\b(\d+)[uUlL]+\b", r"\1", text)   # `1u`, `8LL`, ...
    text = _fold_pow2ceil(text)
    for _ in range(8):
        i, c = _binop_at(text, "*%")
        if i < 0:
            break
        lhs, rhs = text[:i].strip(), text[i + 1:].strip()
        j, _c = _binop_at(rhs, "*%")
        if j >= 0:
            rhs, rest = rhs[:j].strip(), rhs[j:]
        else:
            rest = ""
        text = "%s(%s, %s)%s" % ("mul" if c == "*" else "urem", lhs, rhs, rest)
    return text


def _ordering(name):
    return ORDERINGS.get(name, "ordering_" + re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower())


class Translator:
    """C++ predicate/value text -> `.gisel` text.  Raises Refuse."""

    def __init__(self, types):
        self.t = types
        self.features = {}      # cpp text -> feature name
        self.feature_aliases = {}   # cpp bool variable -> feature name
        self.opcode = None
        self.helpers = {}       # static LegalityPredicate helpers
        self.aligns = {}        # align lambdas: name -> (cond, then, else)
        self.named_preds = {}   # LegalityPredicate variables
        self.refused = []

    # -- features: any `ST.x()` / `XLen == N` becomes a named feature --------
    def feature(self, cpp_text):
        name = cpp_text
        if name not in self.features:
            key = _norm(cpp_text)
            suffix = FEATURE_NAMES.get(CURRENT_TARGET, {}).get(key)
            if suffix:
                USED_RENAMES["feature"].add(key)
            else:
                suffix = re.sub(r"[^0-9A-Za-z]+", "_", cpp_text).strip("_")
            self.features[name] = PREFIX + suffix
        return self.features[name]

    def feature_named(self, name, cpp_text):
        self.features[cpp_text] = PREFIX + name
        return PREFIX + name

    def pred(self, text):
        text = text.strip()
        if text.startswith("LegalityPredicate(") and text.endswith(")"):
            return self.pred_lambda(text)
        if re.match(r"\[[^\]]*\]\s*\(", text):
            return self.pred_lambda(text)
        text = " ".join(text.split())
        text = re.sub(r"\bQ\.", "Query.", text)
        if text in self.feature_aliases:
            return self.feature_aliases[text]
        if self._single_call(text) and re.fullmatch(r"(slot|elem_of|scalar_of|sort_of|num_elems|bits_of|size_of|"
                        r"size_in_bytes_of|addr_space|align_of|mem_ty|mem_slot|"
                        r"mem_ordering|mem_failure_ordering|is_pow2|is_float16|"
                        r"is_bfloat16|is_byte_sized|imm|ty|int_of_size|urem|udiv|mul|"
                        r"select|replace|scalar_or_vec_of|vec_of|elt_type_to|"
                        r"elt_size_to|div_lanes|pow2_ceil|same_as|pow2|pow2_min|"
                        r"multiple_of|clamp|clamp_min|clamp_max|min_vector_size)\s*\(.*\)",
                        text) and "Query." not in text:
            return text
        if text in ("always", "true"):
            return "true"
        if text in ("never", "false"):
            return "not true"
        if text in self.features:
            return self.features[text]
        if text in self.named_preds:
            return "(%s)" % self.named_preds[text]
        if text.startswith("(") and text.endswith(")") and self._balanced(text[1:-1]):
            return self.pred(text[1:-1])
        for op, kw in (("||", "or"), ("&&", "and")):
            parts = self._split_op(text, op)
            if len(parts) > 1:
                return "(" + (" %s " % kw).join(self.pred(p) for p in parts) + ")"
        if text.startswith("!"):
            return "not " + self.pred(text[1:])
        m = re.fullmatch(r"(.+?)\s*(==|!=)\s*AtomicOrdering::NotAtomic", text)
        if m:
            # NotAtomic is the bottom of the ordering lattice, and the DSL has
            # no tag for it: `!= NotAtomic` is `>= Unordered`.
            lhs = self.pred(m.group(1))
            return "%s %s ordering_unordered" % (
                lhs, ">=" if m.group(2) == "!=" else "<")
        text = re.sub(r"AtomicOrdering::(\w+)",
                      lambda m: _ordering(m.group(1)), text)
        text = re.sub(r"isPowerOf2_\d+\(|isPowerOf2\(", "is_pow2(", text)
        m = re.fullmatch(r"(?:::)?(all|any)\s*\((.*)\)", text, re.S)
        if m:
            parts = split_top(m.group(2))
            kw = "and" if m.group(1) == "all" else "or"
            return "(" + (" %s " % kw).join(self.pred(p) for p in parts) + ")"
        m = re.fullmatch(r"LegalityPredicates::(all|any)\s*\((.*)\)", text, re.S)
        if m:
            parts = split_top(m.group(2))
            kw = "and" if m.group(1) == "all" else "or"
            return "(" + (" %s " % kw).join(self.pred(p) for p in parts) + ")"
        # `typeIs(0, s32)(Query)`: the query is implicit in a `.gisel` rule.
        m = re.fullmatch(r"(.+\S)\s*\((?:Query|Q)\)", text, re.S)
        if m:
            return self.pred(m.group(1))
        # `x.isVector() != y.isVector()` is an xor over two predicates.
        m = re.fullmatch(r"(.+?)\.isVector\(\)\s*!=\s*(.+?)\.isVector\(\)",
                         text, re.S)
        if m:
            a = self.pred("%s.isVector()" % m.group(1))
            b = self.pred("%s.isVector()" % m.group(2))
            return "((%s and not %s) or (not %s and %s))" % (a, b, a, b)
        text = self._contained_braces(text)
        m = re.fullmatch(r"llvm::is_contained\(\s*(\w+)\s*,\s*(.+)\)", text, re.S)
        if m:
            return "in(%s, %s)" % (self.expr_text(m.group(2)), PREFIX + m.group(1))
        m = re.fullmatch(r"TM\s*\.\s*getCodeModel\(\)\s*==\s*CodeModel::(\w+)", text)
        if m:
            return self.feature_named(m.group(1) + "CodeModel", text)
        m = self._factory_pred(text)
        if m is not None:
            return m
        # Predicates that name a slot by a constructor variable: fold it first.
        text = re.sub(r"\(\s*(\w+)\s*,", lambda m: "(%s," % (
            m.group(1) if m.group(1).isdigit() else self.slot_index(m.group(1))
        ) if not m.group(1).isdigit() else m.group(0), text)
        for pat, body in (
                (r"sizeIs\s*\(\s*(\d+)\s*,\s*(\d+)\)", r"size_of(slot(\1)) == \2"),
                (r"immIs\s*\(\s*(\d+)\s*,\s*(-?\d+)\)", r"imm(\1) == \2"),
                (r"immInSet\s*\(\s*(\d+)\s*,\s*\{(.*)\}\)", r"in(imm(\1), [\2])"),
                (r"isScalar\s*\(\s*(\d+)\s*\)", r"sort_of(slot(\1)) == scalar"),
        ):
            m = re.fullmatch(pat, text, re.S)
            if m:
                out = re.sub(r"\\(\d)", lambda k: m.group(int(k.group(1))), body)
                return self._types_in_pred(out)
        # A subtarget read (or XLen) compared with a constant is one opaque
        # configuration axis.  Splitting it into `select(feature, ...) == k`
        # would still evaluate correctly, but the feature name is what the
        # `.inc` gates on, so keep it named.
        if re.fullmatch(r"(?:(?:ST|STI)\.\w+\(\)|XLen)\s*(?:==|!=|<=|>=|<|>)\s*"
                        r"(?:\d+|(?:ST|STI)\.\w+\(\)|XLen)", text):
            return self.feature(text)
        cmp = self._split_cmp(text)
        if cmp is not None:
            lhs, op, rhs = cmp
            return "%s %s %s" % (self.expr_text(lhs), op, self.expr_text(rhs))
        local = self.local_pred(text)
        if local is not None:
            return local
        # Subtarget reads and XLen comparisons are cached features.
        if re.fullmatch(r"(ST|STI)\.\w+\(\)", text) or \
                re.fullmatch(r"XLen\s*==\s*\d+", text):
            return self.feature(text)
        if "Query." in text:
            return self.query_body(text)
        raise Refuse(text)

    @staticmethod
    def _single_call(text):
        """True when `text` is one `name(...)` call and nothing else.

        The pass-through regexes use greedy `.*`, so `bits_of(x) != 0 or y`
        also matched them; that silently left `||`/`&&` in the output.
        """
        i = text.find("(")
        if i <= 0 or not re.fullmatch(r"[A-Za-z_]\w*", text[:i].strip()):
            return False
        try:
            return match_paren(text, i) == len(text)
        except Refuse:
            return False

    def _contained_braces(self, text):
        """`llvm::is_contained({v8s8, ...}, DstTy)` (a braced list) -> `in`."""
        key = "llvm::is_contained("
        out, i = [], 0
        while True:
            j = text.find(key, i)
            if j < 0:
                out.append(text[i:])
                return "".join(out)
            k = j + len(key) - 1
            end = match_paren(text, k)
            args = split_top(text[k + 1:end - 1])
            out.append(text[i:j])
            if len(args) == 2 and args[0].strip().startswith("{"):
                items = split_top(args[0].strip()[1:-1].strip())
                if all(re.fullmatch(r"-?\d+", i) for i in items):
                    # An int set only tests an `imm`; for an observation spell
                    # it out as the disjunction the C++ is doing.
                    x = args[1].strip()
                    out.append("(%s)" % " or ".join(
                        "%s == %s" % (x, i) for i in items))
                else:
                    out.append("in(%s, [%s])" % (
                        args[1].strip(),
                        ", ".join(self.t.name(x) for x in items)))
            else:
                out.append(text[j:end])
            i = end

    def _factory_pred(self, text):
        """Predicate factories from `LegalizerInfo.h` -> core predicates."""
        def idx(m):
            return self.slot_index(m.group(1))

        m = re.fullmatch(r"typeIs\s*\(\s*(\w+)\s*,\s*(.+)\)", text, re.S)
        if m:
            return "in(slot(%s), %s)" % (idx(m), self.t.name(m.group(2)))
        m = re.fullmatch(r"typeIsNot\s*\(\s*(\w+)\s*,\s*(.+)\)", text, re.S)
        if m:
            return "not in(slot(%s), %s)" % (idx(m), self.t.name(m.group(2)))
        m = re.fullmatch(r"typeInSet\s*\(\s*(\w+)\s*,\s*\{(.*)\}\)", text, re.S)
        if m:
            return "in(slot(%s), [%s])" % (
                idx(m), ", ".join(self.t.name(x) for x in split_top(m.group(2))))
        m = re.fullmatch(r"typePairInSet\s*\(\s*(\w+)\s*,\s*(\w+)\s*,"
                         r"\s*\{(.*)\}\)", text, re.S)
        if m:
            rows = [split_top(r[1:-1]) for r in split_top(m.group(3))]
            return "in_pairs(slot(%s), slot(%s), [%s])" % (
                idx(m), self.slot_index(m.group(2)),
                ", ".join("[" + ", ".join(self.t.name(x) for x in r) + "]"
                          for r in rows))
        m = re.fullmatch(r"(is\w+)\s*\(\s*(\w+)\s*\)", text)
        if m:
            what = {"isScalar": "scalar", "isVector": "vector",
                    "isScalableVector": "scalable_vector",
                    "isPointer": "pointer",
                    "isPointerVector": "pointer_vector"}.get(m.group(1))
            i = self.slot_index(m.group(2))
            if what == "vector":
                return "sort_of(slot(%s)) == vector" % i
            if what:
                return "sort_of(slot(%s)) == %s" % (i, what)
        m = re.fullmatch(r"elementTypeIs\s*\(\s*(\w+)\s*,\s*(.+)\)", text, re.S)
        if m:
            i, ty = idx(m), self.t.name(m.group(2))
            return ("(sort_of(slot(%s)) == vector and elem_of(slot(%s)) == ty(%s))"
                    % (i, i, ty))
        for name, op in (("scalarNarrowerThan", "<"), ("scalarWiderThan", ">")):
            m = re.fullmatch(r"%s\s*\(\s*(\w+)\s*,\s*(.+)\)" % name, text, re.S)
            if m:
                return "(sort_of(slot(%s)) == scalar and size_of(slot(%s)) %s %s)" % (
                    idx(m), idx(m), op, self.expr_text(m.group(2)))
        for name, op in (("scalarOrEltNarrowerThan", "<"),
                         ("scalarOrEltWiderThan", ">")):
            m = re.fullmatch(r"%s\s*\(\s*(\w+)\s*,\s*(.+)\)" % name, text, re.S)
            if m:
                return "bits_of(slot(%s)) %s %s" % (idx(m), op,
                                                    self.expr_text(m.group(2)))
        m = re.fullmatch(r"scalarOrEltSizeNotPow2\s*\(\s*(\w+)\s*\)", text)
        if m:
            return "not is_pow2(bits_of(slot(%s)))" % idx(m)
        for name, op in (("smallerThan", "<"), ("largerThan", ">")):
            m = re.fullmatch(r"%s\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)" % name, text)
            if m:
                return "size_of(slot(%s)) %s size_of(slot(%s))" % (
                    idx(m), op, self.slot_index(m.group(2)))
        m = re.fullmatch(r"sizeNotMultipleOf\s*\(\s*(\w+)\s*,\s*(.+)\)",
                         text, re.S)
        if m:
            return ("(sort_of(slot(%s)) == scalar and urem(size_of(slot(%s)), %s) != 0)"
                    % (idx(m), idx(m), self.expr_text(m.group(2))))
        m = re.fullmatch(r"atomicOrderingAtLeastOrStrongerThan\s*\(\s*(\w+)"
                         r"\s*,\s*(?:AtomicOrdering::)?(\w+)\s*\)", text)
        if m:
            name = m.group(2)
            if not name.startswith("ordering_"):
                name = _ordering(name)
            return "mem_ordering(mem_slot(%s)) >= %s" % (idx(m), name)
        return None

    # -- mutations -------------------------------------------------------
    def mutation(self, text):
        """`changeTo(i, T)` / `LegalizeMutations::changeTo(i, T)`.

        `changeTo` selects a specific type, so it is `replace(...)` in the DSL:
        the bare `widen(slot, ty)` form keeps the lane count and only moves the
        element size, which is a different mutation.
        """
        text = text.strip()
        m = re.fullmatch(r"(?:LegalizeMutations::)?changeTo\s*\(\s*(\d+)\s*,"
                         r"\s*(.+)\)", text, re.S)
        if not m:
            raise Refuse(text)
        return "slot(%s), replace(%s)" % (m.group(1), self._mut_ty(m.group(2)))

    def _mut_ty(self, text):
        """`changeTo(i, j)`'s numeric form means "the type of slot j"."""
        text = text.strip()
        if re.fullmatch(r"\d+", text):
            return "same_as(%s)" % text
        return "ty(%s)" % self.t.name(text)

    def mutation_lambda(self, text):
        """`bitcastIf`'s new-type lambda -> a `.gisel` type expression."""
        body = re.sub(r"\bQ\.", "Query.", text)
        aliases = dict(re.findall(
            r"(?:const\s+)?LLT\s*&?\s*(\w+)\s*=\s*(Query\.Types\[\d+\]);", body))
        for var, val in aliases.items():
            body = re.sub(r"\b%s\b" % var, val, body)
        m = re.search(r"LLT::vector\(\s*Query\.Types\[(\d+)\]\.getElementCount"
                      r"\(\)\.divideCoefficientBy\((\d+)\)\s*,\s*(\d+)\s*\)", body)
        if m:
            return ("slot(%s), replace(elt_type_to(div_lanes(slot(%s), %s), ty(%s)))"
                    % (m.group(1), m.group(1), m.group(2),
                       self.t.name("s%s" % m.group(3))))
        m = re.search(r"(?:std::)?(?:make_pair|pair(?:<[^>]*>)?)\s*\(?\s*(\d+)\s*,"
                      r"\s*(.+?)\s*\)?\s*;", body, re.S)
        if m:
            idx, ty = m.group(1), m.group(2).strip()
            mm = re.fullmatch(r"LLT::integer\(\s*(.+?)\.getSizeInBits\(\)\s*\)", ty, re.S)
            if mm:
                return "slot(%s), replace(int_of_size(size_of(slot(%s))))" % (
                    idx, idx)
            mm = re.fullmatch(r"(.+?)\.divide\(\s*(\d+)\s*\)", ty, re.S)
            if mm:
                src = re.fullmatch(r"Query\.Types\[(\d+)\]", mm.group(1).strip())
                if src:
                    return "slot(%s), replace(div_lanes(slot(%s), %s))" % (
                        idx, src.group(1), mm.group(2))
            mm = re.fullmatch(r"LLT::vector\(\s*(.+?)\s*,\s*LLT::integer"
                              r"\(\s*(\d+)\s*\)\s*\)", ty, re.S)
            if mm:
                return "slot(%s), replace(vec_of(%s, ty(%s)))" % (
                    idx, self.count_expr(mm.group(1)),
                    self.t.name("LLT::scalar(%s)" % mm.group(2)))
            mm = re.fullmatch(r"LLT::fixed_vector\(\s*(.+?)\s*,\s*(.+?)\s*\)",
                              ty, re.S)
            if mm:
                lanes = self.int_expr(mm.group(1))
                em = re.fullmatch(r"Query\.Types\[(\d+)\]", mm.group(2).strip())
                elt = ("slot(%s)" % em.group(1) if em
                       else "ty(%s)" % self.t.name(mm.group(2)))
                return "slot(%s), replace(vec_of(%s, %s))" % (idx, lanes, elt)
            mm = re.fullmatch(
                r"Query\.Types\[(\d+)\]\.changeElementSize\(\s*"
                r"Query\.Types\[(\d+)\]\.getSizeInBits\(\)\s*\)\s*"
                r"\.changeElementCount\(\s*Query\.Types\[\1\]"
                r"\.getElementCount\(\)\s*\.divideCoefficientBy\(\s*"
                r"Query\.Types\[(\d+)\]\.getNumElements\(\)\s*\)\s*\)",
                ty, re.S)
            if mm:
                # dst: element size := src's total bits, lanes := dst/src.
                return ("slot(%s), replace(elt_size_to(div_lanes(slot(%s),"
                        " num_elems(slot(%s))), size_of(slot(%s))))"
                        % (idx, mm.group(1), mm.group(3), mm.group(2)))
            mm = re.fullmatch(r"LLT::integer\(\s*(\d+)\s*\)", ty)
            if mm:
                return "slot(%s), ty(%s)" % (
                    idx, self.t.name("LLT::scalar(%s)" % mm.group(1)))
            return "slot(%s), replace(%s)" % (idx, self._mut_ty(ty))
        raise Refuse("bitcast lambda %r" % text[:60])

    def count_expr(self, text):
        """`Query.Types[k].getElementCount()` -> `num_elems(slot(k))`."""
        text = text.strip()
        m = re.fullmatch(r"(?:Query\.)?Types\[(\d+)\]\.get(?:ElementCount|NumElements)"
                         r"\(\)", text)
        if m:
            return "num_elems(slot(%s))" % m.group(1)
        m = re.fullmatch(r"(?:Query\.Types\[(\d+)\]|(\w+))", text)
        if m:
            i = m.group(1) or m.group(2)
            return "num_elems(%s)" % ("slot(%s)" % i if m.group(1)
                                      else "ty(%s)" % self.t.name(i))
        return self.int_expr(text)

    # -- local LegalityPredicate helpers ---------------------------------
    def local_pred(self, text):
        """Inline a `static LegalityPredicate F(...)` helper."""
        m = re.fullmatch(r"(\w+)\s*\((.*)\)", text.strip(), re.S)
        if not m or m.group(1) not in self.helpers:
            return None
        tmpl = self.helpers[m.group(1)]
        call = split_top(m.group(2))
        if len(call) != len(tmpl["params"]):
            raise Refuse(text)
        sub = dict(zip(tmpl["params"], call))
        idx = _subst(tmpl["idx"], sub)
        typeset = _subst(tmpl["set"], sub)
        elems = self.t.sets.get(typeset) or [typeset]
        body = tmpl["body"]
        for p in tmpl["params"]:
            body = re.sub(r"\b%s\b" % re.escape(p), sub[p], body)
        pred = self.query_body(body)
        return "(in(slot(%s), [%s]) and %s)" % (
            idx, ", ".join(self.t.name(e) for e in elems), pred)

    def query_body(self, body):
        """A `Query.Types[...]` lambda body -> a `.gisel` predicate."""
        body = re.sub(r"\bQ\.", "Query.", body)
        out = []
        for chunk in re.split(r"(Query\.Types\[[^\]]+\])", body):
            m = re.fullmatch(r"Query\.Types\[(.+)\]", chunk)
            if m:
                out.append("__T(%s)" % m.group(1).strip())
            else:
                out.append(chunk)
        text = "".join(out)
        text = re.sub(r"Query\.MMODescrs\[(\d+)\]\.MemoryTy", r"MEM(\1)", text)
        text = re.sub(r"Query\.MMODescrs\[(\d+)\]\.Ordering", r"ORD(\1)", text)
        m = re.fullmatch(r"(.+?)\s*(==|!=)\s*AtomicOrdering::NotAtomic", text)
        if m:
            # NotAtomic is the bottom of the ordering lattice, and the DSL has
            # no tag for it: `!= NotAtomic` is `>= Unordered`.
            lhs = self.pred(m.group(1))
            return "%s %s ordering_unordered" % (
                lhs, ">=" if m.group(2) == "!=" else "<")
        text = re.sub(r"AtomicOrdering::(\w+)",
                      lambda m: _ordering(m.group(1)), text)
        text = re.sub(r"isPowerOf2_32\(", "is_pow2(", text)
        text = re.sub(r"MEM\((\d+)\)", r"mem_ty(mem_slot(\1))", text)
        text = re.sub(r"mem_ty\(mem_slot\((\d+)\)\)\.getSizeInBits\(\)",
                      r"size_of(mem_ty(mem_slot(\1)))", text)
        text = re.sub(r"ORD\((\d+)\)", r"mem_ordering(mem_slot(\1))", text)
        for pat, rep in (
                (r"__T\((.+?)\)\.getScalarType\(\)\.isFloat16\(\)",
                 r"is_float16(scalar_of(slot(\1)))"),
                (r"__T\((.+?)\)\.getScalarType\(\)\.isBFloat16\(\)",
                 r"is_bfloat16(scalar_of(slot(\1)))"),
                (r"__T\((.+?)\)\.getScalarSizeInBits\(\)", r"bits_of(slot(\1))"),
                (r"__T\((.+?)\)\.getElementCount\(\)\.getKnownMinValue\(\)",
                 r"num_elems(slot(\1))"),
                (r"__T\((.+?)\)\.getElementCount\(\)\.getFixedValue\(\)",
                 r"num_elems(slot(\1))"),
                (r"__T\((.+?)\)\.getNumElements\(\)", r"num_elems(slot(\1))"),
                (r"__T\((.+?)\)\.getSizeInBits\(\)", r"size_of(slot(\1))"),
                (r"__T\((.+?)\)\.getElementType\(\)", r"elem_of(slot(\1))"),
                (r"__T\((.+?)\)\.getAddressSpace\(\)", r"addr_space(slot(\1))"),
                (r"__T\((.+?)\)\.isScalableVector\(\)",
                 r"sort_of(slot(\1)) == scalable_vector"),
                (r"__T\((.+?)\)\.isFixedVector\(\)",
                 r"(sort_of(slot(\1)) == vector and not sort_of(slot(\1)) == scalable_vector)"),
                (r"__T\((.+?)\)\.isPointerVector\(\)",
                 r"sort_of(slot(\1)) == pointer_vector"),
                (r"__T\((.+?)\)\.isPointer\(\)", r"sort_of(slot(\1)) == pointer"),
                (r"__T\((.+?)\)\.isVector\(\)", r"sort_of(slot(\1)) == vector"),
                (r"__T\((.+?)\)\.isScalar\(\)", r"sort_of(slot(\1)) == scalar"),
                (r"__T\((.+?)\)", r"slot(\1)"),
        ):
            text = re.sub(pat, rep, text)
        text = re.sub(r"LLT::scalar\(\s*(\d+)\s*\)", r"s\1", text)
        text = re.sub(r"LLT::fixed_vector\(\s*(\d+)\s*,\s*LLT::scalar\(\s*(\d+)\s*\)\s*\)",
                      r"v\1s\2", text)
        text = re.sub(r"LLT::pointer\(\s*(\d+)\s*,\s*(\d+)\s*\)", r"p\1:\2", text)
        text = re.sub(r"\bslot\(\s*(\w+)\s*\)",
                      lambda m: "slot(%s)" % self.slot_index(m.group(1)), text)
        m = re.fullmatch(r"(.+?)\s*&\s*(\d+)\s*", text, re.S)
        if m:
            # `x & 1` used as a boolean: C++ says "odd".
            if int(m.group(2)) != 1:
                raise Refuse("bit test %r" % text)
            return "(urem(%s, 2) != 0)" % m.group(1).strip()
        if "&&" in text or "||" in text or text.startswith("!"):
            return self.pred(text)
        cmp = self._split_cmp(text)
        if cmp is not None:
            lhs, op, rhs = cmp
            return "%s %s %s" % (_arith(lhs.strip()), op, _arith(rhs.strip()))
        return _arith(text)

    # -- align helpers ---------------------------------------------------
    def align_variants(self, text):
        """`getScalarMemAlign(n)` -> [(gate, integer), ...], mutually exclusive."""
        m = re.fullmatch(r"(\w+)\s*\((.*)\)", text.strip(), re.S)
        if not m or m.group(1) not in self.aligns:
            raise Refuse("memdesc align %r" % text)
        param, cond, a, b = self.aligns[m.group(1)]
        arg = m.group(2).strip()
        if param:
            a = re.sub(r"\b%s\b" % re.escape(param), arg, a)
            b = re.sub(r"\b%s\b" % re.escape(param), arg, b)
        gate = self.pred(cond)
        out = []
        for g, val, neg in ((gate, a, False), ("not " + gate, b, True)):
            if re.fullmatch(r"-?\d+", val.strip()):
                out.append((None if not neg and val == b and val == a else g,
                            int(val)))
            elif val.strip() == "XLen":
                out.append(("%s and %s" % (g, self.pred("XLen == 64")), 64))
                out.append(("%s and %s" % (g, self.pred("XLen == 32")), 32))
            else:
                if not re.fullmatch(r"-?\d+", arg):
                    raise Refuse("memdesc align %r" % text)
                out.append((g, int(arg)))
        # `getScalarMemAlign(8)` is 8 either way: drop the gates.
        if all(v == out[0][1] for _, v in out):
            return [(None, out[0][1])] * 1 if False else [(None, out[0][1])]
        return out

    def slot_index(self, name):
        name = name.strip()
        if re.fullmatch(r"-?\d+", name):
            return name
        env = getattr(self, "env", {})
        v = env.get(name, name)
        if not isinstance(v, int):
            raise Refuse("slot index %r" % name)
        return str(v)

    def int_expr(self, text):
        """A C++ integer constant/expression -> a `.gisel` Int expression."""
        t = text.strip()
        if t.startswith("(") and t.endswith(")") and self._balanced(t[1:-1]):
            return self.int_expr(t[1:-1])
        m = split_ternary(t)
        if m:
            return "select(%s, %s, %s)" % (self.pred(m[0]),
                                           self.int_expr(m[1].strip()),
                                           self.int_expr(m[2].strip()))
        if re.fullmatch(r"-?\d+", t):
            return t
        if t in ("XLen", "ST.getXLen()", "STI.getXLen()"):
            return 'select(%s, 64, 32)' % self.feature("XLen == 64")
        if t.replace(" ", "") in ("2*XLen", "XLen*2"):
            return 'select(%s, 128, 64)' % self.feature("XLen == 64")
        m = re.fullmatch(r"(\w+)\.getNumElements\(\)", t)
        if m:
            return "num_elems(ty(%s))" % self.t.name(m.group(1))
        if t in ("ST.getELen()", "STI.getELen()"):
            return 'select(%s, 64, 32)' % self.feature("ST.getELen() == 64")
        if re.fullmatch(r"[A-Za-z_][\w.()]*", t):
            return 'select(%s, 64, 32)' % self.feature(t)
        raise Refuse(text)

    def expr_text(self, text):
        """One side of a comparison: an int, a type name, or an observation."""
        text = text.strip()
        if split_ternary(text):
            return self.int_expr(text)
        if text in self.features:
            return self.features[text]
        if text in self.named_preds:
            return "(%s)" % self.named_preds[text]
        if re.fullmatch(r"-?\d+", text):
            return text
        if text in ("true", "false") or re.fullmatch(r"ordering_\w+", text):
            return text
        if text in ("XLen", "ST.getXLen()", "STI.getXLen()", "ST.getELen()",
                    "STI.getELen()"):
            return self.int_expr(text)
        m = re.fullmatch(r"(ST|STI)\..+", text)
        if m:
            return self.feature(text)
        if "Query." in text:
            return self.query_body(text)
        if re.fullmatch(r"[A-Za-z_]\w*\s*\(.*\)", text, re.S):
            return text          # already `.gisel` (`bits_of(slot(0))`, ...)
        return "ty(%s)" % self.t.name(text)

    @staticmethod
    def _split_cmp(text):
        depth, i = 0, 0
        while i < len(text):
            c = text[i]
            if c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
            elif depth == 0:
                if text.startswith(("==", "!=", "<=", ">="), i):
                    return text[:i], text[i:i + 2], text[i + 2:]
                if text.startswith(("<<", ">>"), i):
                    i += 2              # shift, not a comparison
                    continue
                if c in "<>":
                    return text[:i], c, text[i + 1:]
            i += 1
        return None

    def pred_lambda(self, text):
        text = text.strip()
        if text.startswith("LegalityPredicate(") and text.endswith(")"):
            return self.pred_lambda(text[len("LegalityPredicate("):-1])
        m = re.match(r"\[.*?\]\s*\((.*?)\)\s*\{(.*)\}$", text, re.S)
        if not m:
            return self.pred(text)
        return self.body_pred(m.group(2))

    def body_pred(self, body):
        """A lambda body of `if (...)` early returns -> one predicate."""
        if self.opcode:
            body = re.sub(r"Query\.Opcode", self.opcode, body)
        stmts = [x.strip() for x in split_statements(body) if x.strip()]
        env, rest = {}, []
        for st in stmts:
            m = re.fullmatch(r"(?:const\s+)?(?:unsigned|int|bool|LLT|auto)\s*&?\s*"
                             r"(\w+)\s*=\s*(.+?);?", st, re.S)
            if m:
                name, val = m.group(1), m.group(2).strip()
                if "Query." not in val:
                    try:
                        env[name] = str(const_eval(val, {}))
                        continue
                    except Refuse:
                        pass
                env[name] = " ".join(val.split())
                continue
            rest.append(st)
        text = "; ".join(x.rstrip(";") for x in rest)
        for _ in range(4):          # names may alias other names
            before = text
            for name, val in env.items():
                text = re.sub(r"\b%s\b" % re.escape(name),
                              lambda _m, v=val: v, text)
            if text == before:
                break
        return self._body_stmts(
            [x.strip() for x in split_statements(text) if x.strip()])

    def _body_stmts(self, stmts):
        if not stmts:
            raise Refuse("empty predicate lambda")
        st = stmts[0].rstrip(";").strip()
        if st.startswith("if"):
            cond, then = self._if_parts(st)
            cond = self.pred(cond)
            rest = self._body_stmts(stmts[1:]) if len(stmts) > 1 else None
            if then in ("return false", "return true"):
                val = "false" if then == "return false" else "true"
                if rest is None:
                    return cond if val == "true" else "not (%s)" % cond
                if val == "false":
                    return "(%s and %s)" % ("not (%s)" % cond, rest)
                return "((%s) or (not (%s) and %s))" % (cond, cond, rest)
            if not then.startswith("return "):
                raise Refuse(st)
            val = self.pred(then[len("return "):])
            if rest is None:
                return "(%s and %s)" % (cond, val)
            return "((%s and %s) or (not (%s) and %s))" % (cond, val, cond, rest)
        if st.startswith("switch"):
            i = st.index("(")
            close = match_paren(st, i) - 1
            body = st[close + 1:].strip()
            tail = ""
            if body.startswith("{"):
                end = match_brace(body, 0)
                st, tail = st[:close + 1] + body[:end], body[end:].strip()
            rest = (([tail] if tail else []) + stmts[1:])
            p = self.switch_pred(st)
            rp = self._body_stmts(rest) if rest else None
            return p if rp is None else "(%s and %s)" % (p, rp)
        if st.startswith("return"):
            expr = st[len("return"):].strip()
            if expr == "true":
                return "true"
            if expr == "false":
                return "not true"
            return self.pred(expr)
        raise Refuse(st)

    @staticmethod
    def _if_parts(st):
        i = st.index("(")
        close = match_paren(st, i) - 1
        cond, rest = st[i + 1:close], st[close + 1:].strip()
        while rest.startswith("{"):
            end = match_brace(rest, 0)
            rest = (rest[1:end - 1].strip() + " " + rest[end:].strip()).strip()
        return " ".join(cond.split()), rest.rstrip(";").strip()

    def switch_pred(self, st):
        """`switch (Q.Types[i].getSizeInBits()) { case N: ... }` -> `in`."""
        i = st.index("(")
        close = match_paren(st, i) - 1
        subject = st[i + 1:close].strip()
        body = st[close + 1:].strip()
        if body.startswith("{"):
            body = body[1:match_brace(body, 0) - 1]
        cases = [int(x) for x in re.findall(r"case\s+(-?\d+)\s*:", body)]
        if not cases:
            raise Refuse(st)
        negate = bool(re.search(r"default:\s*return\s+true", body))
        positive = bool(re.search(r"(return\s+true|break\s*;)", body))
        if negate:
            positive = not positive
        if not positive:
            raise Refuse(st)
        subj = self.pred(subject)
        if subj.startswith("imm("):
            out = "in(%s, [%s])" % (subj, ", ".join(str(c) for c in cases))
        else:
            # An int set only tests an `imm`; the C++ switch is a disjunction.
            out = "(%s)" % " or ".join("%s == %s" % (subj, c) for c in cases)
        return "not " + out if negate else out

    def _types_in_pred(self, out):
        # `in(slot(0), ty(s3))` -> the set/list members are type references
        def sub(m):
            return self.t.name(m.group(0))
        return re.sub(r"\b[A-Za-z_]\w*\b", sub, out)

    @staticmethod
    def _balanced(text):
        depth = 0
        for c in text:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth < 0:
                    return False
        return depth == 0

    @staticmethod
    def _split_op(text, op):
        parts, depth, cur, i = [], 0, [], 0
        while i < len(text):
            c = text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            if depth == 0 and text.startswith(op, i):
                parts.append("".join(cur).strip())
                cur = []
                i += len(op)
                continue
            cur.append(c)
            i += 1
        parts.append("".join(cur).strip())
        return parts


def _subst(text, sub):
    for k, v in sub.items():
        text = re.sub(r"\b%s\b" % re.escape(k), v, text)
    return text


def parse_helpers(source):
    """`static LegalityPredicate F(...) { ... return all(typeInSet(i, S), P); }`"""
    out = {}
    for m in re.finditer(r"static\s+LegalityPredicate\s+(\w+)\s*\((.*?)\)\s*\{(.*?)^\}",
                         source, re.S | re.M):
        name, params, body = m.group(1), m.group(2), m.group(3)
        pm = re.search(r"(\w+)\s*=\s*\[[^\]]*\]\(const LegalityQuery\s*&\s*Query\)"
                       r"\s*\{(.*?)\};", body, re.S)
        rm = re.search(r"return\s+all\s*\(\s*typeInSet\s*\(\s*(\w+)\s*,\s*"
                       r"(\w+)\s*\)\s*,\s*(\w+)\s*\)", body, re.S)
        if not pm or not rm:
            continue
        names = [p.split()[-1].lstrip("&*") for p in split_top(params)]
        body = pm.group(2)
        body = re.sub(r"^\s*return\s+", "", body.strip())
        body = body.strip().rstrip(";")
        out[name] = {"params": names, "idx": rm.group(1), "set": rm.group(2),
                     "body": body}
    return out


def parse_aligns(source):
    """`auto F = [&ST](unsigned Size) { return Cond ? A : B; };`"""
    out = {}
    for m in re.finditer(r"auto\s+(\w+)\s*=\s*\[[^\]]*\]\s*\(([^)]*)\)\s*\{\s*"
                         r"return\s+(.+?)\?(.+?):(.+?);\s*\};", source, re.S):
        param = m.group(2).split()[-1].lstrip("&*") if m.group(2).strip() else ""
        out[m.group(1)] = (param, m.group(3).strip(), m.group(4).strip(),
                           m.group(5).strip())
    return out


class Refuse(Exception):
    pass


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

class Chain:
    def __init__(self, name, opcodes, line):
        self.name = name          # ruleset name
        self.opcodes = opcodes
        self.rules = []           # [(line, text)]
        self.line = line


class Program:
    def __init__(self):
        self.rulesets = []        # [Chain]
        self.by_object = {}       # C++ chain variable -> Chain
        self.refused = []

    def refuse(self, line, why):
        self.refused.append((line, why))


INT_CONST = {}


def const_eval(text, env):
    """Evaluate the constant expressions the constructor uses for indices."""
    text = text.strip()
    if text in env:
        return env[text]
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    m = re.fullmatch(r"(.+?)\s*\?\s*(-?\d+)\s*:\s*(-?\d+)", text, re.S)
    if m:
        cond = const_eval(m.group(1), env)
        if not isinstance(cond, bool) and not isinstance(cond, int):
            raise Refuse(text)      # `XLen ? a : b` is not a compile-time
        return const_eval(m.group(2), env) if cond \
            else const_eval(m.group(3), env)
    m = re.fullmatch(r"(.+?)\s*==\s*(.+)", text, re.S)
    if m:
        a = const_eval(m.group(1), env)
        b = const_eval(m.group(2), env)
        if type(a) is not type(b):
            # `XLen == 64` is a *runtime* subtarget test.  Comparing the
            # spelling "XLen" with 64 would answer False and silently drop
            # the whole `if` body.
            raise Refuse(text)
        return a == b
    if text in env:
        return env[text]
    if re.fullmatch(r"G_\w+", text):
        return text          # an opcode name, not a value
    raise Refuse(text)


def idx_of(text, env):
    """A slot index argument (always a small integer once constants fold)."""
    v = const_eval(text, env)
    if not isinstance(v, int) or isinstance(v, bool):
        raise Refuse("slot index %r" % text)
    return v


def opcodes_of(text, env):
    """`{G_A, G_B}` / `G_A` / `Op` -> ["G_A", "G_B"]."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return [o.strip() for o in split_top(text[1:-1])]
    if text in env:
        return [env[text]]
    if re.fullmatch(r"G_\w+", text):
        return [text]
    raise Refuse(text)


STATS = {"calls": {}, "rules": {}}


def _product(lists):
    out = [[]]
    for xs in lists:
        out = [prev + [x] for prev in out for x in xs]
    return out


ACTIONS = {"legalFor": "legal", "customFor": "custom", "libcallFor": "libcall",
           "lowerFor": "lower", "unsupportedFor": "unsupported"}


def emit_chain_call(tr, p, chain, method, args, line, env=None):
    """One builder call -> zero or more `.gisel` rule lines."""
    args = split_top(args) if args.strip() else []
    env = env or {}
    out = []

    def type_preds(idx, text):
        """A `{t, t}` / `{{a,b}}` / named set -> [(gate, predicate)]."""
        text = text.strip()
        if text.startswith("{"):
            parts = split_top(text[1:-1])
            if parts and all(x.lstrip().startswith("{") for x in parts):
                rows = [split_top(r[1:-1]) for r in parts]
                triples = ["[" + ", ".join(tr.t.name(x) for x in r) + "]"
                           for r in rows]
                arity = len(rows[0])
                if arity == 2:
                    return [(None, "in_pairs(slot(0), slot(1), [%s])"
                             % ", ".join(triples))]
                if arity == 3:
                    return [(None, "in_triples(slot(0), slot(1), slot(2), [%s])"
                             % ", ".join(triples))]
                raise Refuse(text)
            elems = [tr.t.name(x) for x in parts]
            return [(None, "in(slot(%d), [%s])" % (idx, ", ".join(elems)))]
        m = split_ternary(text)
        if m:
            g = tr.pred(m[0])
            return ([(g, t) for _, t in type_preds(idx, m[1].strip())] +
                    [("not " + g, t) for _, t in type_preds(idx, m[2].strip())])
        if text in tr.t.sets:
            return [(None, "in(slot(%d), %s)" % (idx, PREFIX + text))]
        return [(None, "in(slot(%d), %s)" % (idx, tr.t.name(text)))]

    def expand_sets(ref):
        """A cartesian-product operand -> [(gate, [type name])]."""
        ref = ref.strip()
        m = split_ternary(ref)
        if m:
            g = tr.pred(m[0])
            return ([(g, xs) for _, xs in expand_sets(m[1].strip())] +
                    [("not " + g, xs) for _, xs in expand_sets(m[2].strip())])
        if ref.startswith("{"):
            return [(None, [tr.t.name(x) for x in split_top(ref[1:-1])])]
        if ref in tr.t.sets:
            return [(None, [tr.t.name(x) for x in tr.t.sets[ref]])]
        raise Refuse(ref)

    def mutation(text):
        """A `LegalizeMutations::` call or a lambda returning a pair."""
        text = text.strip()
        m = re.fullmatch(r"(?:LegalizeMutations::)?moreElementsToNextPow2"
                         r"\s*\(\s*(\d+)\s*\)", text)
        if m:
            return "slot(%s), pow2" % m.group(1)
        m = re.fullmatch(r"(?:LegalizeMutations::)?fewerElementsToNextPow2"
                         r"\s*\(\s*(\d+)\s*\)", text)
        if m:
            return "slot(%s), pow2" % m.group(1)
        m = re.fullmatch(r"(?:LegalizeMutations::)?changeTo"
                         r"\s*\(\s*(\d+)\s*,\s*(.+)\)", text, re.S)
        if m:
            return "slot(%s), replace(%s)" % (m.group(1), tr._mut_ty(m.group(2)))
        m = re.fullmatch(r"(?:LegalizeMutations::)?changeElementSizeTo"
                         r"\s*\(\s*(\d+)\s*,\s*(.+)\)", text, re.S)
        if m:
            i, arg = m.group(1), m.group(2).strip()
            if re.fullmatch(r"\d+", arg):
                src = "bits_of(slot(%s))" % arg
            else:
                src = "size_of(ty(%s))" % tr.t.name(arg)
            return "slot(%s), replace(elt_size_to(slot(%s), %s))" % (i, i, src)
        m = re.fullmatch(r"(?:LegalizeMutations::)?changeElementTo\s*\(\s*(\d+)"
                         r"\s*,\s*(.+)\)", text, re.S)
        if m:
            i, ty = m.group(1), tr.t.name(m.group(2))
            return "slot(%s), replace(elt_type_to(slot(%s), ty(%s)))" % (i, i, ty)
        m = re.fullmatch(r"(?:LegalizeMutations::)?narrowScalarTo\s*\(\s*(\d+)"
                         r"\s*,\s*(.+)\)", text, re.S)
        if m:
            return "slot(%s), ty(%s)" % (m.group(1), tr.t.name(m.group(2)))
        if text.startswith("["):
            return tr.mutation_lambda(text)
        raise Refuse(text)

    # `legalFor(pred, {..})` / `minScalar(pred, 0, sXLen)`: the predicate is a
    # table-build-time gate, which is exactly what a `when`/`and` already means.
    BASE_ARGS = {"legalFor": 1, "customFor": 1, "libcallFor": 1, "lowerFor": 1,
                 "unsupportedFor": 1, "legalForTypesWithMemDesc": 1,
                 "minScalar": 2, "maxScalar": 2, "clampScalar": 3,
                 "minScalarOrElt": 2, "clampScalarOrElt": 3}
    pred_arg = None
    if method in BASE_ARGS and len(args) == BASE_ARGS[method] + 1:
        pred_arg, args = args[0], args[1:]
    if method.endswith("CartesianProduct") and args:
        head = args[0].lstrip()
        if not (head.startswith("{") or args[0] in tr.t.sets or "?" in args[0]):
            pred_arg, args = args[0], args[1:]
    pg = tr.pred(pred_arg) if pred_arg is not None else None

    def act(op, pred, gate=None):
        gs = [x for x in (pg, gate) if x]
        if gs:
            pred = "(%s and %s)" % (" and ".join(gs), pred)
        return "%s %s" % (op, pred)

    def when(text, gate):
        return text if gate is None else "%s when %s" % (text, gate)

    if method in ACTIONS:
        for g, pred in type_preds(0, args[0]):
            out.append(act(ACTIONS[method], pred, g))
    elif method in ("legalForCartesianProduct", "customForCartesianProduct",
                    "lowerForCartesianProduct"):
        op = {"legalForCartesianProduct": "legal",
              "customForCartesianProduct": "custom",
              "lowerForCartesianProduct": "lower"}[method]
        if len(args) <= 2:
            b_ref = args[1] if len(args) > 1 else args[0]
            for ga, a in expand_sets(args[0]):
                for gb, b in expand_sets(b_ref):
                    rows = [[x, y] for x in a for y in b]
                    pred = "in_pairs(slot(0), slot(1), [%s])" % ", ".join(
                        "[" + ", ".join(r) + "]" for r in rows)
                    out.append(act(op, pred,
                                   " and ".join(x for x in (ga, gb) if x) or None))
        else:
            for combo in _product([expand_sets(a) for a in args]):
                gates = [g for g, _ in combo if g]
                parts = ["in(slot(%d), [%s])" % (i, ", ".join(xs))
                         for i, (_, xs) in enumerate(combo)]
                out.append(act(op, " and ".join(parts),
                               " and ".join(gates) or None))
    elif method in ("legalForTypesWithMemDesc",):
        for g, pred in mem_desc_tables(tr, args[0]):
            out.append(act("legal", pred, g))
    elif method in ("legalIf", "customIf", "lowerIf", "unsupportedIf", "libcallIf"):
        out.append(act(method[:-2], tr.pred_lambda(args[0])))
    elif method in ("lower", "unsupported", "alwaysLegal", "libcall", "custom"):
        out.append({"lower": "lower true", "unsupported": "unsupported true",
                    "alwaysLegal": "legal true", "libcall": "libcall true",
                    "custom": "custom true"}[method])
    elif method == "scalarize":
        out.append("scalarize(slot(%s))" % (idx_of(args[0], env) if args else 0))
    elif method == "scalarizeIf":
        i = idx_of(args[1], env)
        out.append("scalarize(slot(%d)) when %s" % (i, tr.pred_lambda(args[0])))
    elif method == "clampScalar":
        idx = idx_of(args[0], env)
        out.append("widen(slot(%d), ty(%s))" % (idx, tr.t.name(args[1])))
        out.append("narrow(slot(%d), ty(%s))" % (idx, tr.t.name(args[2])))
    elif method == "clampScalarOrElt":
        idx = idx_of(args[0], env)
        out.append("widen(elem_of(slot(%d)), ty(%s))" % (idx, tr.t.name(args[1])))
        out.append("narrow(elem_of(slot(%d)), ty(%s))" % (idx, tr.t.name(args[2])))
    elif method in ("minScalar", "maxScalar"):
        idx = idx_of(args[0], env)
        ty = tr.t.name(args[1])
        out.append("widen(slot(%d), ty(%s))" % (idx, ty)
                   if method == "minScalar" else
                   "narrow(slot(%d), ty(%s))" % (idx, ty))
    elif method == "minScalarOrElt":
        idx = idx_of(args[0], env)
        out.append("widen(elem_of(slot(%d)), ty(%s))" % (idx, tr.t.name(args[1])))
    elif method == "minScalarOrEltIf":
        idx = idx_of(args[1], env)
        out.append("widen(elem_of(slot(%d)), ty(%s)) when %s"
                   % (idx, tr.t.name(args[2]), tr.pred_lambda(args[0])))
    elif method in ("minScalarSameAs", "maxScalarSameAs"):
        a, b = idx_of(args[0], env), idx_of(args[1], env)
        op = "widen" if method == "minScalarSameAs" else "narrow"
        out.append("%s(slot(%d), same_as(%d))" % (op, a, b))
    elif method in ("minScalarEltSameAsIf", "maxScalarEltSameAsIf"):
        a, b = idx_of(args[1], env), idx_of(args[2], env)
        g = tr.pred_lambda(args[0])
        if method == "minScalarEltSameAsIf":
            out.append("widen(slot(%d), same_as(%d)) when %s" % (a, b, g))
        else:
            out.append("narrow(slot(%d), replace(same_as(%d))) when (%s and "
                       "bits_of(slot(%d)) < bits_of(slot(%d)))" % (a, b, g, b, a))
    elif method == "maxScalarIf":
        idx = idx_of(args[1], env)
        out.append("narrow(slot(%d), ty(%s)) when %s"
                   % (idx, tr.t.name(args[2]), tr.pred_lambda(args[0])))
    elif method in ("widenScalarToNextPow2", "widenScalarOrEltToNextPow2",
                    "widenScalarOrEltToNextPow2OrMinSize"):
        idx = idx_of(args[0], env)
        if method == "widenScalarOrEltToNextPow2OrMinSize":
            # C++: `ssz < Min || !isPow2(ssz)`, which is exactly the int form.
            to = tr.int_expr(args[1]) if len(args) > 1 else "pow2"
            out.append("widen(slot(%d), %s)" % (idx, to))
        else:
            on = "elem_of(slot(%d))" % idx if "OrElt" in method else "slot(%d)" % idx
            if len(args) > 1:
                out.append("widen(%s, pow2_min(%s))" % (on, tr.int_expr(args[1])))
            else:
                out.append("widen(%s, pow2)" % on)
    elif method == "widenVectorEltsToVectorMinSize":
        idx = idx_of(args[0], env)
        out.append("widen(elem_of(slot(%d)), min_vector_size(%s))"
                   % (idx, tr.int_expr(args[1])))
    elif method == "widenScalarFor":
        for g, pred in type_preds(0, args[0]):
            out.append("widen(%s) when %s" % (mutation(args[1]), pred))
    elif method == "scalarSameSizeAs":
        a, b = idx_of(args[0], env), idx_of(args[1], env)
        out.append("widen(slot(%d), same_as(%d))" % (a, b))
        out.append("narrow(slot(%d), same_as(%d))" % (a, b))
    elif method in ("moreElementsToNextPow2", "fewerElementsToNextPow2"):
        idx = idx_of(args[0], env)
        out.append("%s(slot(%d), pow2)"
                   % ("more" if method.startswith("more") else "fewer", idx))
    elif method in ("moreElementsIf", "fewerElementsIf"):
        op = "more" if method.startswith("more") else "fewer"
        if len(args) == 1:
            out.append("%s(%s)" % (op, mutation(args[0])))
        else:
            out.append("%s(%s) when %s" % (op, mutation(args[1]),
                                           tr.pred_lambda(args[0])))
    elif method == "clampMinNumElements":
        out.append("clamp_min(%s, %s, %s)" % (idx_of(args[0], env),
                                              tr.t.name(args[1]),
                                              tr.int_expr(args[2])))
    elif method == "clampMaxNumElements":
        out.append("clamp_max(%s, %s, %s)" % (idx_of(args[0], env),
                                              tr.t.name(args[1]),
                                              tr.int_expr(args[2])))
    elif method == "clampNumElements":
        idx = idx_of(args[0], env)
        elt = tr.t.elem_of(args[1])
        out.append("clamp_min(%d, %s, num_elems(ty(%s)))"
                   % (idx, elt, tr.t.name(args[1])))
        out.append("clamp_max(%d, %s, num_elems(ty(%s)))"
                   % (idx, elt, tr.t.name(args[2])))
    elif method in ("widenScalarIf", "narrowScalarIf", "bitcastIf"):
        if len(args) != 2:
            raise Refuse("%s with %d args" % (method, len(args)))
        pred, mut = args[0], args[1]
        op = {"widenScalarIf": "widen", "narrowScalarIf": "narrow",
              "bitcastIf": "bitcast"}[method]
        to = tr.mutation_lambda(mut) if op == "bitcast" else mutation(mut)
        out.append("%s(%s) when %s" % (op, to, tr.pred_lambda(pred)))
    elif method == "immIdx":
        out.append("imm_idx(%s)" % idx_of(args[0], env))
    elif method == "unsupportedIfMemSizeNotPow2":
        out.append("unsupported not is_pow2(size_in_bytes_of("
                   "mem_ty(mem_slot(0))))")
    elif method == "narrowScalarFor":
        pairs = split_top(args[0].strip()[1:-1])
        rows = [split_top(r[1:-1]) for r in pairs]
        to = mutation(args[1])
        out.append("narrow(%s) when in_pairs(slot(0), slot(1), [%s])"
                   % (to, ", ".join("[" + ", ".join(tr.t.name(x) for x in r) + "]"
                                    for r in rows)))
    elif method in ("lowerIfMemSizeNotByteSizePow2", "lowerIfMemSizeNotPow2"):
        mt = "mem_ty(mem_slot(0))"
        if method == "lowerIfMemSizeNotByteSizePow2":
            pred = ("(not is_byte_sized(%s) or not is_pow2(size_in_bytes_of(%s)))"
                    % (mt, mt))
        else:
            pred = "not is_pow2(size_in_bytes_of(%s))" % mt
        out.append("lower %s" % pred)
    elif method == "bitcast":
        out.append("bitcast(slot(0), %s)" % type_preds(0, args[0])[0][1][len("in(slot(0), "):-1])
    else:
        raise Refuse("%s(...)" % method)
    if pred_arg is not None and method in (
            "minScalar", "maxScalar", "clampScalar", "widenScalarToNextPow2",
            "widenScalarOrEltToNextPow2", "widenScalarOrEltToNextPow2OrMinSize",
            "scalarSameSizeAs", "minScalarOrElt", "clampScalarOrElt"):
        g = tr.pred(pred_arg)
        out = [l if " when " in l else l + " when " + g for l in out]
    STATS["calls"][method] = STATS["calls"].get(method, 0) + 1
    STATS["rules"][method] = STATS["rules"].get(method, 0) + len(out)
    return out


def mem_desc_tables(tr, text):
    """`{{t, p, mt, align}, ...}` -> [(gate|None, `in_mem_desc(...)`), ...].

    `getScalarMemAlign(n)` is `ST.enableUnalignedScalarMem() ? 8 : n`, so a row
    that uses it forces the whole table to be written once per variant, with
    mutually exclusive `when` gates -- exactly what the C++ does.
    """
    rows = [split_top(r[1:-1]) for r in split_top(text.strip()[1:-1])]
    parsed = []
    for parts in rows:
        if len(parts) != 4:
            raise Refuse(", ".join(parts))
        t0, t1, mt, al = [x.strip() for x in parts]
        if re.fullmatch(r"\d+", al):
            variants = [(None, int(al))]
        else:
            variants = tr.align_variants(al)
        parsed.append((tr.t.name(t0), tr.t.name(t1), tr.t.name(mt), variants))

    n = max(len(p[3]) for p in parsed)
    if n == 1:
        return [(None, "in_mem_desc(slot(0), slot(1), mem_slot(0), [%s])" %
                 ", ".join("mem_desc(%s, %s, %s, %s)" % (a, b, c, v[0][1])
                           for a, b, c, v in parsed))]

    # The most specific row defines the table split; the others are the same
    # value under every variant (or pick by the first gate atom).
    template = max(parsed, key=lambda p: len(p[3]))[3]

    def atom(gate):
        return None if gate is None else gate.split(" and ")[0]

    tables = []
    for k, (gate, _val) in enumerate(template):
        entries, gates = [], []
        for a, b, c, variants in parsed:
            if len(variants) == 1:
                val = variants[0][1]
            else:
                val = variants[k][1] if len(variants) == len(template) else next(
                    v for g, v in variants if atom(g) == atom(gate))
            entries.append("mem_desc(%s, %s, %s, %s)" % (a, b, c, val))
            if gate:
                gates.append(gate)
        gates = list(dict.fromkeys(gates))
        tables.append((" and ".join(gates) or None,
                       "in_mem_desc(slot(0), slot(1), mem_slot(0), [%s])" %
                       ", ".join(entries)))
    return tables


def match_paren(text, i):
    """Index just past the `)` that closes the `(` at i."""
    depth = 0
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise Refuse("unbalanced parentheses")


def match_brace(text, i):
    """Index just past the `}` that closes the `{` at i."""
    depth = 0
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise Refuse("unbalanced braces")


def consume_one(text, i):
    """Consume one statement (simple or braced) and return the next index."""
    while i < len(text) and text[i] in " \t\n\r":
        i += 1
    m = re.match(r"(if|for|while)\b", text[i:])
    if m:
        j = text.index("(", i)
        j = match_paren(text, j)
        j = consume_one(text, j)
        m2 = re.match(r"\s*else\b", text[j:])
        if m2:
            j += m2.end()
            j = consume_one(text, j)
        return j
    if i < len(text) and text[i] == "{":
        depth = 0
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise Refuse("unbalanced braces")
    depth = 0
    while i < len(text):
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == ";" and depth == 0:
            return i + 1
        i += 1
    return i


def split_statements(text):
    """Top-level statements, keeping `if`/`for` bodies attached."""
    out, i, n = [], 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\n\r":
            i += 1
        if i >= n:
            break
        start = i
        m = re.match(r"(if|for|while)\b", text[i:])
        if m:
            j = text.index("(", i)
            j = match_paren(text, j)
            j = consume_one(text, j)
            m2 = re.match(r"\s*else\b", text[j:])
            if m2:
                j += m2.end()
                j = consume_one(text, j)
            out.append(text[start:j].strip())
            i = j
            continue
        if text[i] == "{":
            j = consume_one(text, i)
            out.append(text[start:j].strip())
            i = j
            continue
        j = consume_one(text, i)
        out.append(text[start:j].strip())
        i = j
    return out


TERMINALS = ("legal", "custom", "lower", "unsupported", "libcall")


def apply_gate(line, gate):
    if not gate:
        return line
    head, _, rest = line.partition(" ")
    if head in TERMINALS:
        rest = rest.strip()
        return "%s %s" % (head, gate if rest == "true" else "(%s and %s)" % (gate, rest))
    if " when " in line:
        body, _, when = line.partition(" when ")
        return "%s when (%s and %s)" % (body, gate, when)
    if line.startswith("scalarize(") or line.startswith("imm_idx("):
        return line          # both are markers, not rules with predicates
    return line + " when " + gate


class Importer:
    def __init__(self, target, source=""):
        global PREFIX, CURRENT_TARGET
        PREFIX = target[0].upper() + "_"
        CURRENT_TARGET = target
        self.p = Program()
        self.t = Types()
        self.tr = Translator(self.t)
        self.t.cond_fn = self.tr.pred
        self.t.feat_name = self.tr.feature
        self.tr.helpers = parse_helpers(source)
        self.tr.aligns = parse_aligns(source)
        self.named_preds = {}
        self.tr.named_preds = self.named_preds
        self.rulesets = []
        self.gate = []
        self.env = {}
        self.tr.env = self.env

    # -- statements ------------------------------------------------------
    def block(self, text, line0=0):
        for st in split_statements(text):
            try:
                self.statement(st, line0)
            except Refuse as e:
                self.p.refuse(line0, "%s: %s" % (st.splitlines()[0][:60], e))

    def statement(self, st, line):
        st = st.strip()
        if st.endswith(";"):
            st = st[:-1].rstrip()
        if not st:
            return
        if st.startswith("if "):
            return self.if_stmt(st, line)
        if st.startswith("for "):
            return self.for_stmt(st, line)
        if st.startswith("{"):
            return self.block(st[1:-1], line)
        if re.match(r"(const\s+)?LLT\s+\w+\s*=", st):
            m = re.match(r"(?:const\s+)?LLT\s+(\w+)\s*=\s*(.+)$", st, re.S)
            return self.t.add(m.group(1), m.group(2), line)
        if re.match(r"(const\s+)?bool\s+\w+\s*=", st):
            m = re.match(r"(?:const\s+)?bool\s+(\w+)\s*=\s*(.+)$", st, re.S)
            name, expr = m.group(1), m.group(2).strip()
            self.tr.features[expr] = PREFIX + name
            self.tr.feature_aliases[name] = PREFIX + name
            return
        if re.match(r"auto\s+\w+\s*=\s*\[", st):
            if "LegalityQuery" in st:
                m = re.match(r"auto\s+(\w+)\s*=\s*(.+)$", st, re.S)
                self.named_preds[m.group(1)] = self.tr.pred_lambda(m.group(2))
            return          # otherwise an align helper, parsed from the source
        if re.match(r"auto\s+\w+\s*=\s*\{", st):
            m = re.match(r"auto\s+(\w+)\s*=\s*\{(.*)\}$", st, re.S)
            self.t.sets[m.group(1)] = [x.strip() for x in split_top(m.group(2))]
            return
        m = re.match(r"(?:const\s+)?std::initializer_list<LLT>\s+(\w+)\s*=\s*"
                     r"\{(.*)\}$", st, re.S)
        if m:
            self.t.sets[m.group(1)] = [x.strip() for x in split_top(m.group(2))]
            return
        m = re.match(r"SmallVector<LLT,\s*\d+>\s+(\w+)\s*\(\s*(\w+)\s*\)$", st)
        if m:
            src = self.t.sets.get(m.group(2))
            if src is None:
                raise Refuse("unknown type list %r" % m.group(2))
            self.t.sets[m.group(1)] = list(src)
            return
        if re.match(r"const\s+TargetMachine\s*&", st):
            return          # `TM` only appears inside C++ predicates
        if st == "return":
            return          # `if (...) return;` in a helper
        m = re.match(r"(?:auto|LegalityPredicate)\s+(\w+)\s*=\s*(\[.*\]\s*\(.*)$",
                     st, re.S)
        if m:
            self.named_preds[m.group(1)] = self.tr.pred_lambda(m.group(2))
            return
        m = re.match(r"(?:auto|LegalityPredicate)\s+(\w+)\s*=\s*(all\s*\(.*)$",
                     st, re.S)
        if m:
            self.named_preds[m.group(1)] = self.tr.pred(m.group(2))
            return
        if re.match(r"auto\s*&\s*\w+\s*=", st):
            m = re.match(r"auto\s*&\s*(\w+)\s*=\s*(.+)$", st, re.S)
            return self.chain(m.group(1), m.group(2), line)
        if st.startswith("getActionDefinitionsBuilder"):
            return self.chain(None, st, line)
        m = re.match(r"(\w+)\s*\.", st)
        if m and m.group(1) in self.p.by_object:
            return self.extend(self.p.by_object[m.group(1)], st[m.end(1):], line)
        if re.match(r"unsigned\s+\w+\s*=", st):
            m = re.match(r"unsigned\s+(\w+)\s*=\s*(.+)$", st, re.S)
            self.env[m.group(1)] = const_eval(m.group(2), self.env)
            return
        if re.match(r"LegalityPredicate\s+\w+\s*=", st):
            return self.predicate_var(st, line)
        if re.match(r"verify\s*\(", st) or st.startswith("using namespace "):
            return
        m = re.match(r"(\w+)\s*=\s*(.+)$", st, re.S)
        if m and m.group(1) in self.named_preds:
            return self.predicate_var("LegalityPredicate " + st, line)
        raise Refuse("unrecognised statement")

    def predicate_var(self, st, line):
        m = re.match(r"LegalityPredicate\s+(\w+)\s*=\s*(.+)$", st, re.S)
        name, rhs = m.group(1), m.group(2).strip()
        if name in self.named_preds:
            cond = self.gate[-1] if self.gate else "true"
            self.named_preds[name] = "((%s and %s) or (not %s and %s))" % (
                cond, self._pred_text(rhs, line), cond, self.named_preds[name])
            return
        self.named_preds[name] = self._pred_text(rhs, line)

    def _pred_text(self, rhs, line):
        rhs = rhs.strip().rstrip(";")
        m = re.match(r"\[.*?\]\s*\((.*?)\)\s*\{(.*)\}$", rhs, re.S)
        if not m:
            # A plain predicate expression: `all(sizeIs(0, 64), immIs(0, 32))`.
            return self.tr.pred(rhs)
        body = m.group(2)
        aliases = dict(re.findall(r"LLT\s+(\w+)\s*=\s*(Query\.Types\[[^\]]+\]);",
                                  body))
        for var, val in aliases.items():
            body = re.sub(r"\b%s\b" % var, val, body)
        rm = re.search(r"return\s+(.+?);", body, re.S)
        if not rm:
            raise Refuse("predicate lambda")
        return self.tr.query_body(rm.group(1))

    def if_stmt(self, st, line):
        open_ = st.index("(")
        close = match_paren(st, open_) - 1
        cond, rest = st[open_ + 1:close], st[close + 1:]
        then, els = self._split_else(rest)
        try:
            v = const_eval(cond, self.env)
        except Refuse:
            v = None
        if isinstance(v, bool):
            body = then if v else els
            if body:
                self.block(body, line)
            return
        try:
            gate = self.tr.pred(cond)
        except Refuse:
            self.p.refuse(line, "if (%s)" % cond)
            return
        self.gate.append(gate)
        self.block(then, line)
        self.gate.pop()
        if els is not None:
            self.gate.append("not " + gate)
            self.block(els, line)
            self.gate.pop()

    @staticmethod
    def _split_else(rest):
        rest = rest.strip()
        if not rest.startswith("{"):
            # Brace-less `if (c) A; else B;` -- split at the first top-level else.
            depth, k = 0, 0
            while k < len(rest):
                c = rest[k]
                if c in "([{":
                    depth += 1
                elif c in ")]}":
                    depth -= 1
                elif depth == 0 and rest.startswith("else", k) and (
                        k == 0 or not (rest[k-1].isalnum() or rest[k-1] == "_")) and (
                        k + 4 == len(rest) or not (rest[k+4].isalnum() or rest[k+4] == "_")):
                    return Importer._strip_semicolon(rest[:k]), rest[k+4:].strip()
                k += 1
        if rest.startswith("{"):
            depth, i = 0, 0
            while i < len(rest):
                if rest[i] == "{":
                    depth += 1
                elif rest[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            then, tail = rest[1:i], rest[i + 1:].strip()
        else:
            then, tail = rest, ""
        if tail.startswith("else"):
            tail = tail[4:].strip()
            if tail.startswith("{"):
                return then, tail[1:-1]
            # `else <one statement>`: take exactly that statement, not the rest
            # of the constructor.
            end = consume_one(tail, 0)
            return then, tail[:end].strip().rstrip(";")
        return then, None

    @staticmethod
    def _strip_semicolon(text):
        text = text.strip()
        return text[:-1] if text.endswith(";") else text

    def for_stmt(self, st, line):
        open_ = st.index("(")
        close = match_paren(st, open_) - 1
        head, body = st[open_ + 1:close], st[close + 1:].strip()
        m = re.fullmatch(r"unsigned\s+(\w+)\s*:\s*(.+)", head, re.S)
        if not m or not body.startswith("{"):
            raise Refuse("for (unrecognised)")
        var, items, body = m.group(1), m.group(2), body[1:-1]
        for op in opcodes_of(items, self.env):
            self.env[var] = op
            self.block(body, line)
        self.env.pop(var, None)

    # -- chains ----------------------------------------------------------
    def chain(self, obj, text, line):
        m = re.match(r"getActionDefinitionsBuilder\s*\((.*?)\)\s*(.*)$", text, re.S)
        head = split_top(m.group(1))[0]
        ops = opcodes_of(head, self.env)
        if len(ops) > 1 and "Query.Opcode" in text:
            # A chain that branches on `Query.Opcode` loses that branch when
            # one rule set covers several opcodes; split it per opcode.
            for op in ops:
                self.tr.opcode = op
                try:
                    self.chain_one(obj, text, line, [op])
                finally:
                    self.tr.opcode = None
            return
        self.chain_one(obj, text, line, ops)

    def chain_one(self, obj, text, line, ops):
        m = re.match(r"getActionDefinitionsBuilder\s*\((.*?)\)\s*(.*)$", text, re.S)
        name = PREFIX + ops[0]
        # Repeated builders for one opcode are separate rule sets in C++ (both
        # apply, in order).  Keep both, but give the def a unique name.
        taken = {r.name for r in self.rulesets}
        if name in taken:
            k = 2
            while "%s_%d" % (name, k) in taken:
                k += 1
            name = "%s_%d" % (name, k)
        rs = Chain(name, ops, line)
        self.rulesets.append(rs)
        if obj:
            self.p.by_object[obj] = rs
        tail = m.group(2).strip().lstrip(". ")
        if tail:
            self.extend(rs, "." + tail, line, bare=True)

    def extend(self, rs, text, line, bare=False):
        text = text.strip()
        if not text.startswith("."):
            text = "." + text
        i = 0
        while i < len(text):
            text_slice = text[i:]
            m = re.match(r"\s*\.\s*([A-Za-z_]\w*)\s*\(", text_slice)
            if not m:
                break
            got = take_call(text_slice, m.start() + len(m.group(0)) - len(m.group(1)) - 1)
            if not got:
                break
            _, args, end = got
            method = m.group(1)
            try:
                rules = emit_chain_call(self.tr, self.p, rs, method, args, line,
                                        self.env)
            except Refuse as e:
                self.p.refuse(line, "%s.%s: %s" % (rs.name, method, e))
                rules = []
            gate = " and ".join(self.gate) if self.gate else ""
            if len(self.gate) > 1:
                gate = "(" + " and ".join(self.gate) + ")"
            for r in rules:
                rs.rules.append((line, apply_gate(r, gate)))
            i += end
        rest = text[i:].strip()
        if rest not in ("", ";"):
            self.p.refuse(line, "%s: trailing %r" % (rs.name, rest[:40]))


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

HEADER = """//===- {name}.gisel - imported from {src} -*- gisel -*-===//
//
// One-shot transcription: `tools/import-cxx.py {target} {src}`.
// Source sha256 {sha}.  Do not edit by hand; re-run the importer instead.
//
// The importer refuses what it cannot translate; every refusal below is a
// statement that still has to be written by hand (or taught to the importer).
//
{notes}//===----------------------------------------------------------------------===//
"""


def member_types(path):
    """`sXLen(LLT::scalar(XLen))` from the constructor's init list."""
    text = "\n".join(strip_comments(open(path).read()))
    m = re.search(r"::\w+LegalizerInfo\s*\([^)]*\)\s*:\s*([^{]*)\{", text)
    if not m:
        return []
    out = []
    for name, rhs in re.findall(r"(\w+)\s*\(([^()]*(?:\([^()]*\))?[^()]*)\)", m.group(1)):
        if rhs.strip().startswith("LLT::"):
            out.append((name, rhs.strip()))
    return out


def constructor_text(path):
    lines = strip_comments(open(path).read())
    text = "\n".join(lines)
    m = re.search(r"::\w+LegalizerInfo\s*\([^)]*const\s+\w+Subtarget\s*&[^)]*\)"
                  r"[^{]*\{", text)
    if not m:
        raise SystemExit("no constructor found")
    start = m.end() - 1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    raise SystemExit("unbalanced constructor")


# ---------------------------------------------------------------------------
# Reviewed deviations
#
# This tool is a one-shot transcriber for the three constructors under
# `lib/Target/*/GISel`, not a general C++ parser.  The shipped corpus is the
# transcription plus the edits below; each one asserts that the text it
# rewrites is still present, so an upstream change fails loudly instead of
# silently applying to nothing.
# ---------------------------------------------------------------------------

def deviation_x86_build_vector(imp):
    """Drop the minimum-element clamp on G_BUILD_VECTOR.

    Upstream clamps both ends (X86LegalizerInfo.cpp:559-563) and then asks for
    the next power of two.  For a narrow build vector that means *adding*
    undef elements, and narrowing the result back recreates the same query, so
    the legalizer re-enqueues it forever (the cycle `gisel graph` finds on the
    unpatched transcription).  Keep the maximum clamp only: a narrow build
    vector is Unsupported and falls back to SelectionDAG.
    """
    rs = next(r for r in imp.rulesets if r.opcodes == ["G_BUILD_VECTOR"])
    before = len(rs.rules)
    keep = [(l, t) for l, t in rs.rules
            if not t.startswith(("clamp_min(", "more("))]
    dropped = before - len(keep)
    if dropped != 5:            # four clamp_min + one more
        raise SystemExit("X86 G_BUILD_VECTOR: expected 5 droppable rules, "
                         "found %d" % dropped)
    rs.rules = keep


def deviation_x86_ctpop(imp):
    """Vector CTPOP is legal with VPOPCNTDQ (+VLX under 512 bits).

    Not in upstream's constructor yet: our corpus carries the vector
    legalization, so the frozen answers (tests/cases/x86_ref_dump.jsonl) list
    those types as Legal.
    """
    rs = next(r for r in imp.rulesets if r.opcodes == ["G_CTPOP"])
    if not rs.rules or not rs.rules[1][1].startswith("legal "):
        raise SystemExit("X86 G_CTPOP: expected two leading legal rules")
    vp = imp.tr.feature_named("HasVPOPCNTDQ", "Subtarget.hasVPOPCNTDQ()")
    vlx = imp.tr.feature("Subtarget.hasVLX()")
    p = PREFIX
    rs.rules[2:2] = [
        (0, "legal (%s and in_pairs(slot(0), slot(1), "
            "[[%sv16s32, %sv16s32], [%sv8s64, %sv8s64]]))"
            % (vp, p, p, p, p)),
        (0, "legal ((%s and %s) and in_pairs(slot(0), slot(1), "
            "[[%sv4s32, %sv4s32], [%sv8s32, %sv8s32], "
            "[%sv2s64, %sv2s64], [%sv4s64, %sv4s64]]))"
            % (vp, vlx, p, p, p, p, p, p, p, p)),
    ]


X86_DEVIATIONS = (deviation_x86_build_vector, deviation_x86_ctpop)


def render(imp):
    t = imp.t
    out = []
    out.append('include "llvm/Target/LegalizerInfo.td"')
    out.append('include "llvm/Target/Target.td"')
    out.append("")
    for cpp, name in sorted(imp.tr.features.items(), key=lambda kv: kv[1]):
        out.append("feature %s = %s" % (name, cpp))
    out.append("")
    for _, name, rhs in t.decl:
        out.append("type %s = %s" % (name, rhs))
    for emitted, _lo, _hi in getattr(t, "selects", []):
        out.append("select %s = if %s then %s else %s"
                   % (emitted, imp.tr.feature("XLen == 64"),
                      _hi, _lo))
    for name, text in getattr(t, "preds", []):
        out.append("pred %s = %s" % (name, text))
    for name, cond, then, els in getattr(t, "anon", []):
        out.append("select %s = if %s then %s else %s"
                   % (name, cond, then, els))
    for cpp, elems in t.sets.items():
        out.append("type_set %s = [%s]" % (PREFIX + cpp,
                                           ", ".join(t.name(e) for e in elems)))
    out.append("")
    for rs in imp.rulesets:
        if not rs.rules:
            continue
        out.append("ruleset %s: %s" % (rs.name, " ".join(rs.opcodes)))
        for _, text in rs.rules:
            out.append("    " + text)
        out.append("")
    return "\n".join(out)


class Target:
    """One pinned constructor: relative source, prefix, expected counts."""

    def __init__(self, name, prefix, rel, rulesets, rules, deviations=()):
        self.name = name
        self.prefix = prefix
        self.rel = rel
        self.rulesets = rulesets
        self.rules = rules
        self.deviations = deviations

    @property
    def env(self):
        return "GS_%s_SRC" % self.name.upper()

    @property
    def corpus_name(self):
        return "%sLegalizerInfo.gisel" % self.name


TARGETS = {
    "X86": Target(
        "X86", "X",
        "lib/Target/X86/GISel/X86LegalizerInfo.cpp",
        63, 328, X86_DEVIATIONS),
    "AArch64": Target(
        "AArch64", "A",
        "lib/Target/AArch64/GISel/AArch64LegalizerInfo.cpp",
        117, 744),
    "RISCV": Target(
        "RISCV", "R",
        "lib/Target/RISCV/GISel/RISCVLegalizerInfo.cpp",
        96, 402),
}


def find_source(spec, args):
    """Explicit --source, then $GS_<TARGET>_SRC, then --llvm-src + pinned path."""
    if args.source:
        return Path(args.source)
    env = os.environ.get(spec.env)
    if env:
        return Path(env)
    if args.llvm_src:
        return Path(args.llvm_src) / spec.rel
    raise SystemExit(
        "%s: no source; pass --source, --llvm-src, or set %s"
        % (spec.name, spec.env))


def transcribe(spec, source, out):
    """Run the transcription; return (exit code, generated text)."""
    source = Path(source)
    text = source.read_text()
    STATS["calls"].clear()
    STATS["rules"].clear()
    USED_RENAMES["select"].clear()
    USED_RENAMES["feature"].clear()
    imp = Importer(spec.name, text)
    for name, rhs in member_types(source):
        imp.t.add(name, rhs, 0)
    imp.block(constructor_text(source))
    for fix in spec.deviations:
        fix(imp)

    refusals = imp.p.refused + [(l, w) for l, w in imp.t.refused] + \
        [(0, w) for w in imp.tr.refused]
    notes = ""
    if refusals:
        notes = "// Refused (%d statement(s), not transcribed):\n" % len(refusals)
        for line, why in refusals[:40]:
            notes += "//   line %d: %s\n" % (line, why)
        notes += "//\n"
    name = spec.name + "LegalizerInfo"
    body = render(imp)
    header = HEADER.format(
        name=name, src=source.name, target=spec.name,
        sha=hashlib.sha256(text.encode()).hexdigest(), notes=notes)
    generated = header + body

    rules = sum(len(rs.rules) for rs in imp.rulesets)
    rulesets = sum(1 for rs in imp.rulesets if rs.rules)
    where = str(out) if out else source.name
    print("%s: %d rulesets, %d rules, %d refused"
          % (where, rulesets, rules, len(refusals)))
    for line, why in refusals:
        print("  refused line %s: %s" % (line, why))

    rc = 1 if refusals else 0
    # The pin only applies to the canonical upstream file, not to fixtures.
    if source.name == "%sLegalizerInfo.cpp" % spec.name:
        if (rulesets, rules) != (spec.rulesets, spec.rules):
            print("  DRIFT: %s pinned at %d rulesets / %d rules, got %d / %d"
                  % (spec.name, spec.rulesets, spec.rules, rulesets, rules))
            rc = 1
        for kind, table in (("select", SELECT_NAMES),
                            ("feature", FEATURE_NAMES)):
            stale = set(table.get(spec.name, {})) - USED_RENAMES[kind]
            if stale:
                print("  DRIFT: %s %s rename keys no longer match: %s"
                      % (spec.name, kind, ", ".join(sorted(stale))))
                rc = 1
        unnamed = getattr(imp.t, "unnamed", 0)
        if unnamed:
            print("  DRIFT: %s has %d unnamed select(s); extend SELECT_NAMES"
                  % (spec.name, unnamed))
            rc = 1

    if out is not None:
        Path(out).write_text(generated)
    return rc, generated


def show_stats():
    print("%-40s %6s %6s" % ("method", "calls", "rules"))
    for k in sorted(STATS["calls"]):
        print("%-40s %6d %6d" % (k, STATS["calls"][k], STATS["rules"][k]))
    print("%-40s %6d %6d" % ("TOTAL", sum(STATS["calls"].values()),
                             sum(STATS["rules"].values())))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="One-shot transcription of the three pinned legalizer "
                    "constructors; not a general C++ importer.")
    ap.add_argument("target", nargs="?", choices=sorted(TARGETS))
    ap.add_argument("source", nargs="?",
                    help="source .cpp (default: $GS_<TARGET>_SRC or --llvm-src)")
    ap.add_argument("--all", action="store_true",
                    help="transcribe every pinned target")
    ap.add_argument("--llvm-src", help="LLVM source root containing lib/Target")
    ap.add_argument("--out", help="output .gisel (single target)")
    ap.add_argument("--out-dir", help="output directory in --all mode")
    ap.add_argument("--check", action="store_true",
                    help="compare with the checked-in corpus instead of writing")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args(argv)

    if args.all == bool(args.target):
        ap.error("pass exactly one of TARGET or --all")
    if args.all and (args.source or args.out):
        ap.error("a source path and --out are single-target; "
                 "use --llvm-src/--out-dir")
    if not args.all and (args.out_dir or args.check):
        ap.error("--out-dir/--check are --all options")

    specs = [TARGETS[t] for t in sorted(TARGETS)] if args.all \
        else [TARGETS[args.target]]
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "tests" / "corpus"

    rc = 0
    for spec in specs:
        source = find_source(spec, args)
        if args.all:
            dest = out_dir / spec.corpus_name
        else:
            dest = Path(args.out) if args.out else out_dir / spec.corpus_name
        if args.check:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            try:
                old = dest.read_text()
            except FileNotFoundError:
                print("%s: missing (%s)" % (dest, digest))
                rc = 1
                continue
            code, generated = transcribe(spec, source, None)
            if generated != old:
                print("%s: DIFFERS (source sha256 %s)" % (dest, digest))
                rc = 1
            else:
                print("%s: matches (source sha256 %s)" % (dest, digest))
            rc = rc or code
        else:
            code, _ = transcribe(spec, source, dest)
            rc = rc or code
        if args.stats:
            show_stats()
    return rc


if __name__ == "__main__":
    sys.exit(main())
