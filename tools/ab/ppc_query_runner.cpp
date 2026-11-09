//===- ppc_query_runner.cpp - answer JSONL queries with PowerPC's rules ---===//
//
// Built twice: `official` links the target library's constructor, `ours` also
// links a replacement constructor object that includes the generated `.inc`.
// The two binaries differ only in which definition of the constructor the
// linker picks, so an answer difference is a rule difference.
//
// The constructor reads no subtarget feature: every rule is about types, so
// the configuration axis is one point, like M68k.
//===----------------------------------------------------------------------===//

#include "GISel/PPCLegalizerInfo.h"
#include "PPCSubtarget.h"
#include "PPCTargetMachine.h"
#include "llvm/Support/TargetSelect.h"

using namespace llvm;

using TargetSubtarget = PPCSubtarget;
using TargetLegalizer = PPCLegalizerInfo;

#include "query_runner_common.h"

namespace {

static void initializeTarget() {
  LLVMInitializePowerPCTargetInfo();
  LLVMInitializePowerPCTarget();
  LLVMInitializePowerPCTargetMC();
}

static ArrayRef<Config> configs() {
  // The legalizer assumes the 64-bit register file (P0 is `pointer(0, 64)`),
  // so the triple is ppc64le; the CPU does not change a rule.
  static const Config Table[] = {
      {"default", "powerpc64le-unknown-linux-gnu", "", "", std::nullopt},
  };
  return Table;
}

static std::unique_ptr<TargetLegalizer>
makeLegalizer(const TargetSubtarget &ST, TargetMachine &) {
  return std::make_unique<TargetLegalizer>(ST);
}

} // namespace
