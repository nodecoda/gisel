#!/usr/bin/env python3
"""Import a hand-written `*LegalizerInfo.cpp` constructor into `.gisel`.

    tools/import-cxx.py TARGET RISCVLegalizerInfo.cpp --out R.gisel

The input is not C++ in general: it is the subset a legalizer constructor is
written in -- `getActionDefinitionsBuilder(...)` chains, `auto &X = ...` with
later extension, `if`/`else`, `for` over opcode lists, `const LLT` constants
and a handful of `LegalityPredicate` lambdas.

Anything outside that subset is **refused with a line number**, never dropped:
a transcription that silently loses a rule is worse than no transcription.

Exit codes: 0 imported, 1 refused something (partial output still written),
2 parse error.
"""

import argparse
import re
import sys

PREFIX = None  # set from the target name: RISCV -> "R_"


# ---------------------------------------------------------------------------
# Lexing helpers
# ---------------------------------------------------------------------------

def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return [re.sub(r"//.*$", "", line) for line in text.splitlines()]


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
        m = re.fullmatch(r"\(?\s*(.+?)\s*\)?\s*\?\s*(.+?)\s*:\s*(.+)$",
                         cpp.strip(), re.S)
        if m:
            # `(cond) ? T : F` -> a named `select` declaration (the backends
            # resolve type values through names, not inline expressions).
            self.anon = getattr(self, "anon", [])
            self.preds = getattr(self, "preds", [])
            pname = PREFIX + "cond%d" % len(self.preds)
            cond = self.cond_fn(m.group(1))
            cond = re.sub(r'feature\("((?:[^"\\]|\\.)*)"\)',
                          lambda k: self.feat_name(k.group(1)), cond)
            self.preds.append((pname, cond))
            name = PREFIX + "sel%d" % len(self.anon)
            self.anon.append((name, pname, self.name(m.group(2)),
                              self.name(m.group(3))))
            self.by_cpp[cpp.strip()] = name
            return name
        return cpp

    def translate_refs(self, expr):
        """Rewrite C++ local type names to their `.gisel` names."""
        def sub(m):
            word = m.group(0)
            return self.by_cpp.get(word, word)
        return re.sub(r"\b[A-Za-z_]\w*\b", sub, expr)

    def add(self, cpp_name, rhs, line):
        emitted = PREFIX + cpp_name
        text = self.translate_refs(rhs)
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

