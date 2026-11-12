"""Explicit analysis-axis profiles.

An axis profile is a sidecar ``--axes FILE`` consumed by the analysis commands
(``cases``, ``domain``, ``graph``).  It never enters the code-generation model:
``gen``/``check``/``lint``/``eval`` do not read it, and the frozen core JSON is
unchanged.

The profile separates two things:

* **values** (``types``, ``mems``, ``imms``) -- a target-specific finite set;
* **sampling** (``profiles``) -- what each analysis backend does with it.

Absent fields keep the current derivation.  ``mode: "derive"`` edits the
derived set with ``add``/``remove``; ``mode: "explicit"`` replaces it.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import ast as A
from . import eval as E
from . import llt as L


AXIS_NAMES = ("types", "mem", "imm", "ordering")
PROFILE_NAMES = ("cases", "domain", "graph")
MODES = ("derive", "explicit")
ORDERINGS = {"NotAtomic"} | set(E._ORDERING_FROM_TAG.values())

_PROFILE_KEYS = {
    "cases": {"max_slot_values", "boundaries", "max_outside"},
    "domain": {"full", "max_points"},
    "graph": {"state", "skip"},
}


class AxisError(ValueError):
    """A malformed or source-inconsistent axis profile."""


def load(path):
    """Load and schema-check an axis profile (source binding comes later)."""
    return Axes.load(path)


def _type_key(value):
    return repr(value)


def _dedup(values):
    out, seen = [], set()
    for value in values:
        key = _type_key(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _row_key(row):
    return tuple(row)


class Axes:
    def __init__(self, data, path="<memory>"):
        self.data = data
        self.path = path
        self.doc = None
        self._named = {}
        self._selects = set()
        self._doc_types = set()
        self._imm_indices = set()
        self._configs = set()
        self._configs_path = None
        self._profile_dir = Path(path).parent if path != "<memory>" else Path(".")

    # -- loading ---------------------------------------------------------

    @classmethod
    def load(cls, path):
        try:
            text = Path(path).read_text()
        except OSError as exc:
            raise AxisError("%s: %s" % (path, exc.strerror)) from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AxisError("%s: %s" % (path, exc)) from exc
        axes = cls(data, str(path))
        axes._validate_schema()
        return axes

    def bind(self, source, doc, features=None):
        """Validate source-dependent values and remember the document."""
        self.doc = doc
        self._doc_types = {t for t in doc.get("domain", {}).get("types", [])
                           if isinstance(t, str)}
        self._imm_indices = set(doc.get("domain", {}).get("imms", []))
        try:
            program = A.parse_program(Path(source).read_text())
        except (OSError, ValueError) as exc:
            raise AxisError("%s: %s" % (source, exc)) from exc
        self._named = {}
        self._selects = set(program.selects)
        for name, decl in program.named_types.items():
            self._named[name] = A.llt_text(decl.llt)
        if features is not None:
            self._configs = set(features.table)

        # Type values must be concrete LLTs, not config-selected types.
        for text in self._type_texts():
            self.resolve_type(text)
        # Memory rows use the same type spellings.
        for row in self._mem_rows():
            for text in row[:3]:
                if text:
                    self.resolve_type(text)
        # Immediates must be indices the source actually reads.
        for index in self._imm_spec():
            if index not in self._imm_indices:
                raise AxisError(
                    "%s: imms[%d] is not read by any predicate (known: %s)"
                    % (self.path, index,
                       ", ".join(str(i) for i in sorted(self._imm_indices)) or "none"))
        # Config bindings must name a row in the truth table.
        if self._configs:
            for config in self._bind().get("pointer_width", {}):
                if config not in self._configs:
                    raise AxisError(
                        "%s: bind.pointer_width[%r] is not a configuration"
                        % (self.path, config))
            for config in self._bind().get("extended", {}):
                if config not in self._configs:
                    raise AxisError(
                        "%s: bind.extended[%r] is not a configuration"
                        % (self.path, config))
        return self

    # -- schema validation ----------------------------------------------

    def _validate_schema(self):
        data = self.data
        if not isinstance(data, dict):
            raise AxisError("%s: top level must be an object" % self.path)
        unknown = set(data) - {"version", "types", "mems", "imms", "bind",
                               "profiles"}
        if unknown:
            raise AxisError("%s: unknown key(s): %s"
                            % (self.path, ", ".join(sorted(unknown))))
        if data.get("version") != 1:
            raise AxisError("%s: version must be 1" % self.path)

        types = data.get("types", {})
        if not isinstance(types, dict):
            raise AxisError("%s: types must be an object" % self.path)
        self._validate_mode(types, "types")
        if types.get("mode", "derive") == "explicit" and not types.get("values"):
            raise AxisError("%s: types.values is required for explicit mode"
                            % self.path)
        for key in ("values", "add", "remove"):
            self._validate_str_list(types.get(key, []), "types.%s" % key)

        mems = data.get("mems", {})
        if not isinstance(mems, dict):
            raise AxisError("%s: mems must be an object" % self.path)
        self._validate_mode(mems, "mems")
        rows = mems.get("rows", [])
        if not isinstance(rows, list):
            raise AxisError("%s: mems.rows must be a list" % self.path)
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 4:
                raise AxisError("%s: mems.rows entries must be "
                                "[t0, t1, mty, align]" % self.path)
            if not isinstance(row[0], str) or not isinstance(row[1], str) \
                    or not isinstance(row[2], str) or not isinstance(row[3], int):
                raise AxisError("%s: mems.rows entry has a bad type" % self.path)
        self._validate_str_list(mems.get("remove", []), "mems.remove",
                                allow_rows=True)
        for key in ("orderings", "failure_orderings"):
            self._validate_str_list(mems.get(key, []), "mems.%s" % key)
            for tag in mems.get(key, []):
                if tag not in ORDERINGS:
                    raise AxisError("%s: mems.%s has unknown ordering %r"
                                    % (self.path, key, tag))

        imms = data.get("imms", {})
        if not isinstance(imms, dict):
            raise AxisError("%s: imms must be an object" % self.path)
        for key, values in imms.items():
            if not str(key).isdigit():
                raise AxisError("%s: imms keys must be integer indices"
                                % self.path)
            if not isinstance(values, list) or not all(
                    isinstance(v, int) for v in values):
                raise AxisError("%s: imms[%s] must be a list of integers"
                                % (self.path, key))

        bind = data.get("bind", {})
        if not isinstance(bind, dict):
            raise AxisError("%s: bind must be an object" % self.path)
        unknown = set(bind) - {"configs", "pointer_width", "extended"}
        if unknown:
            raise AxisError("%s: unknown bind key(s): %s"
                            % (self.path, ", ".join(sorted(unknown))))
        configs = bind.get("configs")
        if configs is not None and not isinstance(configs, str):
            raise AxisError("%s: bind.configs must be a string" % self.path)
        if configs:
            path = Path(configs)
            if not path.is_absolute():
                path = self._profile_dir / path
            self._configs_path = str(path)
        widths = bind.get("pointer_width", {})
        if not isinstance(widths, dict) or not all(
                isinstance(k, str) and isinstance(v, int) and v > 0
                for k, v in widths.items()):
            raise AxisError("%s: bind.pointer_width must map config -> int"
                            % self.path)
        extended = bind.get("extended", {})
        if not isinstance(extended, dict) or not all(
                isinstance(k, str) and isinstance(v, bool)
                for k, v in extended.items()):
            raise AxisError("%s: bind.extended must map config -> bool"
                            % self.path)

        profiles = data.get("profiles", {})
        if not isinstance(profiles, dict):
            raise AxisError("%s: profiles must be an object" % self.path)
        unknown = set(profiles) - set(PROFILE_NAMES)
        if unknown:
            raise AxisError("%s: unknown profile(s): %s"
                            % (self.path, ", ".join(sorted(unknown))))
        for name, profile in profiles.items():
            if not isinstance(profile, dict):
                raise AxisError("%s: profiles.%s must be an object"
                                % (self.path, name))
            unknown = set(profile) - _PROFILE_KEYS[name]
            if unknown:
                raise AxisError("%s: profiles.%s has unknown key(s): %s"
                                % (self.path, name, ", ".join(sorted(unknown))))
        state = profiles.get("graph", {}).get("state")
        if state is not None:
            if not isinstance(state, list) or not all(
                    isinstance(v, str) for v in state):
                raise AxisError("%s: profiles.graph.state must be a list"
                                % self.path)
            bad = set(state) - set(AXIS_NAMES)
            if bad:
                raise AxisError("%s: profiles.graph.state has unknown axis %r"
                                % (self.path, sorted(bad)[0]))

    def _validate_mode(self, section, name):
        mode = section.get("mode", "derive")
        if mode not in MODES:
            raise AxisError("%s: %s.mode must be derive or explicit"
                            % (self.path, name))

    def _validate_str_list(self, values, name, allow_rows=False):
        if not isinstance(values, list):
            raise AxisError("%s: %s must be a list" % (self.path, name))
        for value in values:
            if allow_rows:
                if not isinstance(value, (list, tuple)) or len(value) != 4:
                    raise AxisError("%s: %s entries must be mem_desc rows"
                                    % (self.path, name))
            elif not isinstance(value, str):
                raise AxisError("%s: %s entries must be strings"
                                % (self.path, name))

    # -- accessors -------------------------------------------------------

    def _types(self):
        return self.data.get("types", {})

    def _mems(self):
        return self.data.get("mems", {})

    def _imms(self):
        return self.data.get("imms", {})

    def _bind(self):
        return self.data.get("bind", {})

    def _type_texts(self):
        types = self._types()
        return (list(types.get("values", [])) + list(types.get("add", []))
                + list(types.get("remove", [])))

    def _mem_rows(self):
        mems = self._mems()
        return ([tuple(row) for row in mems.get("rows", [])]
                + [tuple(row) for row in mems.get("remove", [])])

    def _imm_spec(self):
        return {int(key): list(values) for key, values in self._imms().items()}

    @property
    def configs_path(self):
        return self._configs_path

    def resolve_type(self, text):
        if text in self._doc_types:
            try:
                return E.parse_case_llt(text)
            except E.EvalError as exc:
                raise AxisError("%s: type %r: %s" % (self.path, text, exc)) from exc
        if text in self._named:
            try:
                return E.parse_case_llt(self._named[text])
            except E.EvalError as exc:
                raise AxisError("%s: type %r: %s"
                                % (self.path, text, exc)) from exc
        if text in self._selects:
            raise AxisError(
                "%s: type %r is configuration-selected; list a concrete "
                "LLT in the axis instead" % (self.path, text))
        try:
            return E.parse_case_llt(text)
        except E.EvalError as exc:
            raise AxisError("%s: type %r: %s" % (self.path, text, exc)) from exc

    def types_explicit(self):
        return self._types().get("mode", "derive") == "explicit"

    def mems_explicit(self):
        return self._mems().get("mode", "derive") == "explicit"

    def profile(self, name):
        return dict(self.data.get("profiles", {}).get(name, {}))

    def pointer_width(self, config, default=64):
        return int(self._bind().get("pointer_width", {}).get(config, default))

    def extended(self, config, default=None):
        return self._bind().get("extended", {}).get(config, default)

    def imms(self):
        return self._imm_spec()

    def orderings(self):
        return list(self._mems().get("orderings", []))

    def failure_orderings(self):
        return list(self._mems().get("failure_orderings", []))

    def has_orderings(self):
        return bool(self.orderings())

    def ordering_pairs(self):
        """``(ordering, failure_ordering)`` points to sample.

        Declaring ``mems.orderings`` turns the axis on; the failure ordering
        defaults to ``NotAtomic`` (the value non-atomic loads/stores carry).
        """
        orderings = self.orderings()
        if not orderings:
            return [("NotAtomic", "NotAtomic")]
        failures = self.failure_orderings() or ["NotAtomic"]
        return [(o, f) for o in orderings for f in failures]

    def apply_features(self, features):
        """Apply ``bind.extended`` over the derived feature truth table."""
        for config, value in (self._bind().get("extended") or {}).items():
            row = features.table.get(config)
            if row is not None:
                row["LLT::getUseExtended()"] = bool(value)
        return features

    # -- application -----------------------------------------------------

    def apply_imms(self, index, values):
        """Profile values replace the derived ones for one imm index."""
        spec = self._imm_spec()
        return list(spec[index]) if index in spec else list(values)

    def apply_types(self, values, pointer_only=False):
        types = self._types()
        mode = types.get("mode", "derive")
        if mode == "explicit":
            out = [self.resolve_type(v) for v in types.get("values", [])]
        else:
            out = list(values)
            out += [self.resolve_type(v) for v in types.get("add", [])]
        remove = {_type_key(self.resolve_type(v))
                  for v in types.get("remove", [])}
        out = [v for v in out if _type_key(v) not in remove]
        if pointer_only:
            out = [v for v in out if v[0] == "pointer"]
        return _dedup(out)

    def _canon_row(self, row):
        t0, t1, mty, align = row
        return (L.spell(self.resolve_type(t0)) if t0 else "",
                L.spell(self.resolve_type(t1)) if t1 else "",
                L.spell(self.resolve_type(mty)) if mty else "",
                int(align))

    def apply_mems(self, rows):
        mems = self._mems()
        mode = mems.get("mode", "derive")
        if mode == "explicit":
            out = [self._canon_row(tuple(row))
                   for row in mems.get("rows", [])]
        else:
            out = [tuple(row) for row in rows]
            out += [self._canon_row(tuple(row))
                    for row in mems.get("rows", [])]
        remove = {_row_key(self._canon_row(tuple(row)))
                  for row in mems.get("remove", [])}
        out = [row for row in out if _row_key(row) not in remove]
        dedup, seen = [], set()
        for row in out:
            key = _row_key(row)
            if key in seen:
                continue
            seen.add(key)
            dedup.append(row)
        return dedup
