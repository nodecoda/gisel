#!/usr/bin/env python3
"""Freeze the GenericOpcodes.td slot table (arity + pointer slots).

DEVELOPMENT ONLY.  The domain enumerator reads the committed JSON so that
`gisel domain` works without an LLVM source tree, exactly like
`gisel/data/generic_opcodes.json` does for lint.

    python3 tools/gen-opcode-slots.py \
        /home/ubuntu/llvm/trees/explore/llvm/include/llvm/Target/GenericOpcodes.td
"""
import io
import json
import os
import re
import sys

DEF_RE = re.compile(
    r"^def\s+(G_[A-Z0-9_]+)\s*:\s*GenericInstruction\s*"
    r"(\{(?:[^{}]|\{[^{}]*\})*\}|;)", re.M)
TYPE_RE = re.compile(r"(?<![A-Za-z0-9_])type(\d+)\b")
PTYPE_RE = re.compile(r"(?<![A-Za-z0-9_])ptype(\d+)\b")


def parse(path):
    text = io.open(path, encoding="utf-8", newline="").read()
    out = {}
    for m in DEF_RE.finditer(text):
        body = m.group(2)
        slots = sorted(set(int(x) for x in TYPE_RE.findall(body))
                       | set(int(x) for x in PTYPE_RE.findall(body)))
        out[m.group(1)] = {
            "arity": (max(slots) + 1) if slots else None,
            "ptype": sorted(set(int(x) for x in PTYPE_RE.findall(body))),
        }
    return out


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
                "null arity = variadic/unknown",
        "opcodes": opcodes,
    }
    with open(dst, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    print("%s: %d opcodes" % (dst, len(opcodes)))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
