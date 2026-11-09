//===- m68k_query_runner.cpp - answer JSONL queries with M68k's legalizer -===//
//
// Built twice: `official` links the target library's constructor, `ours` also
// links a replacement constructor object that includes the generated `.inc`.
// The two binaries differ only in which definition of the constructor the
// linker picks, so an answer difference is a rule difference.
//===----------------------------------------------------------------------===//

#include "GISel/M68kLegalizerInfo.h"
#include "M68kSubtarget.h"
#include "M68kTargetMachine.h"
#include "llvm/Support/TargetSelect.h"

using namespace llvm;

using TargetSubtarget = M68kSubtarget;
using TargetLegalizer = M68kLegalizerInfo;

#include "query_runner_common.h"

namespace {

static void initializeTarget() {
  LLVMInitializeM68kTargetInfo();
  LLVMInitializeM68kTarget();
  LLVMInitializeM68kTargetMC();
}

static ArrayRef<Config> configs() {
  // M68k's constructor reads no subtarget feature, so the configuration axis
  // is one point.  `M68040` is the CPU the GlobalISel MIR tests run on.
  static const Config Table[] = {
      {"default", "m68k", "M68040", "", std::nullopt},
  };
  return Table;
}

static std::unique_ptr<TargetLegalizer>
makeLegalizer(const TargetSubtarget &ST, TargetMachine &) {
  return std::make_unique<TargetLegalizer>(ST);
}

} // namespace
