#!/usr/bin/env python3
"""AB harness: one command for the LLVM legalizer differential loop.

    tools/ab/ab.py run --target x86 --tree TREE --build BUILD \
        --source tests/corpus/X86LegalizerInfo.gisel \
        --features tests/cases/x86-features.json \
        --queries QUERIES.jsonl --out OUT [--compare action|full]

This is the workbench side of the boundary in ``docs/SCOPE.md``: it consumes
the ``.inc`` and answerless queries produced by gisel, builds the official and
the replaced legalizer, runs both over one query file, and compares the
answers.  It does not call an LLM and it does not change gisel's command
surface.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gisel import answers as A  # noqa: E402
from gisel import eval as E  # noqa: E402

sys.path.insert(0, str(ROOT / "tools" / "ab"))
import attribute  # noqa: E402

TARGET_DIR = ROOT / "tools" / "ab" / "targets"
NINJA = os.environ.get("NINJA", "ninja")


class HarnessError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load_target(name: str) -> dict:
    path = TARGET_DIR / ("%s.json" % name)
    if not path.exists():
        known = sorted(p.stem for p in TARGET_DIR.glob("*.json"))
        raise HarnessError("unknown target %r (known: %s)"
                           % (name, ", ".join(known) or "none"))
    doc = read_json(path)
    required = ("schema", "name", "source", "strategy", "baseline_inc",
                "inc_name", "library", "runner", "features")
    missing = [key for key in required if key not in doc]
    if missing:
        raise HarnessError("%s: missing %s" % (path, ", ".join(missing)))
    if doc["schema"] != 1:
        raise HarnessError("%s: unsupported schema %r" % (path, doc["schema"]))
    if doc["strategy"] not in ("swap-library", "generated-ctor"):
        raise HarnessError("%s: unknown strategy %r"
                           % (path, doc["strategy"]))
    return doc


def git_head(tree: Path) -> str:
    proc = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    if proc.returncode:
        raise HarnessError("cannot read git HEAD from %s: %s"
                           % (tree, proc.stderr.strip()))
    return proc.stdout.strip()


def run_capture(cmd, cwd=None):
    return subprocess.run([str(part) for part in cmd], cwd=str(cwd or ROOT),
                          capture_output=True, text=True)


def run_checked(cmd, cwd=None):
    proc = run_capture(cmd, cwd)
    if proc.returncode:
        raise HarnessError("command failed (%d): %s\n%s"
                           % (proc.returncode,
                              " ".join(str(part) for part in cmd),
                              proc.stderr.strip()))
    return proc


def ninja(build: Path, target: str):
    run_checked([NINJA, "-C", build, target])


def touch(path: Path):
    os.utime(path, None)


class Lock:
    """One writer per state directory; flock is released on process exit."""

    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.handle = open(self.path, "w")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            raise HarnessError("another run holds %s" % self.path)
        self.handle.write(str(os.getpid()))
        self.handle.flush()
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()
        return False


def validate_queries(path: Path, features_path: Path, expected=None) -> int:
    try:
        table = E.load_features(str(features_path)).table
    except (OSError, ValueError, E.EvalError) as exc:
        raise HarnessError("cannot read features %s: %s"
                           % (features_path, exc))
    seen = set()
    count = 0
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                q = json.loads(line)
            except ValueError as exc:
                raise HarnessError("%s:%d: %s" % (path, lineno, exc))
            mem = q.get("mem")
            if mem is not None and len(mem) not in (2, 4):
                raise HarnessError("%s:%d: mem must be null, 2-tuple or "
                                   "4-tuple" % (path, lineno))
            try:
                key = A.key(q)
            except (KeyError, TypeError, ValueError, E.EvalError) as exc:
                raise HarnessError("%s:%d: %s" % (path, lineno, exc))
            if key[0] not in table:
                raise HarnessError("%s:%d: unknown config %r"
                                   % (path, lineno, key[0]))
            if key in seen:
                raise HarnessError("%s:%d: duplicate query key"
                                   % (path, lineno))
            seen.add(key)
            count += 1
    if expected is not None and count != expected:
        raise HarnessError("%s: %d queries, expected %d"
                           % (path, count, expected))
    return count


def ensure_baseline(target: dict, tree: Path, build: Path, state: Path,
                    refresh: bool = False) -> tuple[Path, dict]:
    base = state / "baseline"
    inc = build / target["baseline_inc"]
    if not inc.exists():
        raise HarnessError("baseline inc not found: %s" % inc)
    lib = build / target["library"]
    current = {
        "tree": str(tree),
        "build": str(build),
        "git_head": git_head(tree),
        "inc_sha256": sha256(inc),
        "lib_sha256": sha256(lib) if lib.exists() else None,
    }
    prov_path = base / "provenance.json"
    if prov_path.exists() and not refresh:
        prov = read_json(prov_path)
        if prov.get("inc_sha256") != current["inc_sha256"]:
            raise HarnessError(
                "baseline inc changed (%s -> %s); pass --refresh-baseline"
                % (prov.get("inc_sha256", "?")[:12],
                   current["inc_sha256"][:12]))
        if prov.get("git_head") != current["git_head"]:
            raise HarnessError(
                "baseline tree HEAD changed (%s -> %s); pass --refresh-baseline"
                % (prov.get("git_head", "?")[:12],
                   current["git_head"][:12]))
        if (prov.get("lib_sha256") is not None
                and prov["lib_sha256"] != current["lib_sha256"]):
            raise HarnessError(
                "baseline library changed (%s -> %s); pass --refresh-baseline"
                % (prov["lib_sha256"][:12],
                   (current["lib_sha256"] or "?")[:12]))
        return base, prov
    base.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(inc, base / target["inc_name"])
    if lib.exists():
        shutil.copyfile(lib, base / lib.name)
    prov_path.write_text(json.dumps(current, indent=2) + "\n")
    return base, current


def generate_inc(target: dict, source: Path, out: Path) -> Path:
    dest = out / target["inc_name"]
    run_checked([sys.executable, "-m", "gisel", "gen", source,
                 "--emit=inc", "--out", dest])
    if not dest.exists():
        raise HarnessError("gisel gen did not write %s" % dest)
    return dest


def build_swap_runner(target: dict, tree: Path, build: Path, out: Path,
                      name: str) -> Path:
    builder = ROOT / target["runner"]["builder"]
    runner = out / name
    run_checked(["bash", builder, tree, build, runner,
                 target["runner"].get("mode", "shipping")])
    return runner


def build_ctor_runners(target: dict, tree: Path, build: Path, inc: Path,
                       out: Path) -> tuple[Path, Path]:
    builder = ROOT / target["runner"]["builder"]
    prefix = out / "runner"
    run_checked(["bash", builder, tree, build, inc, prefix])
    return out / "runner.official", out / "runner.ours"


def answer(runner: Path, queries: Path, out: Path):
    run_checked([sys.executable, ROOT / "tools" / "ab" / "run-queries.py",
                 runner, queries, out])


def install_inc(target: dict, tree: Path, build: Path, inc: Path):
    dest = build / target["swap_inc"]
    if not dest.parent.exists():
        raise HarnessError("swap target directory does not exist: %s"
                           % dest.parent)
    shutil.copyfile(inc, dest)
    touch(dest)
    source = tree / target["touch_source"]
    if source.exists():
        touch(source)
    ninja(build, target["ninja_target"])
    want = sha256(inc)
    got = sha256(dest)
    if want != got:
        raise HarnessError("installed include was overwritten: %s != %s"
                           % (got[:12], want[:12]))


def restore_inc(target: dict, tree: Path, build: Path, baseline: Path,
                prov: dict):
    dest = build / target["swap_inc"]
    shutil.copyfile(baseline / target["inc_name"], dest)
    touch(dest)
    source = tree / target["touch_source"]
    if source.exists():
        touch(source)
    ninja(build, target["ninja_target"])
    got = sha256(dest)
    if got != prov["inc_sha256"]:
        raise HarnessError("restore did not reproduce the baseline inc "
                           "(%s != %s)" % (got[:12], prov["inc_sha256"][:12]))


def generate_core(target: dict, source: Path, out: Path) -> Path:
    dest = out / "core.json"
    run_checked([sys.executable, "-m", "gisel", "gen", source,
                 "--emit=core", "--out", dest])
    return dest


def run_eval(core: Path, features: Path, queries: Path, out: Path) -> tuple[Path, int]:
    dest = out / "eval.answers.jsonl"
    proc = run_capture([sys.executable, "-m", "gisel", "eval",
                        "--doc", core, "--features", features,
                        "--cases", queries, "--answers", dest])
    if proc.returncode not in (0, 1):
        raise HarnessError("gisel eval failed: %s" % proc.stderr.strip())
    return dest, proc.returncode


def compare(target: dict, ref: Path, ours: Path, out: Path, mode: str):
    proc = run_capture([sys.executable, ROOT / "tools" / "ab" / "diff.py",
                        ref, ours, "--json", "--compare", mode,
                        "--details", "1000000"])
    (out / "diff.json").write_text(proc.stdout)
    if proc.returncode == 2:
        raise HarnessError("diff failed: %s" % proc.stderr.strip())
    try:
        result = json.loads(proc.stdout)
    except ValueError as exc:
        raise HarnessError("diff produced invalid JSON: %s" % exc)
    return proc.returncode, result


def append_ledger(state: Path, record: dict):
    with open(state / "ledger.jsonl", "a") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def cmd_run(args) -> int:
    target = load_target(args.target)
    tree = Path(args.tree).resolve()
    build = Path(args.build).resolve()
    out = Path(args.out).resolve()
    state = Path(args.state or (ROOT / ".ab" / target["name"])).resolve()
    source = Path(args.source or (ROOT / target["source"])).resolve()
    features = Path(args.features or (ROOT / target["features"])).resolve()
    queries = Path(args.queries).resolve()
    if not tree.is_dir():
        raise HarnessError("tree not found: %s" % tree)
    if not build.is_dir():
        raise HarnessError("build not found: %s" % build)
    if not queries.exists():
        raise HarnessError("queries not found: %s" % queries)
    if not args.inc and not source.exists():
        raise HarnessError("source not found: %s" % source)
    if not features.exists():
        raise HarnessError("features not found: %s" % features)
    out.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)

    with Lock(state / "lock"):
        count = validate_queries(queries, features, target.get("query_count"))
        baseline, prov = ensure_baseline(target, tree, build, state,
                                         args.refresh_baseline)
        if args.inc:
            inc = out / target["inc_name"]
            shutil.copyfile(Path(args.inc).resolve(), inc)
        else:
            inc = generate_inc(target, source, out)
        inc_sha = sha256(inc)
        record = {
            "run_id": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                      + "-" + target["name"],
            "target": target["name"],
            "strategy": target["strategy"],
            "tree": str(tree),
            "build": str(build),
            "git_head": prov["git_head"],
            "source": str(source) if not args.inc else None,
            "inc": str(inc),
            "inc_sha256": inc_sha,
            "baseline_inc_sha256": prov["inc_sha256"],
            "features": str(features),
            "queries": str(queries),
            "query_sha256": sha256(queries),
            "query_count": count,
            "compare": args.compare,
        }
        core = None
        if not args.no_eval:
            if args.core:
                core = Path(args.core).resolve()
            elif args.inc:
                raise HarnessError("--core is required with --inc when eval is on")
            else:
                core = generate_core(target, source, out)
        if args.dry_run:
            print("target=%s strategy=%s tree=%s build=%s"
                  % (target["name"], target["strategy"], tree, build))
            print("inc=%s sha256=%s" % (inc, inc_sha[:16]))
            print("baseline_inc_sha256=%s" % prov["inc_sha256"][:16])
            print("queries=%s count=%d compare=%s"
                  % (queries, count, args.compare))
            print("eval=%s core=%s" % (not args.no_eval, core))
            print("out=%s state=%s" % (out, state))
            return 0

        official = out / "official.answers.jsonl"
        ours = out / "ours.answers.jsonl"
        cache_dir = state / "cache" / "official"
        cache_dir.mkdir(parents=True, exist_ok=True)
        runner_source = ROOT / target["runner"]["source"]
        cache_key = sha256_text(json.dumps({
            "target": target["name"],
            "git_head": prov["git_head"],
            "baseline_inc_sha256": prov["inc_sha256"],
            "lib_sha256": prov.get("lib_sha256"),
            "build_config": (sha256(build / "CMakeCache.txt")
                             if (build / "CMakeCache.txt").exists() else None),
            "query_sha256": sha256(queries),
            "runner_source_sha256": sha256(runner_source),
        }, sort_keys=True))
        cache_path = cache_dir / (cache_key + ".jsonl")
        cache_hit = (not args.no_cache) and cache_path.exists()
        record["official_cache"] = "off" if args.no_cache else (
            "hit" if cache_hit else "miss")
        rc = 0
        if target["strategy"] == "swap-library":
            if cache_hit:
                shutil.copyfile(cache_path, official)
            else:
                runner = build_swap_runner(target, tree, build, out,
                                           "runner.official")
                answer(runner, queries, official)
                record["official_runner_sha256"] = sha256(runner)
                shutil.copyfile(official, cache_path)
            body_error = None
            try:
                install_inc(target, tree, build, inc)
                runner = build_swap_runner(target, tree, build, out,
                                           "runner.ours")
                record["ours_runner_sha256"] = sha256(runner)
                answer(runner, queries, ours)
            except BaseException as exc:  # keep the build restorable
                body_error = exc
            try:
                restore_inc(target, tree, build, baseline, prov)
            except BaseException as exc:
                raise HarnessError("restore failed after run: %s" % exc)
            if body_error is not None:
                raise body_error
        elif target["strategy"] == "generated-ctor":
            runner_official, runner_ours = build_ctor_runners(
                target, tree, build, inc, out)
            record["official_runner_sha256"] = sha256(runner_official)
            record["ours_runner_sha256"] = sha256(runner_ours)
            if cache_hit:
                shutil.copyfile(cache_path, official)
            else:
                answer(runner_official, queries, official)
                shutil.copyfile(official, cache_path)
            answer(runner_ours, queries, ours)
        else:
            raise HarnessError("unknown strategy %r" % target["strategy"])

        rc, result = compare(target, official, ours, out, args.compare)
        if not args.no_eval:
            eval_answers, eval_rc = run_eval(core, features, queries, out)
            record["eval_rc"] = eval_rc
            query_map = attribute.load_queries(queries)
            official_map, e1 = A.load(official)
            ours_map, e2 = A.load(ours)
            eval_map, e3 = A.load(eval_answers)
            bundle = attribute.build_bundle(
                result, json.loads(core.read_text()), E.load_features(features),
                query_map, official_map, ours_map, eval_map)
            bundle["summary"]["reader_errors"] = e1 + e2 + e3
            bundle_dir = Path(args.bundle).resolve() if args.bundle else (out / "bundle")
            attribute.write_bundle(bundle, bundle_dir)
            record["bundle"] = str(bundle_dir)
            record["matrix"] = bundle["summary"]["matrix"]
        record["diff"] = {
            key: result[key] for key in
            ("mode", "ref", "ours", "matched", "agree", "disagree",
             "unanswerable", "missing_ref", "missing_ours", "errors")
        }
        record["first_classes"] = {
            cls: sum(1 for item in result.get("first_details", [])
                     if item["class"] == cls)
            for cls in ("status", "action", "type_idx", "new_type")
        }
        record["rc"] = rc
        append_ledger(state, record)
        print("target=%s compare=%s queries=%d agree=%d disagree=%d "
              "unanswerable=%d missing_ref=%d missing_ours=%d rc=%d"
              % (target["name"], args.compare, result["matched"],
                 result["agree"], result["disagree"],
                 result["unanswerable"], result["missing_ref"],
                 result["missing_ours"], rc))
        print("official=%s" % official)
        print("ours=%s" % ours)
        print("diff=%s" % (out / "diff.json"))
        return rc


def cmd_verify(args) -> int:
    target = load_target(args.target)
    tree = Path(args.tree).resolve()
    build = Path(args.build).resolve()
    state = Path(args.state or (ROOT / ".ab" / target["name"])).resolve()
    prov_path = state / "baseline" / "provenance.json"
    if not prov_path.exists():
        raise HarnessError("no baseline in %s" % state)
    prov = read_json(prov_path)
    inc = build / target["baseline_inc"]
    if not inc.exists():
        raise HarnessError("baseline inc not found: %s" % inc)
    got = sha256(inc)
    ok = got == prov["inc_sha256"]
    print("inc=%s sha256=%s baseline=%s %s"
          % (inc, got[:16], prov["inc_sha256"][:16],
             "OK" if ok else "MISMATCH"))
    return 0 if ok else 1


def build_parser():
    ap = argparse.ArgumentParser(
        prog="tools/ab/ab.py",
        description="AB harness for the LLVM legalizer differential loop")
    sub = ap.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="build both sides, answer, diff, restore")
    run.add_argument("--target", required=True,
                     help="adapter name under tools/ab/targets")
    run.add_argument("--tree", required=True, help="LLVM source tree")
    run.add_argument("--build", required=True, help="LLVM build directory")
    run.add_argument("--queries", required=True,
                     help="answerless query JSONL")
    run.add_argument("--out", required=True, help="artifact directory")
    run.add_argument("--source", help=".gisel source (default: adapter)")
    run.add_argument("--inc", help="prebuilt inc, skip gisel gen")
    run.add_argument("--features",
                     help="feature truth table (default: adapter)")
    run.add_argument("--state", help="baseline/ledger directory")
    run.add_argument("--compare", choices=("action", "full"), default="full",
                     help="action: smoke; full: acceptance (default)")
    run.add_argument("--refresh-baseline", action="store_true",
                     help="replace a stale baseline snapshot")
    run.add_argument("--dry-run", action="store_true",
                     help="validate inputs, generate inc, print plan")
    run.add_argument("--core", help="prebuilt core JSON (default: gisel gen)")
    run.add_argument("--bundle",
                     help="bundle directory (default: OUT/bundle)")
    run.add_argument("--no-eval", action="store_true",
                     help="skip the three-way eval matrix")
    run.add_argument("--no-cache", action="store_true",
                     help="do not reuse official answers")
    run.set_defaults(func=cmd_run)

    verify = sub.add_parser("verify", help="check the build is back on baseline")
    verify.add_argument("--target", required=True)
    verify.add_argument("--tree", required=True)
    verify.add_argument("--build", required=True)
    verify.add_argument("--state")
    verify.set_defaults(func=cmd_verify)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except HarnessError as exc:
        print("ab: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
