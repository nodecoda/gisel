// The RISC-V A/B ours build replaces only the legalizer constructor. The
// remaining target library, including custom legalization, stays official.

#include "RISCVSubtarget.h"
#include "GISel/RISCVLegalizerInfo.h"
#include "llvm/CodeGen/GlobalISel/MIPatternMatch.h"
#include "llvm/CodeGen/TargetLowering.h"
#include "llvm/CodeGen/TargetOpcodes.h"
#include "llvm/Target/TargetMachine.h"

using namespace llvm;
using namespace LegalizeActions;
using namespace LegalizeMutations;
using namespace LegalityPredicates;
using namespace MIPatternMatch;

// The generated fragment uses the same locals as the handwritten constructor:
// `ST` (the parameter), the `STI`/`XLen`/`sXLen` members, and `sDoubleXLen`/`p0`.
RISCVLegalizerInfo::RISCVLegalizerInfo(const RISCVSubtarget &ST)
    : STI(ST), XLen(STI.getXLen()), sXLen(LLT::scalar(XLen)) {
  using namespace TargetOpcode;
  const LLT sDoubleXLen = LLT::scalar(2 * XLen);
  const LLT p0 = LLT::pointer(0, XLen);
#include "RISCVLegalizerInfo.inc"
}
