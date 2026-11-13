# tools/ab moved

The A/B harness is now its own project: `/home/ubuntu/llvm/gisel-ab` (or the
`gisel-anchor`-style sibling checkout).  Nothing in gisel imports it, and
gisel's wheel never shipped it.

Kept for one release as a pointer so old links do not 404.

- Entry point: `gisel-ab/ab.py` (one verb table; `ab.py --help`)
- Package: `gisel-ab/src/gisel_ab/`
- Evidence: `gisel-ab/evidence/`
- Contract: `gisel-ab/CONTRACTS.md`
- Reports: `gisel-ab/docs/REPORT-ab.md`, `gisel-ab/docs/REQUIREMENTS-ab.md`
- Boundary: `gisel-ab/SCOPE.md` §7
