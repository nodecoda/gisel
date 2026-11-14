# Pressure test: M68k and WebAssembly

> 这是工作台报告：`gisel-anchor/scripts/import-cxx.py` 是工作台工具，不是 gisel 的功能；边界见 `docs/SCOPE.md`。

状态: 证据记录（2026-11-06，2026-11-09 追补）。语料:
`tests/corpus/M68kLegalizerInfo.gisel`（13 条）、
`tests/corpus/WebAssemblyLegalizerInfo.gisel`（109 条，已由 `import-cxx` 转录；
本报告 §4 保留当初人工转写时的拼写记录）。

## 1 结论

- LLVM 里实现了 GlobalISel legalizer 的 target 共 **7 个**（见 §2）。其中 X86 /
  AArch64 已有 `.gisel` 语料（1075 条），其余 5 个当时没有。
- 取最小的 M68k（52 行）和中等且换了一组 API 的 WebAssembly（234 行）各压一遍：
  - **M68k: 13/13 条可表达，0 缺口。**
  - **WebAssembly: 109/109 条可表达，且已转正。** 第一轮压出 1 条缺口
    （`G_SEXT_INREG` 的 legal 规则读 imm 0），当天补上 imm 轴（`imm(i)` 观察子 +
    同质集合）。2026-11-09 起语料改由 `tools/import-cxx.py` 从 C++ 转录，
    29 rulesets / 109 rules / **0 refused**，并跑通端到端
    **942/942 agree**（见 §8）。
- 两份 `.gisel` 的 `--emit=inc` 片段都用**未修改的** LLVM 头文件编译通过
  （`-fsyntax-only`，反例见 §6），也就是说除了那一条，C++ 侧没有 shim 缺口。

## 2 盘点：实现了 GlobalISel legalizer 的 target

盘点 `llvm/lib/Target/*/GISel/*LegalizerInfo.cpp`；全量清单以
`docs/CORPORA.md` 为准（11 个构造函数，9 个已收）。

| target | 行数 | 语料 |
|---|---:|---|
| BPF | 20 | 构造函数为空，没有规则 |
| M68k | 52 | `M68kLegalizerInfo.gisel`（13 条） |
| PowerPC | 91 | `PowerPCLegalizerInfo.gisel`；`legalForCartesianProduct`、`bitcastIf`、自定义谓词 lambda（`PPCLegalizerInfo.cpp:22`） |
| WebAssembly | 234 | `WebAssemblyLegalizerInfo.gisel`（109 条） |
| X86 | 492 | `X86LegalizerInfo.gisel`（328 条） |
| RISCV | 1917 | `RISCVLegalizerInfo.gisel`（402 条；`immInSet`/`immIs`，`RISCVLegalizerInfo.cpp:185-189`） |
| AArch64 | 2902 | `AArch64LegalizerInfo.gisel`（741 条 + 3 个 `imm_idx`） |

## 3 M68k

4 条 builder 链（`legalFor`、`clampScalar`、`widenScalarToNextPow2`、
`legalForTypesWithMemDesc`），6 个 ruleset / 13 条规则，0 缺口。
`clampScalar(0, s8, s32)` 的语料写法是 `widen(slot(0), ty(s8))` +
`narrow(slot(0), ty(s32))`（两条 core 规则），shim 落到
`coreMinScalar`/`coreMaxScalar`。

## 4 WebAssembly：29 条 builder 链 → 109 条规则（人工转写期的记录）

覆盖的 API：`legalFor`、`legalForCartesianProduct`、`legalForTypesWithMemDesc`、
`widenScalarToNextPow2`、`clampScalar`、`minScalar`、`scalarSameSizeAs`、`lower`、
`lowerIfMemSizeNotByteSizePow2`、`legalIf`（带 imm）。前 9 个可表达，最后一个不行。

转写时有 5 处拼写选择，没有一处是语法糖。这些现在都由转录器自动完成
（`LLT::floatIEEE` 归一、通用三元宽度、`_declare_pair` 复用同名 LLT）；下表是
当初手工对齐时留下的依据：

