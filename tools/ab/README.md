# tools/ab moved

The A/B harness is now its own project: `/home/ubuntu/llvm/ab` (or the
`upstream-source`-style sibling checkout).  Nothing in gisel imports it, and
gisel's wheel never shipped it.

Kept for one release as a pointer so old links do not 404.

- Harness: `ab/ab.py`, `ab/diff.py`, `ab/attribute.py`, `ab/run-queries.py`
- Contract: `ab/CONTRACTS.md`
- Reports: `ab/docs/REPORT-ab.md`, `ab/docs/REQUIREMENTS-ab.md`
- Boundary: `docs/SCOPE.md` §7