class Translator:
    """C++ predicate/value text -> `.gisel` text.  Raises Refuse."""

    def __init__(self, types):
        self.t = types
        self.features = {}      # cpp text -> feature name
        self.helpers = {}       # static LegalityPredicate helpers
        self.aligns = {}        # align lambdas: name -> (cond, then, else)
        self.named_preds = {}   # LegalityPredicate variables
        self.refused = []

    # -- features: any `ST.x()` / `XLen == N` becomes a named feature --------
    def feature(self, cpp_text):
        name = cpp_text
        if name not in self.features:
            slug = re.sub(r"[^0-9A-Za-z]+", "_", cpp_text).strip("_")
            self.features[name] = PREFIX + slug
        return self.features[name]

    def pred(self, text):
        text = text.strip()
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
        m = re.fullmatch(r"(all|any)\s*\((.*)\)", text, re.S)
        if m:
            parts = split_top(m.group(2))
            kw = "and" if m.group(1) == "all" else "or"
            return "(" + (" %s " % kw).join(self.pred(p) for p in parts) + ")"
        m = re.fullmatch(r"LegalityPredicates::(all|any)\s*\((.*)\)", text, re.S)
        if m:
            parts = split_top(m.group(2))
            kw = "and" if m.group(1) == "all" else "or"
            return "(" + (" %s " % kw).join(self.pred(p) for p in parts) + ")"
        # Predicates that name a slot by a constructor variable: fold it first.
        text = re.sub(r"\(\s*(\w+)\s*,", lambda m: "(%s," % (
            m.group(1) if m.group(1).isdigit() else self.slot_index(m.group(1))
        ) if not m.group(1).isdigit() else m.group(0), text)
        for pat, body in (
                (r"typeIs\s*\(\s*(\d+)\s*,\s*(.+)\)", r"in(slot(\1), \2)"),
                (r"typeIsNot\s*\(\s*(\d+)\s*,\s*(.+)\)", r"not in(slot(\1), \2)"),
                (r"typeInSet\s*\(\s*(\d+)\s*,\s*\{(.*)\}\)",
                 r"in(slot(\1), [\2])"),
                (r"sizeIs\s*\(\s*(\d+)\s*,\s*(\d+)\)", r"size_of(slot(\1)) == \2"),
                (r"immIs\s*\(\s*(\d+)\s*,\s*(-?\d+)\)", r"imm(\1) == \2"),
                (r"immInSet\s*\(\s*(\d+)\s*,\s*\{(.*)\}\)", r"in(imm(\1), [\2])"),
                (r"isScalar\s*\(\s*(\d+)\s*\)", r"sort_of(slot(\1)) == scalar"),
        ):
            m = re.fullmatch(pat, text, re.S)
            if m:
                out = re.sub(r"\\(\d)", lambda k: m.group(int(k.group(1))), body)
                return self._types_in_pred(out)
        if text in ("true", "false"):
            return text
        if text not in ("XLen", "ST.getXLen()", "STI.getXLen()", "ST.getELen()",
                        "STI.getELen()") and "Query." not in text and \
                re.fullmatch(r"(ST|STI|XLen)\b[\w.()\s<>=!&|+\-]*", text):
            return 'feature("%s")' % cpp_text_for(self.features, self.feature(text))
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
            return 'feature("%s")' % cpp_text_for(self.features, self.feature(text))
        raise Refuse(text)


    # -- mutations -------------------------------------------------------
    def mutation(self, text):
        """`changeTo(i, T)` / `LegalizeMutations::changeTo(i, T)`."""
        text = text.strip()
        m = re.fullmatch(r"(?:LegalizeMutations::)?changeTo\s*\(\s*(\d+)\s*,"
                         r"\s*(.+)\)", text, re.S)
        if not m:
            raise Refuse(text)
        return "slot(%s), ty(%s)" % (m.group(1), self.t.name(m.group(2)))

    def mutation_lambda(self, text):
        """`bitcastIf`'s new-type lambda -> a `.gisel` type expression."""
        m = re.search(r"LLT::vector\(\s*Query\.Types\[(\d+)\]\.getElementCount"
                      r"\(\)\.divideCoefficientBy\((\d+)\)\s*,\s*(\d+)\s*\)", text)
        if m:
            return ("slot(%s), replace(elt_type_to(div_lanes(slot(%s), %s), ty(%s)))"
                    % (m.group(1), m.group(1), m.group(2),
                       self.t.name("s%s" % m.group(3))))
        raise Refuse("bitcast lambda %r" % text[:40])

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
        out = []
        for chunk in re.split(r"(Query\.Types\[[^\]]+\])", body):
            m = re.fullmatch(r"Query\.Types\[(.+)\]", chunk)
            if m:
                out.append("__T(%s)" % m.group(1).strip())
            else:
                out.append(chunk)
        text = "".join(out)
        for pat, rep in (
                (r"__T\((.+?)\)\.getScalarSizeInBits\(\)", r"bits_of(slot(\1))"),
                (r"__T\((.+?)\)\.getElementCount\(\)\.getKnownMinValue\(\)",
                 r"num_elems(slot(\1))"),
                (r"__T\((.+?)\)\.getSizeInBits\(\)", r"size_of(slot(\1))"),
                (r"__T\((.+?)\)\.getElementType\(\)", r"elem_of(slot(\1))"),
                (r"__T\((.+?)\)\.isScalar\(\)", r"sort_of(slot(\1)) == scalar"),
                (r"__T\((.+?)\)", r"slot(\1)"),
        ):
            text = re.sub(pat, rep, text)
        text = re.sub(r"LLT::scalar\(\s*(\d+)\s*\)", r"s\1", text)
        text = re.sub(r"LLT::fixed_vector\(\s*(\d+)\s*,\s*LLT::scalar\(\s*(\d+)\s*\)\s*\)",
                      r"v\1s\2", text)
        text = re.sub(r"LLT::pointer\(\s*(\d+)\s*,\s*(\d+)\s*\)", r"p\1:\2", text)
        text = re.sub(r"\bslot\(\s*(\w+)\s*\)", lambda m: "slot(%s)" % m.group(1), text)
        return self.pred(text)

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
        env = getattr(self, "env", {})
        v = env.get(name, name)
        if not isinstance(v, int):
            raise Refuse("slot index %r" % name)
        return str(v)

    def int_expr(self, text):
        """A C++ integer constant/expression -> a `.gisel` Int expression."""
        t = text.strip()
        if re.fullmatch(r"-?\d+", t):
            return t
        if t in ("XLen", "ST.getXLen()", "STI.getXLen()"):
            return 'select(feature("XLen == 64"), 64, 32)'
        if t.replace(" ", "") in ("2*XLen", "XLen*2"):
            return 'select(feature("XLen == 64"), 128, 64)'
        if t in ("ST.getELen()", "STI.getELen()"):
            return 'select(feature("ST.getELen() == 64"), 64, 32)'
        if re.fullmatch(r"[A-Za-z_][\w.()]*", t):
            return 'select(feature("%s"), 64, 32)' % t
        raise Refuse(text)

    def expr_text(self, text):
        """One side of a comparison: an int, a type name, or an observation."""
        text = text.strip()
        if text in self.named_preds:
            return "(%s)" % self.named_preds[text]
        if re.fullmatch(r"-?\d+", text):
            return text
        if text in ("true", "false"):
            return text
        if text in ("XLen", "ST.getXLen()", "STI.getXLen()", "ST.getELen()",
                    "STI.getELen()"):
            return self.int_expr(text)
        m = re.fullmatch(r"(ST|STI)\..+", text)
        if m:
            return 'feature("%s")' % cpp_text_for(self.features, self.feature(text))
        if "Query." in text:
            return self.query_body(text)
        if re.fullmatch(r"[A-Za-z_]\w*\s*\(.*\)", text, re.S):
            return text          # already `.gisel` (`bits_of(slot(0))`, ...)
        return self.t.name(text)

    @staticmethod
    def _split_cmp(text):
        depth = 0
        for i, c in enumerate(text):
            if c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
            elif depth == 0 and text.startswith(("==", "!=", "<=", ">="), i):
                return text[:i], text[i:i + 2], text[i + 2:]
            elif depth == 0 and c in "<>" and not text.startswith(
                    ("<=", ">="), i):
                return text[:i], c, text[i + 1:]
        return None

    def pred_lambda(self, text):
        text = text.strip()
        m = re.match(r"\[.*?\]\s*\((.*?)\)\s*\{(.*)\}$", text, re.S)
        if not m:
            return self.pred(text)
        body = m.group(2)
        aliases = dict(re.findall(r"LLT\s+(\w+)\s*=\s*(Query\.Types\[[^\]]+\]);",
                                  body))
        for var, val in aliases.items():
            body = re.sub(r"\b%s\b" % var, val, body)
        rm = re.search(r"return\s+(.+?);", body, re.S)
        if not rm:
            raise Refuse("predicate lambda")
        return self.query_body(rm.group(1))

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


