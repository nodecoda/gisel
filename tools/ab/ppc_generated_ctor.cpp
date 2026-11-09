// The PowerPC A/B ours build replaces only the legalizer constructor.  The
// rest of the target library stays official.

#include "GISel/PPCLegalizerInfo.h"
#include "PPCSubtarget.h"
#include "llvm/CodeGen/TargetOpcodes.h"

using namespace llvm;
using namespace LegalizeActions;
using namespace LegalizeMutations;
using namespace LegalityPredicates;

PPCLegalizerInfo::PPCLegalizerInfo(const PPCSubtarget &ST) {
  using namespace TargetOpcode;
#include "PowerPCLegalizerInfo.inc"
}
