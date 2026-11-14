"""The action vocabulary, in one place.

Every consumer that used to spell actions out separately reads this table:
the `.gisel` compiler (`op` -> canonical action), the evaluator and graph
(which actions are terminal), and the C++ emitter (`xxxFor` spelling and the
`markAllIdxsAsCovered` shims).  Adding an action is one edit here plus the
shim it needs; it is not five parallel edits.

Mutation actions carry the target sorts the checker accepts.  Terminal
actions carry no target: their statement has only a guard.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    name: str                 # canonical C++ action, e.g. "Legal"
    op: str                   # `.gisel` statement op, e.g. "legal"
    terminal: bool
    target_sorts: frozenset = frozenset()
    for_spelling: str | None = None     # declarative `xxxFor` form
    covering_shim: str | None = None    # builder that marks every index covered


ACTIONS = (
    Action("Legal", "legal", True,
           for_spelling="legalFor", covering_shim="legalIf"),
    Action("Lower", "lower", True,
           for_spelling="lowerFor", covering_shim="lowerIf"),
    Action("Libcall", "libcall", True,
           for_spelling="libcallFor", covering_shim="libcallIf"),
    Action("Custom", "custom", True,
           for_spelling="customFor", covering_shim="customIf"),
    Action("Unsupported", "unsupported", True,
           for_spelling="unsupportedFor", covering_shim="unsupportedIf"),
    Action("WidenScalar", "widen", False,
           target_sorts=frozenset({"Type", "Int"})),
    Action("NarrowScalar", "narrow", False,
           target_sorts=frozenset({"Type", "Int"})),
    Action("MoreElements", "more", False,
           target_sorts=frozenset({"Int", "Type"})),
    Action("FewerElements", "fewer", False,
           target_sorts=frozenset({"Int", "Type"})),
    Action("Bitcast", "bitcast", False,
           target_sorts=frozenset({"Type"})),
)

BY_NAME = {action.name: action for action in ACTIONS}
BY_OP = {action.op: action for action in ACTIONS}
TERMINAL_ACTIONS = frozenset(a.name for a in ACTIONS if a.terminal)
MUTATION_OPS = frozenset(a.op for a in ACTIONS if not a.terminal)
TERMINAL_OPS = frozenset(a.op for a in ACTIONS if a.terminal)