def cpp_text_for(features, name):
    for k, v in features.items():
        if v == name:
            return k
    raise KeyError(name)



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
        return const_eval(m.group(2), env) if const_eval(m.group(1), env) \
            else const_eval(m.group(3), env)
    m = re.fullmatch(r"(.+?)\s*==\s*(.+)", text, re.S)
    if m:
        return const_eval(m.group(1), env) == const_eval(m.group(2), env)
    if re.fullmatch(r"G_\w+|\w+", text):
        return env.get(text, text)
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


def emit_chain_call(tr, p, chain, method, args, line, env=None):
    """One builder call -> zero or more `.gisel` rule lines."""
    args = split_top(args) if args.strip() else []
    env = env or {}
    out = []

    def types(idx, text):
        """A `{t, t}` / `{{a,b}}` type argument -> `in*` predicate."""
        text = text.strip()
        if text.startswith("{{"):
            rows = split_top(text[1:-1])
            triples = ["[" + ", ".join(tr.t.name(x) for x in split_top(r[1:-1])) + "]"
                       for r in rows]
            arity = len(split_top(rows[0][1:-1]))
            if arity == 2:
                return "in_pairs(slot(0), slot(1), [%s])" % ", ".join(triples)
            if arity == 3:
                return ("in_triples(slot(0), slot(1), slot(2), [%s])"
                        % ", ".join(triples))
            raise Refuse(text)
        if text.startswith("{"):
            elems = [tr.t.name(x) for x in split_top(text[1:-1])]
            return "in(slot(%d), [%s])" % (idx, ", ".join(elems))
        raise Refuse(text)

    def with_gate(pred, pred_arg):
        if pred_arg is None:
            return pred
        return "(%s and %s)" % (tr.pred(pred_arg), pred)

    def lead_pred(a):
        """Split an optional leading LegalityPredicate argument."""
        if a and not a.lstrip().startswith("{") and not re.fullmatch(r"-?\d+", a):
            return a, a[0:]
        return None, a

    # `legalFor(pred, {..})` / `minScalar(pred, 0, sXLen)`: the predicate is a
    # table-build-time gate, which is exactly what `when` already means.
    BASE_ARGS = {"legalFor": 1, "customFor": 1, "libcallFor": 1, "lowerFor": 1,
                 "unsupportedFor": 1, "legalForTypesWithMemDesc": 1,
                 "minScalar": 2, "maxScalar": 2, "clampScalar": 3}
    pred_arg = None
    if method in BASE_ARGS and len(args) == BASE_ARGS[method] + 1:
        pred_arg, args = args[0], args[1:]

    if method in ("legalFor", "customFor", "libcallFor", "lowerFor",
                  "unsupportedFor"):
        body = args[0]
        pred = with_gate(types(0, body), pred_arg)
        op = {"legalFor": "legal", "customFor": "custom",
              "libcallFor": "libcall", "lowerFor": "lower",
              "unsupportedFor": "unsupported"}[method]
        out.append("%s %s" % (op, pred))
    elif method == "legalForTypesWithMemDesc":
        for g, pred in mem_desc_tables(tr, args[0]):
            pred = with_gate(pred, pred_arg)
            out.append("legal %s" % pred if g is None else
                       "legal (%s and %s)" % (g, pred))
    elif method in ("legalIf", "customIf", "lowerIf", "unsupportedIf"):
        op = {"legalIf": "legal", "customIf": "custom", "lowerIf": "lower",
              "unsupportedIf": "unsupported"}[method]
        out.append("%s %s" % (op, with_gate(tr.pred(args[0]), pred_arg)))
    elif method in ("lower", "unsupported", "alwaysLegal", "libcall"):
        out.append({"lower": "lower true", "unsupported": "unsupported true",
                    "alwaysLegal": "legal true", "libcall": "libcall true",
                    }[method])
    elif method == "scalarize":
        out.append("scalarize(slot(0))")
    elif method == "clampScalar":
        idx = idx_of(args[0], env)
        lo, hi = tr.t.name(args[1]), tr.t.name(args[2])
        out.append("widen(slot(%d), ty(%s))" % (idx, lo))
        out.append("narrow(slot(%d), ty(%s))" % (idx, hi))
    elif method in ("minScalar", "maxScalar"):
        idx = idx_of(args[0], env)
        ty = tr.t.name(args[1])
        out.append("widen(slot(%d), ty(%s))" % (idx, ty)
                   if method == "minScalar" else
                   "narrow(slot(%d), ty(%s))" % (idx, ty))
    elif method == "widenScalarToNextPow2":
        idx = idx_of(args[0], env)
        if len(args) > 1:
            out.append("widen(slot(%d), pow2_min(%s))"
                       % (idx, tr.int_expr(args[1])))
        else:
            out.append("widen(slot(%d), pow2)" % idx)
    elif method == "widenScalarOrEltToNextPow2OrMinSize":
        idx = idx_of(args[0], env)
        out.append("widen(slot(%d), %s)" % (idx, tr.int_expr(args[1])))
    elif method == "scalarSameSizeAs":
        a, b = idx_of(args[0], env), idx_of(args[1], env)
        out.append("widen(slot(%d), same_as(%d))" % (a, b))
        out.append("narrow(slot(%d), same_as(%d))" % (a, b))
    elif method in ("widenScalarIf", "narrowScalarIf", "bitcastIf"):
        if len(args) != 2:
            raise Refuse("%s with %d args" % (method, len(args)))
        pred, mut = args[0], args[1]
        op = {"widenScalarIf": "widen", "narrowScalarIf": "narrow",
              "bitcastIf": "bitcast"}[method]
        if op == "bitcast":
            to = tr.mutation_lambda(mut)
        else:
            to = tr.mutation(mut)
        out.append("%s(%s) when %s" % (op, to, tr.pred_lambda(pred)))
    elif method == "narrowScalarFor":
        pairs = split_top(args[0].strip()[1:-1])
        rows = [split_top(r[1:-1]) for r in pairs]
        to = tr.mutation(args[1])
        out.append("narrow(%s) when in_pairs(slot(0), slot(1), [%s])"
                   % (to, ", ".join("[" + ", ".join(tr.t.name(x) for x in r) + "]"
                                    for r in rows)))
    elif method == "lowerForCartesianProduct":
        def elems(text):
            return [tr.t.name(x) for x in split_top(text.strip()[1:-1])]
        a, b = elems(args[0]), elems(args[1])
        rows = [[x, y] for x in a for y in b]
        out.append("lower in_pairs(slot(0), slot(1), [%s])"
                   % ", ".join("[" + ", ".join(r) + "]" for r in rows))
    elif method in ("lowerIfMemSizeNotByteSizePow2", "lowerIfMemSizeNotPow2"):
        mt = "mem_ty(mem_slot(0))"
        if method == "lowerIfMemSizeNotByteSizePow2":
            pred = ("(not is_byte_sized(%s) or not is_pow2(size_in_bytes_of(%s)))"
                    % (mt, mt))
        else:
            pred = "not is_pow2(size_in_bytes_of(%s))" % mt
        out.append("lower %s" % pred)
    elif method == "bitcast":
        out.append("bitcast(slot(0), %s)" % types(0, args[0]))
    else:
        raise Refuse("%s(...)" % method)
    if pred_arg is not None and method in (
            "minScalar", "maxScalar", "clampScalar", "widenScalarToNextPow2",
            "widenScalarOrEltToNextPow2OrMinSize", "scalarSameSizeAs"):
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
    if line.startswith("scalarize("):
        return line
    return line + " when " + gate


