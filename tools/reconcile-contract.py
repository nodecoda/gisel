#!/usr/bin/env python3
"""Reconcile "outside the verifier's contract" with "the runner had no answer".

`domain` enumerates every tuple the rules admit.  Some of those tuples are not
questions real MIR can ask (the verifier rejects the shape); some make the
legalizer abort.  Those are different sets, and this tool prints all three so
the difference is a number, not an argument:

    predicted_verifier   queries whose tuple fails a verifier-backed check
    predicted_crash      the subset whose failed check is marked "sound"
    observed             queries the runner answered with status unanswerable

The contract is `gisel/data/contract-aarch64.jsonc` (`--contract` overrides).
`sound` is a measurement, not a guess: it marks checks that had zero false
positives on the AArch64 domain, i.e. every tuple failing them aborted.

Exit code: 0 when every predicted crash was observed and every query has an
answer row; 1 when the sound contract predicts a crash that did not happen
(the contract is stale or the run is not comparable), or rows are missing;
2 on bad input.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
GISEL = HERE.parents[1]
sys.path.insert(0, str(GISEL))

from gisel import contract  # noqa: E402
from gisel import eval as E  # noqa: E402
from gisel import jsonl as J  # noqa: E402

DEFAULT_CONTRACT = GISEL / "gisel" / "data" / "contract-aarch64.jsonc"


def read_jsonl(path):
    with open(path) as stream:
        for line in stream:
            line = line.strip()
            if line:
                yield json.loads(line)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="reconcile-contract.py",
        description="compare verifier-contract predictions with unanswerable rows")
    ap.add_argument("queries", help="the domain query JSONL")
    ap.add_argument("answers", help="one side's answer JSONL")
    ap.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    contract.table(args.contract)  # fail early on a malformed table

    queries = {}
    for row in read_jsonl(args.queries):
        key = J.key(row)
        if key in queries:
            print("duplicate key in %s: %r" % (args.queries, key), file=sys.stderr)
            return 2
        queries[key] = row

    status = {}
    sites = collections.Counter()
    for row in read_jsonl(args.answers):
        key = J.key(row)
        status[key] = row.get("status", "answered")
        if row.get("assert_site"):
            sites[row["assert_site"]] += 1

    observed = {k for k, v in status.items() if v == "unanswerable"}
    missing = [k for k in queries if k not in status]
    extra = [k for k in status if k not in queries]

    verifier, crash = set(), set()
    for key, row in queries.items():
        types = [E.parse_case_llt(t) for t in row["types"]]
        result = contract.evaluate(row["name"], types, args.contract)
        if result["in_contract"]:
            continue
        verifier.add(key)
        if any(check.get("sound") for check in result["failed"]):
            crash.add(key)

    def by_opcode(keys):
        return dict(collections.Counter(k[1] for k in keys).most_common())

    report = {
        "contract": str(Path(args.contract).resolve()),
        "queries": len(queries),
        "answered": len(queries) - len(observed),
        "observed": len(observed),
        "predicted_verifier": len(verifier),
        "predicted_crash": len(crash),
        "crash_minus_observed": len(crash - observed),
        "observed_minus_crash": len(observed - crash),
        "verifier_minus_observed": len(verifier - observed),
        "observed_minus_crash_by_opcode": by_opcode(observed - crash),
        "verifier_minus_observed_by_opcode": by_opcode(verifier - observed),
        "missing_answers": len(missing),
        "extra_answers": len(extra),
        "sites": dict(sites.most_common()),
        "first_crash_minus_observed": [list(k) for k in
                                       sorted(crash - observed)[:5]],
    }

    if args.json:
        print(json.dumps(report, indent=1, sort_keys=True))
    else:
        print("queries              %7d" % report["queries"])
        print("answered             %7d" % report["answered"])
        print("observed unanswerable%7d" % report["observed"])
        print("predicted (verifier) %7d" % report["predicted_verifier"])
        print("predicted (crash)    %7d" % report["predicted_crash"])
        print("crash - observed     %7d" % report["crash_minus_observed"])
        print("observed - crash     %7d" % report["observed_minus_crash"])
        print("verifier - observed  %7d" % report["verifier_minus_observed"])
        for name, count in report["observed_minus_crash_by_opcode"].items():
            print("    residual %-24s %6d" % (name, count))
        for site, count in report["sites"].items():
            print("    site     %-24s %6d" % (site, count))
        if missing or extra:
            print("missing answers %d, extra answers %d"
                  % (len(missing), len(extra)))

    failed = report["crash_minus_observed"] or missing or extra
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
