#!/usr/bin/env python3
"""Freeze the GenericOpcodes.td slot table (arity + pointer slots).

DEVELOPMENT ONLY.  Writes ``gisel/data/opcode-slots.json``: arity, pointer
slots, generic immediates.  That file is the only opcode snapshot; ``lint``
projects its arity instead of reading a second, derived file.

They used to be produced by different code, which left them disagreeing on 55
opcodes: the slot table did not follow ``def G_X : SomeClass;`` into the class
body, so all 40 ``G_ATOMICRMW_*`` / ``G_VECREDUCE_*`` had no arity, and the
arity view had no entry for the five opcodes whose slots the table did know
(``G_PHI``, ``G_BUILD_VECTOR``, ``G_MERGE_VALUES``, ``G_UNMERGE_VALUES``,
``G_CONCAT_VECTORS``) -- exactly the five ``lint`` reported as "arity unknown".

    python3 tools/gen-opcode-slots.py \
        /home/ubuntu/llvm/trees/explore/llvm/include/llvm/Target/GenericOpcodes.td
"""
import io
import json
import os
import re
import subprocess
import sys

DEF_RE = re.compile(
    r"^def\s+(G_[A-Z0-9_]+)\s*:\s*([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:<[^>]*>)?\s*(\{(?:[^{}]|\{[^{}]*\})*\}|;)", re.M)
# `def G_ATOMICRMW_OR : G_ATOMICRMW_OP;` carries no operand list of its own.
# The slot indices live in the class body, so follow one level of inheritance.
CLASS_RE = re.compile(
    r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>]*>)?\s*:\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>]*>)?\s*\{([^{}]*)\}", re.M)
CLASS_PARENT = {}
TYPE_RE = re.compile(r"(?<![A-Za-z0-9_])type(\d+)\b")
PTYPE_RE = re.compile(r"(?<![A-Za-z0-9_])ptype(\d+)\b")
# Only `untyped_imm_N` is a *generic immediate* operand; a bare `$imm` is an
# operand *name* whose kind is `unknown` (G_CONSTANT, G_FCONSTANT) and it does
# not add a generic imm slot.
IMM_RE = re.compile(r"(?<![A-Za-z0-9_])untyped_imm_(\d+)\b")


def _slots_of(body):
    slots = sorted(set(int(x) for x in TYPE_RE.findall(body))
                   | set(int(x) for x in PTYPE_RE.findall(body)))
    return slots, len(set(int(x) for x in IMM_RE.findall(body)))


def arity_of(body):
    """Type-slot count.

    A typed prefix wins even when the tail is variadic: ``G_BUILD_VECTOR``
    has ``type0``/``type1`` plus ``variable_ops`` and still has two type
    slots.  Only an instruction with no typed operand at all is "unknown"
    (``G_INTRINSIC``) or "none" (``G_BR``, ``G_TRAP``).
    """
    slots, _ = _slots_of(body)
    if slots:
        return max(slots) + 1
    return None if "variable_ops" in body else 0


def parse(path):
    text = io.open(path, encoding="utf-8", newline="").read()
    classes = {}
    for m in CLASS_RE.finditer(text):
        classes[m.group(1)] = m.group(3)
        CLASS_PARENT[m.group(1)] = m.group(2)

    def class_body(name, depth=0):
        """Follow `class A : B { ... }` chains; a one-level lookup missed
        `G_ATOMICRMW_FP_OP : G_ATOMICRMW_OP`, which only overrides a flag."""
        if depth > 8 or name not in classes:
            return None
        body = classes[name]
        if _slots_of(body)[0]:
            return body
        parent = CLASS_PARENT.get(name)
        inherited = class_body(parent, depth + 1) if parent else None
        return (body + "\n" + inherited) if inherited else body

    out = {}
    for m in DEF_RE.finditer(text):
        name, base, body = m.group(1), m.group(2), m.group(3)
        if body == ";":
            inherited = class_body(base)
            if inherited is not None:
                body = inherited
            elif base == "ConstrainedInstruction":
                # Resolved below from the base opcode.
                body = ""
            else:
                # An unknown base: say "unknown", do not invent 0.
                out[name] = {"arity": None, "ptype": [], "imm": 0}
                continue
        slots, imms = _slots_of(body)
        out[name] = {
            "arity": arity_of(body),
            "ptype": sorted(set(int(x) for x in PTYPE_RE.findall(body))),
            "imm": imms,
        }
    # `def G_STRICT_FADD : ConstrainedInstruction<G_FADD>;` has no operand list
    # of its own: it is the base opcode plus FP-environment operands LLVM adds
    # in TableGen, so the slots are the base's.
    base_of = {}
    for m in re.finditer(r"^def\s+(G_[A-Z0-9_]+)\s*:\s*"
                         r"ConstrainedInstruction<\s*(G_[A-Z0-9_]+)\s*>\s*;",
                         text, re.M):
        base_of[m.group(1)] = m.group(2)
    for name, base in base_of.items():
        if base in out:
            out[name] = dict(out[base])
    return out


def source_commit(path):
    """The LLVM revision the table was frozen from, if the tree can tell us."""
    try:
        out = subprocess.run(
            ["git", "-C", os.path.dirname(os.path.abspath(path)), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def main(argv):
    src = argv[1] if len(argv) > 1 else os.environ.get(
        "LLVM_TREE", "/home/ubuntu/llvm/trees/explore"
    ) + "/llvm/include/llvm/Target/GenericOpcodes.td"
    dst = argv[2] if len(argv) > 2 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "gisel", "data", "opcode-slots.json")
    opcodes = parse(src)
    doc = {
        "schema": 1,
        "source": "llvm/include/llvm/Target/GenericOpcodes.td",
        "note": "arity = highest (p)typeN index + 1; ptype = pointer slot indices; "
                "imm = generic immediate slot count; null arity = variadic/unknown",
        "opcodes": opcodes,
    }
    commit = source_commit(src)
    if commit:
        doc["source_commit"] = commit
    with open(dst, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    print("%s: %d opcodes" % (dst, len(opcodes)))



if __name__ == "__main__":
    sys.exit(main(sys.argv))
