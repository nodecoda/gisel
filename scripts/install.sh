#!/bin/sh
# Install the three gisel tools on a machine with no checkout.
#
#   curl -fsSL https://raw.githubusercontent.com/nodecoda/gisel/main/scripts/install.sh | sh
#
# It tries, in order: pipx, uv tool, a plain venv.  `--prefix DIR` forces the
# venv (that is what CI and `--dry-run` use), so the same script is testable
# without touching $HOME.  Packages come from PyPI; `--from-git` installs the
# commits named by gisel-ab/RELEASE.json instead, which is how a cohort is
# checked before its wheels are uploaded.
#
# The script is POSIX sh on purpose: it is piped into `sh` by the README and
# by install.yml, so bash-only syntax would fail exactly where it matters.
set -eu

GISEL_GIT_BASE=${GISEL_GIT_BASE:-https://github.com/nodecoda}
RELEASE_URL=${GISEL_RELEASE_URL:-https://raw.githubusercontent.com/nodecoda/gisel-ab/main/RELEASE.json}

PREFIX=
DRY_RUN=0
FROM_GIT=0
PYTHON=${PYTHON:-python3}
REV_GISEL=
REV_ANCHOR=
REV_AB=

usage() {
    cat <<'EOF'
usage: install.sh [options]

  --prefix DIR     install into DIR/venv and DIR/bin (implies the venv path)
  --from-git       install the commits pinned in gisel-ab/RELEASE.json
  --rev-gisel REV  override the gisel revision (implies --from-git)
  --rev-anchor REV override the gisel-anchor revision
  --rev-ab REV     override the gisel-ab revision
  --python PATH    interpreter used to create the venv (default: python3)
  --dry-run        print the commands instead of running them
  -h, --help       this text
EOF
}

say() { printf '%s\n' "$*" >&2; }
die() { say "install.sh: $*"; exit 2; }

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix) [ $# -ge 2 ] || die "--prefix needs a value"; PREFIX=$2; shift 2 ;;
        --prefix=*) PREFIX=${1#*=}; shift ;;
        --from-git) FROM_GIT=1; shift ;;
        --rev-gisel) [ $# -ge 2 ] || die "--rev-gisel needs a value"; REV_GISEL=$2; FROM_GIT=1; shift 2 ;;
        --rev-anchor) [ $# -ge 2 ] || die "--rev-anchor needs a value"; REV_ANCHOR=$2; FROM_GIT=1; shift 2 ;;
        --rev-ab) [ $# -ge 2 ] || die "--rev-ab needs a value"; REV_AB=$2; FROM_GIT=1; shift 2 ;;
        --python) [ $# -ge 2 ] || die "--python needs a value"; PYTHON=$2; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
done

run() {
    if [ "$DRY_RUN" = 1 ]; then
        printf '+ %s\n' "$*"
        return 0
    fi
    "$@"
}

# Python 3.10 is the floor `pyproject.toml` declares; failing here beats a
# SyntaxError inside a tool three steps later.
if [ "$DRY_RUN" = 0 ]; then
    command -v "$PYTHON" >/dev/null 2>&1 || die "$PYTHON not found; install Python 3.10+ or pass --python PATH"
    "$PYTHON" - <<'PY' || die "Python 3.10+ is required (pass --python PATH)"
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY
fi

pins_from_manifest() {
    # The manifest is one JSON object; `repos` names the commit of each repo.
    # Printing three sh assignments keeps the caller free of jq.
    "$PYTHON" - "$RELEASE_URL" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=30) as response:
        doc = json.load(response)
except Exception as exc:                      # noqa: BLE001 - report it
    print("install.sh: cannot read %s: %s" % (url, exc), file=sys.stderr)
    print("install.sh: pass --rev-gisel/--rev-anchor/--rev-ab instead",
          file=sys.stderr)
    sys.exit(2)
repos = doc.get("repos") or {}
missing = [name for name in ("gisel", "ab", "upstream_source")
           if not repos.get(name)]
if missing:
    print("install.sh: %s has no pin for %s" % (url, ", ".join(missing)),
          file=sys.stderr)
    sys.exit(2)
# `${VAR:-...}` keeps a --rev-* the caller passed on the command line.
print('REV_GISEL=${REV_GISEL:-%s}' % repos["gisel"])
print('REV_ANCHOR=${REV_ANCHOR:-%s}' % repos["upstream_source"])
print('REV_AB=${REV_AB:-%s}' % repos["ab"])
PY
}

