// The M68k A/B ours build replaces only the legalizer constructor.  The rest
// of the target library, including custom legalization, stays official.

#include "GISel/M68kLegalizerInfo.h"
#include "M68kSubtarget.h"
#include "llvm/CodeGen/GlobalISel/MIPatternMatch.h"
#include "llvm/CodeGen/TargetLowering.h"
#include "llvm/CodeGen/TargetOpcodes.h"
#include "llvm/Target/TargetMachine.h"

using namespace llvm;
using namespace LegalizeActions;
using namespace LegalizeMutations;
using namespace LegalityPredicates;
using namespace MIPatternMatch;

M68kLegalizerInfo::M68kLegalizerInfo(const M68kSubtarget &ST) {
  using namespace TargetOpcode;
  const M68kSubtarget &Subtarget = ST;
#include "M68kLegalizerInfo.inc"
}
