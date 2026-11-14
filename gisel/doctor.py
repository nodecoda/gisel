"""`gisel doctor`: is this installation able to do its job?

gisel is pure Python over files, so "broken" is narrow and checkable: a
Python too old for the syntax, a package that shipped without its data, a
corpus manifest pointing at a file that is not there, a command that no
longer dispatches.  Everything printed here can be recomputed by hand; the
point is to say which one failed and what to do next, instead of an
AttributeError three steps later.

Exit codes follow `spec/cli.md`: 0 every check passed, 2 something failed
(the run could not establish that the tool works).
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

OK, FAIL = "ok", "fail"


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""

    def as_dict(self) -> dict:
        out = {"name": self.name, "status": self.status, "detail": self.detail}
        if self.fix:
            out["fix"] = self.fix
        return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _python() -> Check:
    version = ".".join(str(n) for n in sys.version_info[:3])
    if sys.version_info < (3, 10):
        return Check("python", FAIL, version,
                     "gisel needs Python 3.10 or newer; install one and "
                     "re-run with it")
    return Check("python", OK, version)


def _version() -> Check:
    from . import __version__
    return Check("version", OK, __version__)


def _install() -> Check:
    """Where this gisel came from: pypi, a git commit, or a checkout.

    Support questions start with "which one am I running", and the answer is
    already on disk: pip writes `direct_url.json` for `git+`/local installs,
    and metadata outside a site-packages directory can only be a source tree.
    This check never fails -- a checkout is a supported way to run gisel, and
    a broken *install* shows up in the checks below, not here.
    """
    from importlib import metadata
    from . import __version__
    try:
        dist = metadata.distribution("gisel")
    except metadata.PackageNotFoundError:
        return Check("install", OK, "checkout (no installed metadata)")
    try:
        raw = dist.read_text("direct_url.json")
    except OSError:
        raw = None
    if raw:
        try:
            direct = json.loads(raw)
        except json.JSONDecodeError:
            direct = {}
        vcs = direct.get("vcs_info") or {}
        if vcs:
            commit = str(vcs.get("commit_id") or "")[:12]
            return Check("install", OK, "git %s" % (commit or "unknown"))
        url = str(direct.get("url") or "")
        if url.startswith("file://") or "dir_info" in direct:
            path = url[len("file://"):] if url.startswith("file://") else ""
            return Check("install", OK, "checkout %s" % (path or "unknown"))
    root = str(dist.locate_file(""))
    if "site-packages" in root or "dist-packages" in root:
        return Check("install", OK, "pypi %s" % __version__)
    return Check("install", OK, "checkout %s" % root)


def _data_dir() -> Path:
    from . import corpus
    return corpus.DATA


def _opcode_slots() -> Check:
    path = _data_dir() / "opcode-slots.json"
    try:
        doc = json.loads(path.read_text())
    except FileNotFoundError:
        return Check("opcode-slots", FAIL, "missing: %s" % path,
                     "reinstall gisel; the wheel must carry gisel/data/*.json")
    except json.JSONDecodeError as exc:
        return Check("opcode-slots", FAIL, "bad JSON: %s" % exc,
                     "reinstall gisel; the file is package data, not editable")
    commit = str(doc.get("source_commit", ""))
    if len(commit) != 40:
        return Check("opcode-slots", FAIL,
                     "schema %s, source_commit %r" % (doc.get("schema"),
                                                      commit),
                     "reinstall gisel: the table must name the LLVM commit "
                     "it was generated from")
    return Check("opcode-slots", OK,
                 "schema %s, commit %s" % (doc.get("schema"), commit[:12]))


def _corpora() -> list[Check]:
    from . import corpus as corpora
    try:
        names = corpora.names()
    except corpora.CorpusError as exc:
        return [Check("corpora", FAIL, str(exc),
                      "reinstall gisel; gisel/data/corpora.json is package "
                      "data")]
    if not names:
        return [Check("corpora", FAIL, "the manifest lists no targets",
                      "reinstall gisel")]
    checks = [Check("corpora", OK, "%d targets: %s"
                    % (len(names), " ".join(names)))]
    for name in names:
        try:
            entry = corpora.get(name)
        except corpora.CorpusError as exc:
            checks.append(Check("corpus:%s" % name, FAIL, str(exc),
                                "reinstall gisel; `--corpus %s` cannot work "
                                "without this file" % name))
            continue
        checks.append(Check("corpus:%s" % name, OK,
                            "%s %s" % (_sha256(entry.source)[:12],
                                       entry.source.name)))
    return checks


def _contracts() -> Check:
    found = sorted(p.name for p in _data_dir().glob("contract-*.jsonc"))
    if not found:
        return Check("contracts", FAIL, "no contract-*.jsonc in %s"
                     % _data_dir(), "reinstall gisel; the contracts are "
                     "package data")
    return Check("contracts", OK, " ".join(found))


def _commands() -> Check:
    try:
        cli = import_module(".cli", __package__)
    except Exception as exc:                     # noqa: BLE001 - report it
        return Check("commands", FAIL, "cli does not import: %s" % exc,
                     "reinstall gisel; this is a broken installation, not a "
                     "usage error")
    commands = getattr(cli, "COMMANDS", ())
    if not commands:
        return Check("commands", FAIL, "COMMANDS is empty",
                     "reinstall gisel; this is a broken installation")
    # The parser is built from COMMANDS and asserts the two agree, so listing
    # it here is enough: a command that cannot dispatch never reaches a user.
    return Check("commands", OK, "%d: %s" % (len(commands),
                                             " ".join(commands)))


def checks() -> list[Check]:
    return ([_python(), _version(), _install(), _opcode_slots(), _contracts(),
             _commands()] + _corpora())


def run(as_json=False, out=sys.stdout) -> int:
    found = checks()
    failed = [c for c in found if c.status != OK]
    if as_json:
        print(json.dumps({"ok": not failed,
                          "checks": [c.as_dict() for c in found]},
                         indent=1, sort_keys=True), file=out)
    else:
        print("gisel doctor", file=out)
        for check in found:
            print("%-16s %-4s %s" % (check.name, check.status, check.detail),
                  file=out)
            if check.fix:
                print("%-16s      fix: %s" % ("", check.fix), file=out)
        print("%d/%d ok" % (len(found) - len(failed), len(found)), file=out)
    return 2 if failed else 0
