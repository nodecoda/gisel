# Pressure test: M68k and WebAssembly

状态: 证据记录（2026-11-06）。语料: `tests/corpus/M68kLegalizerInfo.gisel`（13 条）、
`tests/corpus/WebAssemblyLegalizerInfo.gisel`（108 条）。

## 1 结论

- LLVM 里实现了 GlobalISel legalizer 的 target 共 **7 个**（见 §2）。其中 AArch64 /
  X86 已有 `.td`+`.gisel`（1075 条），其余 5 个没有。
- 取最小的 M68k（52 行）和中等且换了一组 API 的 WebAssembly（234 行）各压一遍：
  - **M68k: 13/13 条可表达，0 缺口。**
  - **WebAssembly: 108/109 条可表达，1 条不可表达**——`G_SEXT_INREG` 的 legal
    规则读 imm 0。这是 core IR 缺 `Imms` 轴，不是拼写问题。
- 两份 `.gisel` 的 `--emit=inc` 片段都用**未修改的** LLVM 头文件编译通过
  （`-fsyntax-only`，反例见 §6），也就是说除了那一条，C++ 侧没有 shim 缺口。

## 2 盘点：实现了 GlobalISel legalizer 的 target

`llvm/lib/Target/*/GISel/*LegalizerInfo.cpp`：

| target | 行数 | 现状 |
|---|---:|---|
| BPF | 20 | 构造函数为空，没有任何规则 |
| M68k | 52 | 本次压测（13 条） |
| PowerPC | 91 | `legalForCartesianProduct`、`bitcastIf`、自定义谓词 lambda（`PPCLegalizerInfo.cpp:22`） |
| WebAssembly | 234 | 本次压测（108 条） |
| X86 | 492 | 已迁移（332 条） |
| RISCV | 1917 | 未迁移；已有 `immInSet`/`immIs`（`RISCVLegalizerInfo.cpp:185-189`） |
| AArch64 | 2902 | 已迁移（743 条 + 3 个 `imm_idx`） |

## 3 M68k

4 条 builder 链（`legalFor`、`clampScalar`、`widenScalarToNextPow2`、
`legalForTypesWithMemDesc`），6 个 ruleset / 13 条规则，0 缺口。
`clampScalar(0, s8, s32)` 的语料写法是 `widen(slot(0), ty(s8))` +
`narrow(slot(0), ty(s32))`（两条 core 规则），shim 落到
`coreMinScalar`/`coreMaxScalar`。

## 4 WebAssembly：29 条 builder 链 → 108 条规则

覆盖的 API：`legalFor`、`legalForCartesianProduct`、`legalForTypesWithMemDesc`、
`widenScalarToNextPow2`、`clampScalar`、`minScalar`、`scalarSameSizeAs`、`lower`、
`lowerIfMemSizeNotByteSizePow2`、`legalIf`（带 imm）。前 9 个可表达，最后一个不行。

转写时有 5 处拼写选择，没有一处是语法糖：

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

`.gisel` 里写 `in(slot(0), [8, 16])` 会被拒：`expected a type, got INT 8`
（`gisel lint` exit 2）。core IR 的 sort 表只有
`Type/Int/Bool/MemDesc/Kind/Ordering/String`，观察子里没有 `Imm`
（`LegalizerCore.td:27-47`），所以**这不是介质税，是语言缺一条轴**。

## 5 缺口表

| C++ | core IR | 结论 | 成本 |
|---|---|---|---|
| `immInSet(i, S)` / `immIs(i, v)` | 无 | **必须加**：加 `Imm(i)` 观察子（SortInt）+ `in` 支持 Int 集合，domain JSON 的 `imms` 已有字段可填 | 中：`LegalizerCore.td` + emitter 的 sort 检查 + 4 个解释器 + eval；受影响 target：WebAssembly、RISCV |
| `LLT::floatIEEE(n)` | 无（只认 `float32()`） | 前端可消除：`normalize_llt` 加一行 | 极低；无测试受影响 |
| `LLT::integer(<任意 C++ 表达式>)` | 只能整数字面量 | 保留：`select` 已覆盖「按特征选类型」；按特征选**整数**（bit 数）目前无人用 | 0（无用到） |
| `lowerIfMemSizeNotByteSizePow2()` | 可合成 | 不需要改；C++ 侧已验证编译（`TypeSize` 有隐式 `operator uint64_t`，`TypeSize.h:384`） | 0 |
| `scalarSameSizeAs` | `same_as(n)` | 不需要改 | 0 |
| 集合字面量只能在 dag 末尾 | 文法里就是「只能是 `in*` 的最后一个实参」 | 保留，但已经变成文法规则而不是 TableGen 报错 | 0 |
| `def not` 撞名 | 面上是前缀运算符 `not(...)`，`.td` 出 `(CoreNot ...)` | 已消除 | 0 |
| `Target.td` include 顺序 | 语料两行 include，`s32`/`v2s64` 由 target 前缀消解（`Wasm_s32`） | 已消除 | 0 |
| `dag` 参数只收 dag（`CoreWidenPow2OrMinSize`） | `widen(slot, pow2_min(n))` 一种拼写 | 已消除（前端出两条规则而不是一个 dag 重载） | 0 |

## 6 验证

```
$ python3 -m gisel lint tests/corpus/M68kLegalizerInfo.gisel
M68kLegalizerInfo.gisel: 0 error(s), 0 warning(s), 13 rule(s)
$ python3 -m gisel lint tests/corpus/WebAssemblyLegalizerInfo.gisel
WebAssemblyLegalizerInfo.gisel: 0 error(s), 0 warning(s), 108 rule(s)
$ python3 -m gisel gen --emit={td,inc,check,table,core} ...   # 五个后端全部 exit 0
$ python3 -m unittest discover -q -s tests
Ran 49 tests ... OK
```

编译门（`inc` 片段 + 未修改的 `LegalizerInfo.h`）：

```
$ g++ -std=c++17 -fsyntax-only -I llvm/include -I build/include wasmtu.cpp
status=0                      # 108 条规则
$ sed 's/\.coreMinScalar(/.coreMinScalarBogus(/' wasm.inc > bad.inc
$ g++ ... badtu.cpp
error: 'class llvm::LegalizeRuleSet' has no member named 'coreMinScalarBogus'
status=2                      # 反例证明片段真的被编译
```

`wasm.core` 的不变量：29 个 ruleset、108 条规则、`escapes: []`、
`domain.types = [f32, f64, i16, i32, i64, i8, p0:64, s32, s64]`、
`domain.imms = []`（就是 §4 那条缺口）。

## 7 对迁移顺序的意义

- 两个新 target 都没有要求新的语法糖：5 处差异全是既有构造子/既有 shim 的新组合。
  说明 1075 条语料推出来的词汇表对「别的 target 怎么写」是够用的。
- 唯一的缺口落在 **imm 轴**，而它恰好是 core IR 从 `.td` 迁过来时被丢掉的一列
  （`(Opcode, Types, MMODescs, Imms)` 里的最后一列）。RISCV 迁移前必须先补。
