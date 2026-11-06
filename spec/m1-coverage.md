# M1 gate G1: shim coverage of the corpus

Every `(operator, observation form, target form)` the two corpora spell,
checked against `CoreShimTable` (`LegalizerInfoEmitter.cpp:2747`).
A triple with no row is a hard error in the C++ emitter, not a fallback.

| operator | on | to | rows | X86 | AArch64 | C++ method |
|---|---|---|---|---|---|---|
| `bitcast` | `slot` | `replace` | 4 | 0 | 4 | `coreBitcastToType` |
| `custom` | `-` | `-` | 35 | 8 | 27 | `coreCustomIf` |
| `fewer` | `slot` | `replace` | 174 | 20 | 154 | `coreFewerTo` |
| `legal` | `-` | `-` | 247 | 134 | 113 | `coreLegalIf` |
| `libcall` | `-` | `-` | 24 | 6 | 18 | `coreLibcallIf` |
| `lower` | `-` | `-` | 67 | 10 | 57 | `coreLowerIf` |
| `more` | `slot` | `pow2` | 30 | 1 | 29 | `coreMoreElementsToNextPow2` |
| `more` | `slot` | `replace` | 107 | 15 | 92 | `coreMoreTo` |
| `narrow` | `elem` | `ty` | 2 | 1 | 1 | `coreMaxScalarOrElt` |
| `narrow` | `slot` | `replace` | 5 | 0 | 5 | `coreNarrowTo` |
| `narrow` | `slot` | `sameAs` | 6 | 4 | 2 | `coreMaxScalarSameAs` |
| `narrow` | `slot` | `ty` | 81 | 37 | 44 | `coreMaxScalar` |
| `scalarize` | `slot` | `-` | 54 | 11 | 43 | `coreScalarizeIf` |
| `unsupported` | `-` | `-` | 13 | 2 | 11 | `coreUnsupportedIf` |
| `widen` | `elem` | `minVectorSize` | 4 | 0 | 4 | `coreWidenVectorEltsToVectorMinSize` |
| `widen` | `elem` | `pow2` | 8 | 0 | 8 | `coreWidenScalarOrEltToNextPow2` |
| `widen` | `elem` | `pow2Min` | 2 | 1 | 1 | `coreWidenScalarOrEltToNextPow2` |
| `widen` | `elem` | `ty` | 20 | 1 | 19 | `coreMinScalarOrElt` |
| `widen` | `slot` | `int` | 5 | 0 | 5 | `coreWidenScalarOrEltToNextPow2OrMinSize` |
| `widen` | `slot` | `pow2` | 26 | 9 | 17 | `coreWidenScalarToNextPow2` |
| `widen` | `slot` | `pow2Min` | 38 | 26 | 12 | `coreWidenScalarToNextPow2` |
| `widen` | `slot` | `replace` | 12 | 0 | 12 | `coreWidenTo` |
| `widen` | `slot` | `sameAs` | 19 | 4 | 15 | `coreMinScalarSameAs` |
| `widen` | `slot` | `select` | 1 | 0 | 1 | `coreWidenScalarOrEltToNextPow2OrMinSize` |
| `widen` | `slot` | `ty` | 91 | 42 | 49 | `coreMinScalar` |

Totals: 25 distinct triples, 1075 rules, 0 uncovered.

Table rows with no corpus use (kept for future rules): `bitcast/slot/ty`, `fewer/slot/ty`, `widen/elem/multipleOf`, `widen/elem/sameAs`, `widen/slot/multipleOf`.
