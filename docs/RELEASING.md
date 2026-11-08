# Releasing `gisel`

The package is pure Python (≥3.10, zero dependencies).  A release is a tag,
a CI-built wheel/sdist, and a Trusted Publishing upload — no tokens.

## 0. Preconditions (once)

Done (2026-11-06):

- remote `origin` = https://github.com/nodecoda/gisel (public).
- GitHub environment `pypi` exists.
- `ci.yml` is green on 3.10 / 3.11 / 3.12.
- **0.2.0 is on PyPI**: https://pypi.org/project/gisel/0.2.0/
  (wheel + sdist), uploaded once with `twine` and then by the `v0.2.0`
  tag pipeline; the repository secret `PYPI_API_TOKEN` authenticates it.
  `skip-existing: true` makes the tag run a green no-op.
- GitHub release: https://github.com/nodecoda/gisel/releases/tag/v0.2.0

Optional, better long-term: add a pending trusted publisher on PyPI
(owner `nodecoda`, repo `gisel`, workflow `publish.yml`, environment `pypi`)
and delete `password:` from the publish job — the action then uses OIDC and
the token secret can be revoked.

## 1. Bump the version in one place

```
gisel/__init__.py     __version__ = "0.3.0"
```

That is the only copy. `pyproject.toml` declares `dynamic = ["version"]` and
reads it via `[tool.setuptools.dynamic]`, and `gisel --version` prints it from
the same constant. `tests/test_cli.py` fails if the two ever disagree or if
`pyproject.toml` starts hardcoding a version again.

## 2. Build and check

```sh
python -m venv /tmp/rel && /tmp/rel/bin/pip install -q build twine
/tmp/rel/bin/python -m build                 # dist/*.whl, dist/*.tar.gz
/tmp/rel/bin/twine check dist/*
```

`twine check` must print PASSED for both files.  The wheel must contain
`gisel/data/generic_opcodes.json` (lint's arity table):

```sh
python -c "import zipfile,glob;z=zipfile.ZipFile(glob.glob('dist/*.whl')[0]);
print([n for n in z.namelist() if 'generic_opcodes' in n])"
```

## 3. Verify a clean install outside the checkout

```sh
python -m venv /tmp/ci && /tmp/ci/bin/pip install dist/*.whl
work=$(mktemp -d) && cp tests/corpus/AArch64LegalizerInfo.gisel "$work/"
cd "$work"
/tmp/ci/bin/gisel --version
/tmp/ci/bin/gisel lint AArch64LegalizerInfo.gisel
for e in inc check table core; do
  /tmp/ci/bin/gisel gen AArch64LegalizerInfo.gisel --emit=$e --out "a.$e"
done
```

The five artifacts must match `tests/artifacts/` (core modulo `origin`).

## 3.5. Product-surface checklist

The wheel ships one surface; check it before tagging:

- `gisel --help` lists exactly `gen check cases domain lint eval graph`
  (`tests/test_cli.py::Commands`), and every verb answers `--help`.
- `gisel diff` is rejected: that command lives in `tools/ab/diff.py`.
- The three exit codes mean the same thing everywhere (`spec/cli.md` §2):
  `0` yes, `1` no, `2` could not start.
- The wheel contains `gisel/data/generic_opcodes.json` and `gisel/data/opcode-slots.json`,
  and **no** `tools/`, `tests/` or `docs/` entries.
- `docs/SCOPE.md` and `spec/cli.md` are the two files a new surface has to
  update; if a release adds a command without them, it is not ready.

## 4. Tag and let CI publish

```sh
git tag -a v0.2.0 -m "gisel 0.2.0"
git push origin main --tags
```

`.github/workflows/publish.yml` builds, runs `twine check`, and uploads via
`pypa/gh-action-pypi-publish` when a `v*` tag is pushed.  A failing `ci.yml`
on the same commit should be treated as a release blocker.

## 5. Post-release check

```sh
python -m venv /tmp/after && /tmp/after/bin/pip install gisel==0.2.0
/tmp/after/bin/gisel --version
```

Known boundary: the wheel ships the opcode table but **not** `tests/`; the
corpus and frozen artifacts are repository-only.  Examples in the README
assume a checkout.