class Importer:
    def __init__(self, target, source=""):
        global PREFIX
        PREFIX = target[0].upper() + "_"
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
        if re.match(r"auto\s+\w+\s*=\s*\[", st):
            return          # align helper; parsed from the whole source
        if re.match(r"auto\s+\w+\s*=\s*\{", st):
            m = re.match(r"auto\s+(\w+)\s*=\s*\{(.*)\}$", st, re.S)
            self.t.sets[m.group(1)] = [x.strip() for x in split_top(m.group(2))]
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
// Generated by `tools/import-cxx.py {target} {src}`.  Do not edit by hand:
// re-run the importer instead.
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
    m = re.search(r"::\w+LegalizerInfo\s*\(const\s+\w+Subtarget\s*&\s*\w+\s*\)"
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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args(argv)

    imp = Importer(args.target, open(args.source).read())
    for name, rhs in member_types(args.source):
        imp.t.add(name, rhs, 0)
    imp.block(constructor_text(args.source))

    refusals = imp.p.refused + [(l, w) for l, w in imp.t.refused] + \
        [(0, w) for w in imp.tr.refused]
    notes = ""
    if refusals:
        notes = "// Refused (%d statement(s), not transcribed):\n" % len(refusals)
        for line, why in refusals[:40]:
            notes += "//   line %d: %s\n" % (line, why)
        notes += "//\n"
    name = args.target + "LegalizerInfo"
    body = render(imp)
    header = HEADER.format(name=name, src=args.source.split("/")[-1],
                           target=args.target, notes=notes)
    with open(args.out, "w") as f:
        f.write(header + body)
    rules = sum(len(rs.rules) for rs in imp.rulesets)
    print("%s: %d rulesets, %d rules, %d refused"
          % (args.out, sum(1 for rs in imp.rulesets if rs.rules), rules,
             len(refusals)))
    for line, why in refusals:
        print("  refused line %s: %s" % (line, why))
    if args.stats:
        print("%-40s %6s %6s" % ("method", "calls", "rules"))
        for k in sorted(STATS["calls"]):
            print("%-40s %6d %6d" % (k, STATS["calls"][k], STATS["rules"][k]))
        print("%-40s %6d %6d" % ("TOTAL", sum(STATS["calls"].values()),
                                 sum(STATS["rules"].values())))
    return 1 if refusals else 0


if __name__ == "__main__":
    sys.exit(main())
