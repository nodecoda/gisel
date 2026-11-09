//===- mips_query_runner.cpp - answer JSONL queries with Mips' rules -----===//
//
// Built twice: `official` links the target library's constructor, `ours` also
// links a replacement constructor object that includes the generated `.inc`.
// The two binaries differ only in which definition of the constructor the
// linker picks, so an answer difference is a rule difference.
//
// The constructor reads three subtarget predicates: `ST.hasMSA()` (the vector
// rules), `ST.hasMips32r2()` (G_BSWAP legal vs. lower), and
// `ST.systemSupportsUnalignedAccess()` (which memory sizes need an aligned
// access).  The five configurations below are those three axes on the
// 32-bit flavours the legalizer assumes (`p0` is `pointer(0, 32)`).
//===----------------------------------------------------------------------===//

#include "MipsLegalizerInfo.h"
#include "MipsSubtarget.h"
#include "llvm/Support/TargetSelect.h"

using namespace llvm;

using TargetSubtarget = MipsSubtarget;
using TargetLegalizer = MipsLegalizerInfo;

#include "query_runner_common.h"

namespace {

static void initializeTarget() {
  LLVMInitializeMipsTargetInfo();
  LLVMInitializeMipsTarget();
  LLVMInitializeMipsTargetMC();
}

static ArrayRef<Config> configs() {
  // MSA needs the 64-bit FP register file (`+fp64`) or the subtarget reports
  // it unavailable.
  static const Config Table[] = {
      {"mips32", "mips-unknown-linux-gnu", "mips32", "", std::nullopt},
      {"mips32r2", "mips-unknown-linux-gnu", "mips32r2", "", std::nullopt},
      {"mips32r6", "mips-unknown-linux-gnu", "mips32r6", "", std::nullopt},
      {"mips32r5-msa", "mips-unknown-linux-gnu", "mips32r5", "+msa,+fp64", std::nullopt},
      {"mips32r6-msa", "mips-unknown-linux-gnu", "mips32r6", "+msa,+fp64", std::nullopt},
  };
  return Table;
}

static std::unique_ptr<TargetLegalizer>
makeLegalizer(const TargetSubtarget &ST, TargetMachine &) {
  return std::make_unique<TargetLegalizer>(ST);
}

} // namespace
