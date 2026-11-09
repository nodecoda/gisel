//===- arm_query_runner.cpp - answer JSONL queries with ARM's rules ------===//
//
// Built twice: `official` links the target library's constructor, `ours` also
// links a replacement constructor object that includes the generated `.inc`.
// The two binaries differ only in which definition of the constructor the
// linker picks, so an answer difference is a rule difference.
//
// The configuration axes are the ones the constructor itself reads:
// `ST.useSoftFloat()`, `ST.hasVFP2Base()`, `ST.hasVFP4Base()`, `ST.hasNEON()`,
// `ST.hasV5TOps()`, the hardware-divide gate, and the AEABI gate.  Thumb1 is
// deliberately absent: the constructor returns before registering a rule, so
// the generated table -- which has no way to spell "this subtarget has no
// rules" -- would disagree on every query by construction.  That gap is
// recorded in docs/REPORT-cxx-corpus.md rather than papered over.
//===----------------------------------------------------------------------===//

#include "ARMLegalizerInfo.h"
#include "ARMSubtarget.h"
#include "llvm/Support/TargetSelect.h"

using namespace llvm;

using TargetSubtarget = ARMSubtarget;
using TargetLegalizer = ARMLegalizerInfo;

#include "query_runner_common.h"

namespace {

static void initializeTarget() {
  LLVMInitializeARMTargetInfo();
  LLVMInitializeARMTarget();
  LLVMInitializeARMTargetMC();
}

static ArrayRef<Config> configs() {
  // `armv7a-neon` is a Cortex-A7 (VFP4 + NEON + hardware divide); `a5` has no
  // VFP4; `nodiv` drops the divide instructions; `arm1176` is NEON-less;
  // `armv4t` has neither V5T nor VFP2; `thumbv7m` is M-profile (no FPU);
  // `armv7-soft` forces the soft-float ABI on a Cortex-A7.
  static const Config Table[] = {
      {"armv7a-neon", "armv7-unknown-linux-gnueabihf", "cortex-a7", "", std::nullopt},
      {"armv7a-nodiv", "armv7-unknown-linux-gnueabihf", "cortex-a7", "-hwdiv,-hwdiv-arm", std::nullopt},
      {"armv7a-a5", "armv7-unknown-linux-gnueabihf", "cortex-a5", "", std::nullopt},
      {"armv6-arm1176", "armv6-unknown-linux-gnueabihf", "arm1176jzf-s", "", std::nullopt},
      {"armv4t", "armv4t-unknown-linux-gnueabi", "arm7tdmi", "+soft-float", std::nullopt},
      {"thumbv7m", "thumbv7m-unknown-none-eabi", "cortex-m3", "", std::nullopt},
      {"armv7-soft", "armv7-unknown-linux-gnueabi", "generic", "+soft-float", std::nullopt},
  };
  return Table;
}

static std::unique_ptr<TargetLegalizer>
makeLegalizer(const TargetSubtarget &ST, TargetMachine &) {
  return std::make_unique<TargetLegalizer>(ST);
}

} // namespace
