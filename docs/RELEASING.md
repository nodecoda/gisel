# Releasing `gisel`

The package is pure Python (≥3.10, zero dependencies).  A release is a tag, a
CI-built wheel/sdist, and an upload through `publish.yml` — no local upload is
required.

## 0. Release history

| version | state | note |
|---|---|---|
| 0.2.0 | on PyPI | https://pypi.org/project/gisel/0.2.0/ — wheel + sdist, plus the GitHub release |
| 0.3.0 | unreleased | current `__version__`; adds `graph`, `eval --answers`, `feature NAME` predicates, `lint imm`, the product-surface pin, **the nine corpora inside the wheel** (`gisel/data/corpus`, `gisel/data/cases`), `--corpus NAME` on every verb that reads a `.gisel` file, and `doctor` |

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

Build from a clean tree.  setuptools reuses `build/lib`, so a file deleted
from `gisel/` survives there and lands in the next wheel:

```sh
python -m venv /tmp/rel && /tmp/rel/bin/pip install -q build twine
python - <<'PY'
import pathlib, shutil
for name in ("build", "dist"):
    shutil.rmtree(pathlib.Path(name), ignore_errors=True)
for path in pathlib.Path(".").glob("*.egg-info"):
    shutil.rmtree(path, ignore_errors=True)
PY
/tmp/rel/bin/python -m build                 # dist/*.whl, dist/*.tar.gz
/tmp/rel/bin/twine check dist/*
```

This is not hypothetical: a wheel built over a stale `build/` carried
`gisel/data/generic_opcodes.json`, a file the source tree had already deleted.

`twine check` must print PASSED for both files.  Build in the venv above,
not with the system `pip wheel`: Debian's pip 22 + setuptools 59 silently
builds an empty `UNKNOWN-0.0.0-py3-none-any.whl` even though the isolated
build installs `setuptools>=77`.  `python -m build` (the path CI uses) does
not have that problem.

The wheel carries the one bundled opcode table (`gisel/data/opcode-slots.json`,
read by `lint`, `domain` and `graph`) and nothing else from the repository:

```sh
python - <<'PY'
import zipfile, glob
z = zipfile.ZipFile(glob.glob('dist/*.whl')[0])
names = z.namelist()
assert any(n.endswith('data/opcode-slots.json') for n in names), names
assert not any(n.endswith('data/generic_opcodes.json') for n in names), names
leaked = [n for n in names if n.startswith(('tools/', 'tests/', 'docs/'))]
assert not leaked, leaked
assert any(n.endswith('licenses/LICENSE') for n in names), names
# The product surface 0.2.0 predates: cases/domain/graph, and the .td path
# must stay out (it was removed from the source tree, not just unwired).
for want in ('gisel/cases.py', 'gisel/domain.py', 'gisel/graph.py'):
    assert any(n.endswith(want) for n in names), (want, names)
for gone in ('gisel/td.py', 'gisel/backend/table.py'):
    assert not any(n.endswith(gone) for n in names), (gone, names)
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

## 4 三仓 cohort

`cases` 和 `graph` 的证据横跨三个仓；发布时三者必须是同一组 commit，否则
`RELEASE.json` 里记的东西无法从 tag 复现。

| 仓 | 放什么 |
|---|---|
| `gisel` | corpus、cases / graph goldens、`inc`/`core` 产物 |
| `upstream-source` | importer、`PIN.json`、`import-report.json` |
| `ab` | 对拍工作台、冻结证据 |

发版前在三个干净的工作区各跑一次（`gisel` 根目录）：

```sh
python3 -m unittest discover -q -s tests
bash tools/check-nine-corpora.sh
bash tools/check-graph-golden.sh          # 约 3m30s（并行）
bash tools/check-cases-golden.sh          # 约 6 分钟（三个 target 并行）
bash tools/check-nightly-graphs.sh        # 约 9 分钟（五个贵配置并行）
python3 tools/check-claims.py
(cd ../upstream-source && python3 import/import-cxx.py --all \
   --pin pin/PIN.json --git-repo /tmp/llvm --check)
(cd ../ab && VERIFY_FROZEN=1 ./verify-evidence.sh)
tools/release-manifest.py                 # 写 ../ab/RELEASE.json
```

`tools/release-manifest.py` 拒绝脏工作区：先提交，再生成清单。清单只记录
commit、sha 和门禁命令，不替代它们。

最后三仓打同一个 tag。**注意**：`publish.yml` 在 `v*` tag 上会发布到 PyPI，
所以打 tag 是外发动作，需要人工确认版本号（`gisel/__init__.py`）与发布历史
一致后再执行。
