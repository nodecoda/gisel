//===- spirv_query_runner.cpp - answer JSONL queries with SPIRV's rules ---===//
//
// Built twice: `official` links the target library's constructor, `ours` also
// links a replacement constructor object that includes the generated `.inc`.
// The two binaries differ only in which definition of the constructor the
// linker picks, so an answer difference is a rule difference.
//
// SPIRV is the one target whose configuration is not carried by the triple
// alone: the legalizer reads `ST.isShader()` and four extension queries, and
// the triple only fixes the pointer width.  Every configuration therefore
// starts from `spirv{32,64}-unknown-unknown` (environment Unknown, so
// `setEnv` is allowed) and the hook below sets the environment and the exact
// extension set the matching `tests/cases/spirv-features.json` entry assumes.
// Setting them after construction is what upstream itself does
// (`SPIRVAPI.cpp` calls `setEnv`/`initAvailableExtensions` on a live
// subtarget); the legalizer is then built from the finalized subtarget.
//===----------------------------------------------------------------------===//

#include "MCTargetDesc/SPIRVBaseInfo.h"
#include "SPIRVLegalizerInfo.h"
#include "SPIRVSubtarget.h"
#include "llvm/Support/TargetSelect.h"

using namespace llvm;

using TargetSubtarget = SPIRVSubtarget;
using TargetLegalizer = SPIRVLegalizerInfo;

#define GISEL_AB_TWEAK_SUBTARGET
#include "query_runner_common.h"

namespace {

static void initializeTarget() {
  LLVMInitializeSPIRVTargetInfo();
  LLVMInitializeSPIRVTarget();
  LLVMInitializeSPIRVTargetMC();
}

static ArrayRef<Config> configs() {
  static const Config Table[] = {
      {"spirv64-kernel", "spirv64-unknown-unknown", "", "", std::nullopt},
      {"spirv32-kernel", "spirv32-unknown-unknown", "", "", std::nullopt},
      {"spirv64-shader", "spirv64-unknown-unknown", "", "", std::nullopt},
      {"spirv32-shader", "spirv32-unknown-unknown", "", "", std::nullopt},
      {"spirv64-kernel-ext", "spirv64-unknown-unknown", "", "", std::nullopt},
      {"spirv32-shader-ext", "spirv32-unknown-unknown", "", "", std::nullopt},
  };
  return Table;
}

// The environment and extension axes, one entry per config above.
struct EnvSpec {
  const char *ID;
  bool Shader;
  bool AlteraInts;
  bool LongVector;
  bool BitInstructions;
};

static void tweakSubtarget(const Config &C, TargetSubtarget &ST) {
  static const EnvSpec Table[] = {
      {"spirv64-kernel", false, false, false, false},
      {"spirv32-kernel", false, false, false, false},
      {"spirv64-shader", true, false, false, false},
      {"spirv32-shader", true, false, false, false},
      {"spirv64-kernel-ext", false, true, true, true},
      // The shader-ext config has arbitrary precision off but IsExtendedInts
      // on, i.e. its untaken path is bit instructions (or int4).
      {"spirv32-shader-ext", true, false, true, true},
  };
  const EnvSpec *Spec = nullptr;
  for (const EnvSpec &E : Table)
    if (StringRef(E.ID) == C.ID)
      Spec = &E;
  if (!Spec) {
    errs() << "no environment spec for " << C.ID << "\n";
    return;
  }
  ExtensionSet Exts;
  if (Spec->AlteraInts)
    Exts.insert(SPIRV::Extension::SPV_ALTERA_arbitrary_precision_integers);
  if (Spec->LongVector)
    Exts.insert(SPIRV::Extension::SPV_EXT_long_vector);
  if (Spec->BitInstructions)
    Exts.insert(SPIRV::Extension::SPV_KHR_bit_instructions);
  // Extensions first, then the environment: both survive, and every extension
  // above is valid in the OpenCL environment the unknown OS selects.
  ST.initAvailableExtensions(Exts);
  ST.setEnv(Spec->Shader ? SPIRVSubtarget::Shader : SPIRVSubtarget::Kernel);
}

static std::unique_ptr<TargetLegalizer>
makeLegalizer(const TargetSubtarget &ST, TargetMachine &) {
  return std::make_unique<TargetLegalizer>(ST);
}

} // namespace