| C++ | `.gisel` | 依据 |
|---|---|---|
| `LLT::floatIEEE(32/64)` | `LLT::float32()/float64()` | 同一个 LLT；前端只规范化命名捷径（`td.py:193-196`） |
| `LLT::integer(ST.hasAddr64() ? 64 : 32)` | `select Wasm_p0i = if Wasm_HasAddr64 then Wasm_i64 else Wasm_i32` | 特征相关的**类型**有 `select`；特征相关的**整数**没有拼写（本次没用到） |
| `scalarSameSizeAs(1, 0)` | `widen(slot(1), same_as(0))` + `narrow(...)` | 已有 shim `coreMinScalarSameAs`/`coreMaxScalarSameAs`，X86 语料先例 |
| `clampScalar(i, lo, hi)` | `widen(i, ty(lo))` + `narrow(i, ty(hi))` | 与 `minScalar`+`maxScalar` 同义；X86/M68k 先例 |
| `lowerIfMemSizeNotByteSizePow2()` | `lower (not(is_byte_sized(mem_ty(...))) or not(is_pow2(size_in_bytes_of(...))))` | 谓词是合成的，C++ 落成 inline lambda |

`G_SEXT_INREG` 的 legal 规则（`WebAssemblyLegalizerInfo.cpp:103-108`）读 imm 0：

```cpp
Builder.legalIf(all(typeInSet(0, {i32, i64}),
                    any(immInSet(0, {8, 16}),
                        all(typeIs(0, i64), immIs(0, 32)))));
```

第一轮压测时这条写不出来：`in(slot(0), [8, 16])` 报 `expected a type, got INT 8`。
core IR 的 sort 表只有 `Type/Int/Bool/MemDesc/Kind/Ordering/String`，观察子里没有
`Imm`，所以**这不是介质税，是语言缺一条轴**。

现在写作：

```
legal (feature("Subtarget.hasSignExt()") and in(slot(0), [Wasm_i32, Wasm_i64])
       and (in(imm(0), [8, 16]) or (in(slot(0), Wasm_i64) and imm(0) == 32)))
```

落成 `.inc`：

```cpp
.coreLegalIf([=](const LegalityQuery &Query) {
  return (Wasm_HasSignExt) && ((Query.Types[0] == Wasm_i32 || ...))
      && ((LegalityPredicates::immInSet(0, {8, 16})(Query))
          || ((Query.Types[0] == Wasm_i64) && (Query.Immediates[0] == 32)));
})
```

`imm(i)` 读 `Query.Immediates[i]`（`LegalizerInfo.h:126`）；`in(imm(i), [...])`
是 `immInSet`，`imm(i) == v` 是 `immIs` 的表达式写法。集合是同质的：`Int` 集合
只能配 `imm`，`Type` 集合只能配 `slot`，混写在 lint 就是一条 error。

## 5 缺口表

| C++ | core IR | 结论 | 成本 |
|---|---|---|---|
| `immInSet(i, S)` / `immIs(i, v)` | `imm(i)` + Int 集合 | **已补**（D-20261107-80）：`imm(i)` 观察子（SortInt）+ `in` 接受 Int 集合，`domain.imms` 填下标；5 个后端 + eval 全覆盖 | 已完成 |
| `LLT::floatIEEE(n)` | 无（只认 `float32()`） | **已消除**：转录器 `_llt_float_ieee()` 归一到 `float32()/float64()/float128()` | 0 |
| `LLT::integer(<任意 C++ 表达式>)` | 只能整数字面量 | 保留：`select` 已覆盖「按特征选类型」；按特征选**整数**（bit 数）目前无人用 | 0（无用到） |
| `lowerIfMemSizeNotByteSizePow2()` | 可合成 | 不需要改；C++ 侧已验证编译（`TypeSize` 有隐式 `operator uint64_t`，`TypeSize.h:384`） | 0 |
| `scalarSameSizeAs` | `same_as(n)` | 不需要改 | 0 |
| 集合字面量只能在 dag 末尾 | 文法里就是「只能是 `in*` 的最后一个实参」 | 保留，但已经是文法规则而不是后端报错 | 0 |
| `def not` 撞名 | 面上是前缀运算符 `not(...)`，与保留字不冲突 | 已消除 | 0 |
| target 前缀消解 | 语料里的 `s32`/`v2s64` 由 target 前缀区分（`Wasm_s32`） | 已消除 | 0 |
| `dag` 参数只收 dag（`CoreWidenPow2OrMinSize`） | `widen(slot, pow2_min(n))` 一种拼写 | 已消除（前端出两条规则而不是一个 dag 重载） | 0 |

