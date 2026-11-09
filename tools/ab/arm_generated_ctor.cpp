// The ARM A/B ours build replaces only the legalizer constructor.  The rest of
// the target library stays official.

#include "ARMLegalizerInfo.h"
#include "ARMSubtarget.h"
#include "llvm/CodeGen/TargetOpcodes.h"

using namespace llvm;
using namespace LegalizeActions;
using namespace LegalizeMutations;
using namespace LegalityPredicates;

// The class keeps a reference to the subtarget; the official constructor
// initialises it in its member-init list, and so must this one.
ARMLegalizerInfo::ARMLegalizerInfo(const ARMSubtarget &ST) : ST(ST) {
  using namespace TargetOpcode;
#include "ARMLegalizerInfo.inc"
}
