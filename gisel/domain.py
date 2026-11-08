#!/usr/bin/env python3
"""Enumerate the answerless query domain (D*) for one `.gisel` source.

This is deliberately not a test-case generator: it never evaluates a rule.
The axes come from upstream facts -- the opcode's declared type slots
(`data/opcode-slots.json`) and the source's type/memory declarations -- so the
query set cannot be biased towards the rules under test.

Output is the same JSONL query shape the oracle dumps use, without the
`action` / `type_idx` / `new_type` columns:

    {"config": "C0", "name": "G_LOAD", "types": ["s8", "p0:64"],
     "mem": ["s8", 1], "imms": []}

The domain is finite and configuration-specific: the pointer width is a
property of the subtarget, so a mixed 32/64-bit configuration set needs one
run per width (`--pointer-width 32` / `64`).
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

from . import ast as A
from . import cases as C
from . import eval as E
from . import dsl


def _data_path(name):
    return Path(__file__).resolve().parent / "data" / name


def load_opcode_slots(path=None):
    """The frozen GenericOpcodes.td table: arity plus pointer slot indices."""
    raw = json.loads(Path(path).read_text() if path else
                     _data_path("opcode-slots.json").read_text())
    return raw.get("opcodes", raw)


def _resolve(text, pointer_width):
    """Turn a configuration-dependent pointer spelling into a concrete one."""
    return text.replace("p0:*", "p0:%d" % pointer_width).replace(
        "p0:64", "p0:%d" % pointer_width)


def _bits(t):
    if t[0] in ("scalar", "integer", "float"):
        return t[1]
    if t[0] == "pointer":
        return t[2] if t[2] != "*" else None
    if t[0] == "vector":
        elem = _bits(t[3])
        return t[1] * elem if elem else None
    if t[0] == "bf16":
        return 16
    return None


def _named_types(source, pointer_width):
    """Every declared named type, with `p0:*` resolved for this subtarget.

    The core document drops wildcard spellings from `domain.types`, which
    loses `v2p0` / `v4p0`.  They are real domain values, so recover them from
    the source declarations rather than from the normal form.
    """
    gs = A.parse_program(Path(source).read_text())
    out = set()
    for decl in gs.decls:
        if isinstance(decl, A.NamedType):
            out.add(_resolve(A.llt_text(decl.llt), pointer_width))
    return out


def _walk_mem_rows(node, out, pointer_width):
    if isinstance(node, dict):
        if node.get("kind") == "inMemDesc":
            args = node.get("args", [])
            if len(args) >= 4 and isinstance(args[3], dict):
                for row in args[3].get("elems", []):
                    if isinstance(row, (list, tuple)) and len(row) >= 4:
                        for text in C.type_value_spellings(row[2]):
                            mty = _resolve(text, pointer_width)
                            try:
                                t = E.parse_case_llt(mty)
                            except E.EvalError:
                                continue
                            bits = _bits(t)
                            if bits:
                                out.add((mty, bits, int(row[3])))
        for value in node.values():
            _walk_mem_rows(value, out, pointer_width)
    elif isinstance(node, list):
        for value in node:
            _walk_mem_rows(value, out, pointer_width)


def _reads_mem(node):
    if isinstance(node, dict):
        if node.get("kind") in ("inMemDesc", "memSlot", "memSize",
                                "typeDiffersFromMemDesc"):
            return True
        return any(_reads_mem(v) for v in node.values())
    if isinstance(node, list):
        return any(_reads_mem(v) for v in node)
    return False


def domain_axes(source, pointer_width=64):
    """`(types, mems, doc)` for one source and pointer width."""
    doc = C.document(source)
    types = {_resolve(t, pointer_width) for t in doc["domain"]["types"]}
    types |= _named_types(source, pointer_width)
    mems = set()
    for rs in doc["rulesets"]:
        for rule in rs["rules"]:
            _walk_mem_rows(rule["predicate"], mems, pointer_width)
    return sorted(types), sorted(mems), doc


def enumerate_domain(source, features, configs=None, pointer_width=64,
                     slots=None):
    """Yield answerless queries for every (config, opcode, types, mem)."""
    types, mems, doc = domain_axes(source, pointer_width)
    slots = slots if slots is not None else load_opcode_slots()
    manifest = dsl.load_arity_manifest()
    configs = list(configs or sorted(features.table))
    skipped = []

    for rs in doc["rulesets"]:
        uses_mem = any(_reads_mem(rule["predicate"]) for rule in rs["rules"])
        mem_axis = list(mems) if uses_mem else [None]
        for opcode in rs["opcodes"]:
            info = slots.get(opcode, {})
            arity = info.get("arity")
            if arity is None:
                arity = manifest.get(opcode)
            if arity is None:
                skipped.append(opcode)
                continue
            ptype = set(info.get("ptype", ()))
            axes = [[_resolve("p0:*", pointer_width)] if i in ptype else types
                    for i in range(arity)]
            for config in configs:
                for combo in itertools.product(*axes):
                    for mem in mem_axis:
                        yield {
                            "config": config,
                            "name": opcode,
                            "types": list(combo),
                            "mem": [mem[0], mem[2]] if mem else None,
                            "imms": [],
                        }
    if skipped:
        # Surface rather than silently narrowing the domain.
        sys.stderr.write("domain: skipped %d opcode(s) with unknown arity: %s\n"
                         % (len(skipped), ", ".join(sorted(set(skipped))[:8])))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="gisel domain",
        description="enumerate the answerless query domain (D*)")
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--features",
                    help="feature truth table (default: derive none/all/only-N)")
    ap.add_argument("--config", action="append", dest="configs",
                    help="limit to configs from --features (repeatable)")
    ap.add_argument("--pointer-width", type=int, default=64,
                    help="subtarget pointer width (default 64)")
    ap.add_argument("--slots", help="opcode slot table (default: bundled)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    doc = C.document(args.source)
    features = C.derive_features(doc, args.features, args.configs)
    configs = sorted(features.table)
    if not configs:
        print("domain: no configurations selected", file=sys.stderr)
        return 2

    slots = load_opcode_slots(args.slots)
    rows = list(enumerate_domain(args.source, features, configs,
                                 args.pointer_width, slots))
    rows.sort(key=lambda q: (q["config"], q["name"], tuple(q["types"]),
                             json.dumps(q["mem"])))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    types, mems, _ = domain_axes(args.source, args.pointer_width)
    stats = {
        "configs": configs,
        "types": len(types),
        "mems": len(mems),
        "points": len(rows),
        "per_config": {c: sum(1 for r in rows if r["config"] == c)
                       for c in configs},
        "per_opcode": len({r["name"] for r in rows}),
    }
    if args.json:
        print(json.dumps(stats, indent=1, sort_keys=True))
    else:
        print("%s: points=%d configs=%s types=%d mems=%d opcodes=%d"
              % (args.out, stats["points"], ",".join(configs),
                 stats["types"], stats["mems"], stats["per_opcode"]))
    return 0 if rows else 2


if __name__ == "__main__":
    sys.exit(main())
