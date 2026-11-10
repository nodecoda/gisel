# Releasing `gisel`

The package is pure Python (≥3.10, zero dependencies).  A release is a tag, a
CI-built wheel/sdist, and an upload through `publish.yml` — no local upload is
required.

## 0. Release history

| version | state | note |
|---|---|---|
| 0.2.0 | on PyPI | https://pypi.org/project/gisel/0.2.0/ — wheel + sdist, plus the GitHub release |
| 0.3.0 | unreleased | current `__version__`; adds `graph`, `eval --answers`, `feature NAME` predicates, `lint imm`, and the product-surface pin |

Infrastructure, done once (2026-11-06):

- remote `origin` = https://github.com/nodecoda/gisel (public);
- GitHub environment `pypi` exists;
- `ci.yml` is green on 3.10 / 3.11 / 3.12;
- `publish.yml` authenticates with the repository secret `PYPI_API_TOKEN` and
  `skip-existing: true`, so a tag pushed after a manual upload is a green
  no-op.

Optional, better long-term: add a pending trusted publisher on PyPI
(owner `nodecoda`, repo `gisel`, workflow `publish.yml`, environment `pypi`)
and delete `password:` from the publish job — the action then uses OIDC and
the token secret can be revoked.

## 1. Bump the version in one place

```
gisel/__init__.py     __version__ = "0.3.0"
```

That is the only copy. `pyproject.toml` declares `dynamic = ["version"]` and
reads it via `[tool.setuptools.dynamic]`; `gisel --version` prints the same
constant. `tests/test_cli.py::Version` fails if the two disagree, if
`pyproject.toml` starts hardcoding a version, or if it appears twice.

## 2. Build and check

```sh
python -m venv /tmp/rel && /tmp/rel/bin/pip install -q build twine
/tmp/rel/bin/python -m build                 # dist/*.whl, dist/*.tar.gz
/tmp/rel/bin/twine check dist/*
```

`twine check` must print PASSED for both files.  The wheel carries the two
bundled tables (`gisel/data/generic_opcodes.json` for `lint`,
`gisel/data/opcode-slots.json` for `domain`/`graph`) and nothing else from the
repository:

```sh
python - <<'PY'
import zipfile, glob
z = zipfile.ZipFile(glob.glob('dist/*.whl')[0])
names = z.namelist()
assert any(n.endswith('data/generic_opcodes.json') for n in names), names
assert any(n.endswith('data/opcode-slots.json') for n in names), names
leaked = [n for n in names if n.startswith(('tools/', 'tests/', 'docs/'))]
assert not leaked, leaked
assert any(n.endswith('licenses/LICENSE') for n in names), names
print(len(names), 'files')
PY
```

## 3. Verify a clean install outside the checkout

```sh
python -m venv /tmp/ci && /tmp/ci/bin/pip install dist/*.whl
work=$(mktemp -d) && cp tests/corpus/AArch64LegalizerInfo.gisel "$work/"
cd "$work"
/tmp/ci/bin/gisel --version
/tmp/ci/bin/gisel lint AArch64LegalizerInfo.gisel
for e in inc check core; do
  /tmp/ci/bin/gisel gen AArch64LegalizerInfo.gisel --emit=$e --out "a.$e"
done
```

The **three** artifacts must match `tests/artifacts/` (`core` modulo `origin`).
`tests/artifacts/` holds nine files: three artifacts for each of the three
transcribed targets (`X86`, `AArch64`, `RISC-V`), plus `SHA256`.

## 3.5. Product-surface checklist

The wheel ships one surface; check it before tagging:

- `gisel --help` lists exactly `gen check cases domain lint eval graph`
  (`tests/test_cli.py::Commands`), and every verb answers `--help`.
- `gisel diff` is rejected: that command lives in `ab/diff.py`.
- The three exit codes mean the same thing everywhere (`spec/cli.md` §2):
  `0` yes, `1` no, `2` could not start.
- `gisel/` imports no external-process or network module and no `tools/`
  module (`tests/test_scope.py`), matching `spec/cli.md` §3.
- `docs/SCOPE.md` and `spec/cli.md` are the two files a new surface has to
  update; if a release adds a command without them, it is not ready.
- Run the installed-file check **outside the checkout**.  At the repo root,
  `gisel.egg-info` wins the `importlib.metadata` lookup and the check silently
  inspects the build tree instead of the installed wheel (`ci.yml` `cd`s to
  `$RUNNER_TEMP` for this reason).

## 4. Tag and let CI publish

Take the tag from the package, so the tag cannot disagree with the wheel:

```sh
version=$(python -c 'import gisel; print(gisel.__version__)')
git tag -a "v$version" -m "gisel $version"
git push origin main --tags
```

`publish.yml` builds, runs `twine check`, and uploads on any `v*` tag.  A
failing `ci.yml` on the same commit is a release blocker.

## 5. Post-release check

```sh
version=$(python -c 'import gisel; print(gisel.__version__)')
python -m venv /tmp/after && /tmp/after/bin/pip install "gisel==$version"
/tmp/after/bin/gisel --version
```

Known boundary: the wheel ships the opcode tables but **not** `tests/`; the
corpus and frozen artifacts are repository-only.  Examples in the README
assume a checkout.
