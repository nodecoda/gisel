// The WebAssembly A/B ours build replaces only the legalizer constructor.
// The rest of the target library, including legalizeCustom, stays official.

#include "GISel/WebAssemblyLegalizerInfo.h"
#include "WebAssemblySubtarget.h"
#include "llvm/CodeGen/TargetOpcodes.h"

using namespace llvm;
using namespace LegalizeActions;
using namespace LegalizeMutations;
using namespace LegalityPredicates;

WebAssemblyLegalizerInfo::WebAssemblyLegalizerInfo(
    const WebAssemblySubtarget &ST) {
  using namespace TargetOpcode;
#include "WebAssemblyLegalizerInfo.inc"
}
