// The Mips A/B ours build replaces only the legalizer constructor.  The rest
// of the target library stays official.

#include "MipsLegalizerInfo.h"
#include "MipsSubtarget.h"
#include "llvm/CodeGen/TargetOpcodes.h"

using namespace llvm;
using namespace LegalizeActions;
using namespace LegalizeMutations;
using namespace LegalityPredicates;

MipsLegalizerInfo::MipsLegalizerInfo(const MipsSubtarget &ST) {
  using namespace TargetOpcode;
#include "MipsLegalizerInfo.inc"
}
