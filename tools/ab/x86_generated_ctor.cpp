// The X86 A/B ours build replaces only the legalizer constructor.  The
// remaining target library, including custom legalization, stays official.

#include "X86Subtarget.h"
#include "GISel/X86LegalizerInfo.h"
#include "llvm/CodeGen/GlobalISel/MIPatternMatch.h"
#include "llvm/CodeGen/TargetLowering.h"
#include "llvm/CodeGen/TargetOpcodes.h"
#include "llvm/Target/TargetMachine.h"

using namespace llvm;
using namespace LegalizeActions;
using namespace LegalizeMutations;
using namespace LegalityPredicates;
using namespace MIPatternMatch;

X86LegalizerInfo::X86LegalizerInfo(const X86Subtarget &STI,
                                   const X86TargetMachine &TM)
    : Subtarget(STI) {
  using namespace TargetOpcode;
  const X86Subtarget &Subtarget = STI;
#include "X86LegalizerInfo.inc"
  verify(*STI.getInstrInfo());
}
