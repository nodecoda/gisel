// The SPIRV A/B ours build replaces only the legalizer constructor.  The rest
// of the target library stays official.
//
// The two statements the importer lists as "constructor plumbing" are restored
// here rather than in the corpus: `legalizeCustom` reads `ST`/`GR`, and the
// upstream constructor ends with the same `verify` call.  Omitting them would
// compile, but ours would then skip the table check official performs.

#include "SPIRVLegalizerInfo.h"
#include "SPIRVSubtarget.h"
#include "llvm/CodeGen/TargetOpcodes.h"

using namespace llvm;
using namespace LegalizeActions;
using namespace LegalizeMutations;
using namespace LegalityPredicates;

SPIRVLegalizerInfo::SPIRVLegalizerInfo(const SPIRVSubtarget &ST) {
  this->ST = &ST;
  GR = ST.getSPIRVGlobalRegistry();
  using namespace TargetOpcode;
#include "SPIRVLegalizerInfo.inc"
  verify(*ST.getInstrInfo());
}