if [ "$FROM_GIT" = 1 ]; then
    if [ -z "$REV_GISEL" ] || [ -z "$REV_ANCHOR" ] || [ -z "$REV_AB" ]; then
        if [ "$DRY_RUN" = 1 ]; then
            REV_GISEL=${REV_GISEL:-<RELEASE.json:repos.gisel>}
            REV_ANCHOR=${REV_ANCHOR:-<RELEASE.json:repos.upstream_source>}
            REV_AB=${REV_AB:-<RELEASE.json:repos.ab>}
        else
            pins=$(pins_from_manifest) || exit 2
            eval "$pins"
        fi
        if [ -z "$REV_GISEL" ] || [ -z "$REV_ANCHOR" ] || [ -z "$REV_AB" ]; then
            die "could not read the pins from $RELEASE_URL; pass --rev-* explicitly"
        fi
    fi
    SPEC_GISEL="git+$GISEL_GIT_BASE/gisel@$REV_GISEL"
    SPEC_ANCHOR="git+$GISEL_GIT_BASE/gisel-anchor@$REV_ANCHOR"
    SPEC_AB="git+$GISEL_GIT_BASE/gisel-ab@$REV_AB"
    say "install.sh: from git: gisel $REV_GISEL, anchor $REV_ANCHOR, ab $REV_AB"
else
    SPEC_GISEL=gisel
    SPEC_ANCHOR=gisel-anchor
    SPEC_AB=gisel-ab
    say "install.sh: from PyPI"
fi

# Pick the installer.  `--prefix` pins the venv: pipx and uv own $HOME, and a
# test (or CI) must be able to install somewhere disposable.
if [ -n "$PREFIX" ]; then
    MODE=venv
elif command -v pipx >/dev/null 2>&1; then
    MODE=pipx
elif command -v uv >/dev/null 2>&1; then
    MODE=uv
else
    MODE=venv
    PREFIX=${XDG_DATA_HOME:-$HOME/.local}/gisel
fi

say "install.sh: $MODE"

case "$MODE" in
pipx)
    BIN=$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || true)
    [ -n "$BIN" ] || BIN=$HOME/.local/bin
    # One venv, three tools: ab imports gisel, so injecting keeps a single
    # copy of gisel on the machine instead of three that can disagree.
    run pipx install --force "$SPEC_GISEL"
    run pipx inject gisel "$SPEC_ANCHOR" "$SPEC_AB"
    GISEL=$BIN/gisel
    ANCHOR=$BIN/gisel-anchor
    AB=$BIN/gisel-ab
    ;;
uv)
    BIN=$(uv tool dir --bin 2>/dev/null || true)
    [ -n "$BIN" ] || BIN=$HOME/.local/bin
    # `uv tool install --with` exposes only the named tool's entry points, so
    # each package gets its own tool env; ab's env carries gisel.
    run uv tool install --force "$SPEC_GISEL"
    run uv tool install --force --with gisel "$SPEC_ANCHOR"
    run uv tool install --force --with gisel "$SPEC_AB"
    GISEL=$BIN/gisel
    ANCHOR=$BIN/gisel-anchor
    AB=$BIN/gisel-ab
    ;;
venv)
    VENV=$PREFIX/venv
    BIN=$PREFIX/bin
    if [ ! -x "$VENV/bin/python" ]; then
        run mkdir -p "$PREFIX"
        run "$PYTHON" -m venv "$VENV"
    fi
    run "$VENV/bin/python" -m pip install --quiet --upgrade pip
    run "$VENV/bin/python" -m pip install --quiet "$SPEC_GISEL" "$SPEC_ANCHOR" "$SPEC_AB"
    if [ "$DRY_RUN" = 0 ]; then
        mkdir -p "$BIN"
        for tool in gisel gisel-anchor gisel-ab; do
            ln -sf "../venv/bin/$tool" "$BIN/$tool"
        done
    fi
    GISEL=$BIN/gisel
    ANCHOR=$BIN/gisel-anchor
    AB=$BIN/gisel-ab
    ;;
esac

# Verification: the three versions, then `doctor`, which is the tool's own
# answer to "is this install able to work?".
run "$GISEL" --version
run "$ANCHOR" --version
run "$AB" --version
run "$GISEL" doctor

if [ "$DRY_RUN" = 1 ]; then
    say "install.sh: dry run, nothing was installed"
    exit 0
fi

if ! command -v gisel >/dev/null 2>&1; then
    say "install.sh: $BIN is not on PATH; add this to your shell profile:"
    say "  export PATH=\"$BIN:\$PATH\""
fi

cat >&2 <<EOF
install.sh: ok
next:
  $GISEL demo
  $GISEL cases --corpus x86 --out x86.cases.jsonl
  $AB --version && $AB suite check --target m68k
EOF
