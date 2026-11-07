// The AArch64 A/B ours build replaces only the legalizer constructor. The
// remaining target library, including custom legalization, stays official.

#include "AArch64Subtarget.h"
#include "GISel/AArch64LegalizerInfo.h"
#include "llvm/CodeGen/GlobalISel/MIPatternMatch.h"
#include "llvm/CodeGen/TargetLowering.h"
#include "llvm/CodeGen/TargetOpcodes.h"
#include "llvm/Target/TargetMachine.h"

using namespace llvm;
using namespace LegalizeActions;
using namespace LegalizeMutations;
using namespace LegalityPredicates;
using namespace MIPatternMatch;

AArch64LegalizerInfo::AArch64LegalizerInfo(const AArch64Subtarget &ST)
    : ST(&ST) {
  using namespace TargetOpcode;
  const AArch64Subtarget &Subtarget = ST;
  const TargetMachine &TM = ST.getTargetLowering()->getTargetMachine();
#include "AArch64LegalizerInfo.inc"
}
