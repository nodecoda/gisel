# Releasing `gisel`

The package is pure Python (≥3.10, zero dependencies).  A release is a tag,
a CI-built wheel/sdist, and a Trusted Publishing upload — no tokens.

## 0. Preconditions (once)

- A git remote exists (`git remote -v`).  The repository currently has none,
  so this is the first blocking step.
- GitHub: Settings → Environments → `pypi` (no secrets; OIDC only).
- PyPI: the project is registered as a Trusted Publisher for
  `owner/repo` + workflow `publish.yml` + environment `pypi`.

## 1. Bump the version in both places

```
pyproject.toml        version = "0.2.0"
gisel/cli.py          version="gisel 0.2.0"
```

They are deliberately duplicated so `gisel --version` works without parsing
packaging metadata; `tests/test_artifacts.py` fails if they drift.

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
/usr/bin/env -S /tmp/ci/bin/gisel --version
/tmp/ci/bin/gisel lint AArch64LegalizerInfo.gisel
for e in td inc check table core; do
  /tmp/ci/bin/gisel gen AArch64LegalizerInfo.gisel --emit=$e --out "a.$e"
done
```

The five artifacts must match `tests/artifacts/` (core modulo `origin`).

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