## 6 验证

以下是当时的快照：`td` / `table` 两个出口已经移除，`--emit` 现在只有
`inc` / `check` / `core`（见 `docs/KNOWN-LIMITATIONS.md`）。命令保留原样，
`--emit` 的值按历史记录读，不要照抄。

<!-- audit: historical -->
```
$ python3 -m gisel lint tests/corpus/M68kLegalizerInfo.gisel
M68kLegalizerInfo.gisel: 0 error(s), 0 warning(s), 13 rule(s)
$ python3 -m gisel lint tests/corpus/WebAssemblyLegalizerInfo.gisel
WebAssemblyLegalizerInfo.gisel: 0 error(s), 0 warning(s), 109 rule(s)
$ python3 -m gisel gen --emit={td,inc,check,table,core} ...   # 五个后端全部 exit 0
$ python3 -m unittest discover -q -s tests
Ran 52 tests ... OK
```

编译门（`inc` 片段 + 未修改的 `LegalizerInfo.h`）：

```
$ g++ -std=c++17 -fsyntax-only -I llvm/include -I build/include wasmtu.cpp
status=0                      # 109 条规则
$ sed 's/\.coreMinScalar(/.coreMinScalarBogus(/' wasm.inc > bad.inc
$ g++ ... badtu.cpp
error: 'class llvm::LegalizeRuleSet' has no member named 'coreMinScalarBogus'
status=2                      # 反例证明片段真的被编译
```

`wasm.core` 的不变量：29 个 ruleset、109 条规则、`escapes: []`、
`domain.types = [f32, f64, i16, i32, i64, i8, p0:64, s32, s64]`、
`domain.imms = [0]`（唯一读立即数的那条规则）。

`gisel eval` 对 imm 的端到端检查（`tests/test_artifacts.py` 里同样有）：
```json
{"config":"signext","name":"G_SEXT_INREG","types":["i32"],"imms":[8], ...}
```
5 个点：i32/8 合法、i32/16 合法、i32/32 落到 lower、i64/32 合法、i64/8 合法，
`cases=5 disagreements=0 errors=0`。

## 7 对导入顺序的意义

- 两个新 target 都没有要求新的语法糖：5 处差异全是既有构造子/既有 shim 的新组合。
  说明 1075 条语料推出来的词汇表对「别的 target 怎么写」是够用的。
- 唯一的缺口落在 **imm 轴**，也就是 core IR 的 `(Opcode, Types, MMODescs, Imms)`
  里此前没有建模的一列。**已补**（D-20261107-80），
  RISCV 导入的前置条件不再缺这一块。

## 8 端到端证据（2026-11-09）

```
$ python3 ../gisel-anchor/scripts/import-cxx.py WebAssembly \
    --pin ../gisel-anchor/pin/PIN.json \
    --git-repo /home/ubuntu/llvm/llvm-project \
    --out tests/corpus/WebAssemblyLegalizerInfo.gisel
tests/corpus/WebAssemblyLegalizerInfo.gisel: 29 rulesets, 109 rules, 0 refused

$ gisel-ab/run-wasm-end-to-end.sh TREE BUILD wasm.inc /tmp/wasm-e2e
/tmp/wasm-e2e/runner.official: 942 queries, 0 unanswerable
/tmp/wasm-e2e/runner.ours: 942 queries, 0 unanswerable
{"agree": 942, "disagree": 0, "unanswerable": 0, ...}
```

配置轴（两个都是构造函数真读的）：

| config | triple | CPU | `hasAddr64` | `hasSignExt` |
|---|---|---|---|---|
| `wasm32` | `wasm32-unknown-unknown` | `mvp` | false | false |
| `wasm32-signext` | `wasm32-unknown-unknown` | `generic` | false | true |
| `wasm64` | `wasm64-unknown-unknown` | `mvp` | true | false |
| `wasm64-signext` | `wasm64-unknown-unknown` | `generic` | true | true |

`generic` 是默认 CPU，特征表里含 `sign-ext`；要关掉得显式用 `mvp`（空基线），
否则“无 sign-ext”这个配置根本不存在。
