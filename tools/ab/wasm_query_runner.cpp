//===- wasm_query_runner.cpp - answer JSONL queries with WebAssembly's rules -*-===//
//
// Built twice: `official` links the target library's constructor, `ours` also
// links a replacement constructor object that includes the generated `.inc`.
// The two binaries differ only in which definition of the constructor the
// linker picks, so an answer difference is a rule difference.
//
// The two configuration axes are the ones the constructor itself reads:
// `ST.hasAddr64()` (wasm32 vs wasm64) and `ST.hasSignExt()` (`+sign-ext`),
// which together decide both type selects and G_SEXT_INREG's legal rule.
//===----------------------------------------------------------------------===//

#include "GISel/WebAssemblyLegalizerInfo.h"
#include "WebAssemblySubtarget.h"
#include "WebAssemblyTargetMachine.h"
#include "llvm/Support/TargetSelect.h"

using namespace llvm;

using TargetSubtarget = WebAssemblySubtarget;
using TargetLegalizer = WebAssemblyLegalizerInfo;

#include "query_runner_common.h"

namespace {

static void initializeTarget() {
  LLVMInitializeWebAssemblyTargetInfo();
  LLVMInitializeWebAssemblyTarget();
  LLVMInitializeWebAssemblyTargetMC();
}

static ArrayRef<Config> configs() {
  // `generic` (the default CPU) enables sign-ext; `mvp` is the empty baseline,
  // so the CPU is what turns the feature off.  Passing `-sign-ext` with an
  // empty CPU would say the same thing with a spelling upstream MIR does not
  // use.
  static const Config Table[] = {
      {"wasm32", "wasm32-unknown-unknown", "mvp", "", std::nullopt},
      {"wasm32-signext", "wasm32-unknown-unknown", "generic", "", std::nullopt},
      {"wasm64", "wasm64-unknown-unknown", "mvp", "", std::nullopt},
      {"wasm64-signext", "wasm64-unknown-unknown", "generic", "", std::nullopt},
  };
  return Table;
}

static std::unique_ptr<TargetLegalizer>
makeLegalizer(const TargetSubtarget &ST, TargetMachine &) {
  return std::make_unique<TargetLegalizer>(ST);
}

} // namespace
