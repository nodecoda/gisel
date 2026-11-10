"""The shape contract: which type tuples the MIR verifier would never see.

A *question* is `(opcode, types, mem, imms)`.  Some tuples cannot come from
real MIR at all -- `G_CONCAT_VECTORS` with a non-vector destination, a shift
mixing scalars and vectors, `G_MERGE_VALUES` on vectors.  Asking the legalizer
about them produces answers that no `llc` input can reach, and sometimes makes
the legalizer assert.  They are not part of the domain.

The rules live in `gisel/data/contract-shapes.jsonc`, one entry per opcode,
each with a `source` naming the verifier check it transcribes.  A rule without
a source is rejected at load time: a shape claim about LLVM is either quoted
from upstream or it is a guess, and the file does not keep guesses.

Two shapes of rule are supported:

  checks   every check must hold for the tuple to stay in contract
  any_of   at least one branch must hold (used for `G_UNMERGE_VALUES`, whose
           scalar and vector forms are checked differently)

Check vocabulary (all predicates are in `gisel.eval`'s LLT tuple model):

  {"slot": n, "kind": k}
  {"all_slots": k}
  {"relation": r, "slots": [...]}

  kinds      scalar, vector, pointer, integer, float,
             integer_scalar_or_vector, not_vector, scalar_or_pointer
  relations  same_lane_count   same vector-ness and lane count
             same_element      equal element type
             same_shape        both vector or both scalar
             same_element_all  every slot shares element type and scalability
             dest_lanes_double destination has twice the lanes of the source
"""

from __future__ import annotations

import json
from pathlib import Path

from . import eval as E

DATA = Path(__file__).resolve().parent / "data" / "contract-shapes.jsonc"

_KINDS = {
    "scalar": E.is_scalar,
    "vector": E.is_vector,
    "not_vector": lambda t: not E.is_vector(t),
    "pointer": E.is_pointer,
    "integer": E.is_integer,
    "float": E.is_float,
    "scalar_or_pointer": lambda t: E.is_scalar(t) or E.is_pointer(t),
    # The comparison result is ANY_SCALAR-shaped: `i32` (extended integer)
    # is deliberately not accepted here, matching the filter that has been
    # running since 9e59c9d.
    "integer_scalar_or_vector": lambda t: (
        (not E.is_vector(t) and t[0] == "scalar")
        or (E.is_vector(t) and t[3][0] == "scalar")),
}


def _same_lane_count(a, b):
    return E.is_vector(a) == E.is_vector(b) and (
        not E.is_vector(a) or a[1] == b[1])


def _same_element(a, b):
    return E.llt_eq(a[3], b[3])


_RELATIONS = {
    "same_lane_count": _same_lane_count,
    "same_element": _same_element,
    "same_shape": lambda a, b: E.is_vector(a) == E.is_vector(b),
    "dest_lanes_double": lambda dst, src: dst[1] == src[1] * 2,
}


def _strip_jsonc(text):
    """Remove // and /* */ comments outside strings."""
    out = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _branch_ok(branch, types):
    if "min_slots" in branch and len(types) < branch["min_slots"]:
        return False
    for check in branch.get("checks", []):
        if "slot" in check:
            if check["slot"] >= len(types):
                return False
            if not _KINDS[check["kind"]](types[check["slot"]]):
                return False
        elif "all_slots" in check:
            kind = _KINDS[check["all_slots"]]
            if not all(kind(t) for t in types):
                return False
        elif check.get("relation") == "same_element_all":
            first = types[0][3] if E.is_vector(types[0]) else types[0]
            if not all(E.llt_eq(t[3] if E.is_vector(t) else t, first)
                       for t in types):
                return False
            if not all(E.is_vector(t) and t[2] == types[0][2] for t in types):
                return False
        else:
            slots = check.get("slots", [])
            if any(s >= len(types) for s in slots):
                return False
            fn = _RELATIONS[check["relation"]]
            if not all(fn(types[a], types[b])
                       for a, b in zip(slots, slots[1:])):
                return False
    return True


def validate(document, path="<contract>"):
    """Reject a table that cannot be used as a contract."""
    if document.get("schema") != "gisel-contract/1":
        raise ValueError("%s: unknown schema %r" % (path, document.get("schema")))
    seen = set()
    for rule in document.get("rules", []):
        opcode = rule.get("opcode")
        if not opcode:
            raise ValueError("%s: rule without opcode" % path)
        if opcode in seen:
            raise ValueError("%s: duplicate rule for %s" % (path, opcode))
        seen.add(opcode)
        if not rule.get("source"):
            raise ValueError("%s: %s has no source" % (path, opcode))
        branches = rule.get("any_of") or [rule]
        for branch in branches:
            for check in branch.get("checks", []):
                if "slot" in check and check["kind"] not in _KINDS:
                    raise ValueError("%s: %s: unknown kind %r"
                                     % (path, opcode, check["kind"]))
                if "all_slots" in check and check["all_slots"] not in _KINDS:
                    raise ValueError("%s: %s: unknown kind %r"
                                     % (path, opcode, check["all_slots"]))
                if ("relation" in check
                        and check["relation"] not in _RELATIONS
                        and check["relation"] != "same_element_all"):
                    raise ValueError("%s: %s: unknown relation %r"
                                     % (path, opcode, check["relation"]))
    return document


_CACHE = {}


def table(path=None):
    path = Path(path or DATA)
    if path not in _CACHE:
        document = validate(json.loads(_strip_jsonc(path.read_text())), path)
        _CACHE[path] = {rule["opcode"]: rule for rule in document["rules"]}
    return _CACHE[path]


def check(opcode, types, path=None):
    """True when the tuple is a question the verifier could pass to us."""
    rule = table(path).get(opcode)
    if rule is None:
        return True
    if rule.get("short_ok") and len(types) < rule.get("min_slots", 0):
        return True
    branches = rule.get("any_of") or [rule]
    return any(_branch_ok(branch, types) for branch in branches)
