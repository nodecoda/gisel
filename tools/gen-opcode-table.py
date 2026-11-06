#!/usr/bin/env python3
"""Regenerate gisel/data/generic_opcodes.json from GenericOpcodes.td.

Development only: the generated JSON is checked in, and every runtime path
(gisel lint / gen / eval) reads the JSON.  Nothing here runs llvm-tblgen.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gisel import dsl  # noqa: E402

DEFAULT_TD = Path("/home/ubuntu/llvm/trees/explore/llvm/include/llvm/Target/"
                  "GenericOpcodes.td")
OUT = ROOT / "gisel" / "data" / "generic_opcodes.json"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--td", default=str(DEFAULT_TD))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    table = dsl.build_arity_manifest(args.td)
    doc = {"schema": 1,
           "source": "llvm/include/llvm/Target/GenericOpcodes.td",
           "note": "arity = highest (p)typeN index + 1; null = variadic/unknown",
           "opcodes": {k: table[k] for k in sorted(table)}}
    Path(args.out).write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{args.out}: {len(table)} opcodes, "
          f"{sum(1 for v in table.values() if v is None)} unknown")
    return 0


if __name__ == "__main__":
    sys.exit(main())
