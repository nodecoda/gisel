#!/usr/bin/env python3
"""Point a legalizer constructor at a gisel-generated .inc.

    tools/ab/swap-source-ctor.py apply   --target aarch64 --tree TREE --inc INC
    tools/ab/swap-source-ctor.py restore --target aarch64 --tree TREE
    tools/ab/swap-source-ctor.py apply   --target x86 --build BUILD --inc INC

AArch64 and RISC-V spell the rules inline in the constructor, so there is no
generated .inc to replace.  ``apply`` swaps the constructor body for an
``#include`` of the generated fragment and leaves the rest of the translation
unit (custom legalization, helpers) untouched.  X86 already includes a
generated .inc; for it ``apply`` only replaces that file inside the build.

The original is kept under ``TREE/.gisel-swap`` (or ``BUILD/.gisel-swap``) so
``restore`` is byte exact.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

TARGETS = {
    "x86": {
        "source": "llvm/lib/Target/X86/GISel/X86LegalizerInfo.cpp",
        "ctor": "X86LegalizerInfo::X86LegalizerInfo(",
        "inc": "X86LegalizerInfo.inc",
        "subtarget": "X86Subtarget",
        "body": """\
{
  (void)TM;
#include "__INC__"
  verify(*STI.getInstrInfo());
}
""",
    },
    "aarch64": {
        "source": "llvm/lib/Target/AArch64/GISel/AArch64LegalizerInfo.cpp",
        "ctor": ("AArch64LegalizerInfo::AArch64LegalizerInfo("
                 "const AArch64Subtarget &ST)"),
        "inc": "AArch64LegalizerInfo.inc",
        "subtarget": "AArch64Subtarget",
    },
    "riscv": {
        "source": "llvm/lib/Target/RISCV/GISel/RISCVLegalizerInfo.cpp",
        "ctor": ("RISCVLegalizerInfo::RISCVLegalizerInfo("
                 "const RISCVSubtarget &ST)"),
        "inc": "RISCVLegalizerInfo.inc",
        "subtarget": "RISCVSubtarget",
    },
}

BODY = """\
{
  using namespace TargetOpcode;
  const __SUBTARGET__ &SubtargetRef = ST;
  (void)SubtargetRef;
  const TargetMachine &TM = ST.getTargetLowering()->getTargetMachine();
#include "__INC__"
  verify(*ST.getInstrInfo());
}
"""


def _body(subtarget, inc):
    return BODY.replace("__SUBTARGET__", subtarget).replace("__INC__", inc)


def _matching_brace(text, start):
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    raise SystemExit("unbalanced braces after constructor")


def _is_patched(text, inc):
    """True when the constructor body still points at a generated fragment."""
    return ('#include "%s"' % inc) in text


def _tuple_target(name):
    if name not in TARGETS:
        raise SystemExit("unknown target %r (known: %s)"
                         % (name, ", ".join(sorted(TARGETS))))
    return TARGETS[name]


def cmd_apply(args):
    if args.target == "x86" and args.build and not args.tree:
        if not args.build:
            raise SystemExit("x86 needs --build or --tree")
        build = Path(args.build).resolve()
        dest = build / "lib" / "Target" / "X86" / "X86LegalizerInfo.inc"
        backup = build / ".gisel-swap" / "X86LegalizerInfo.inc"
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copyfile(dest, backup)
        shutil.copyfile(args.inc, dest)
        print("x86: %s <- %s (original in %s)" % (dest, args.inc, backup))
        return 0

    spec = _tuple_target(args.target)
    tree = Path(args.tree).resolve()
    source = tree / spec["source"]
    text = source.read_text()
    start = text.find(spec["ctor"])
    if start < 0:
        raise SystemExit("constructor not found in %s" % source)
    brace = text.index("{", start)
    end = _matching_brace(text, brace)

    backup = tree / ".gisel-swap" / spec["source"]
    backup.parent.mkdir(parents=True, exist_ok=True)
    # A backup only means anything while the file it came from is patched.
    # A worktree that was patched in an earlier session and then committed
    # (or repaired by hand) would otherwise be restored to that old text and
    # silently lose the edits made since.
    if not (backup.exists() and _is_patched(text, spec["inc"])):
        shutil.copyfile(source, backup)
    inc_path = source.parent / spec["inc"]
    shutil.copyfile(args.inc, inc_path)
    template = spec.get("body")
    body = (template.replace("__INC__", spec["inc"])
            if template else _body(spec["subtarget"], spec["inc"]))
    source.write_text(text[:brace] + body + text[end + 1:])
    print("%s: %s patched, %s written (original in %s)"
          % (args.target, source, inc_path, backup))
    return 0


def cmd_restore(args):
    if args.target == "x86" and args.build and not args.tree:
        build = Path(args.build).resolve()
        dest = build / "lib" / "Target" / "X86" / "X86LegalizerInfo.inc"
        backup = build / ".gisel-swap" / "X86LegalizerInfo.inc"
        if not backup.exists():
            raise SystemExit("no backup at %s" % backup)
        shutil.copyfile(backup, dest)
        print("x86: restored %s" % dest)
        return 0

    spec = _tuple_target(args.target)
    tree = Path(args.tree).resolve()
    source = tree / spec["source"]
    backup = tree / ".gisel-swap" / spec["source"]
    if not _is_patched(source.read_text(), spec["inc"]):
        print("%s: %s is not patched, nothing to restore"
              % (args.target, source))
        return 0
    if not backup.exists():
        raise SystemExit("no backup at %s" % backup)
    shutil.copyfile(backup, source)
    inc_path = source.parent / spec["inc"]
    if inc_path.exists():
        inc_path.unlink()
    print("%s: restored %s" % (args.target, source))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="swap-source-ctor")
    parser.add_argument("mode", choices=("apply", "restore"))
    parser.add_argument("--target", required=True,
                        choices=sorted(TARGETS))
    parser.add_argument("--tree")
    parser.add_argument("--build")
    parser.add_argument("--inc")
    args = parser.parse_args(argv)
    if args.mode == "apply" and not args.inc:
        parser.error("apply needs --inc")
    if not args.tree and args.target != "x86":
        parser.error("%s needs --tree" % args.target)
    return cmd_apply(args) if args.mode == "apply" else cmd_restore(args)


if __name__ == "__main__":
    sys.exit(main())
