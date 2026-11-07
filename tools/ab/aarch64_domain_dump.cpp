//===- aarch64_domain_dump.cpp - dump LLVM's answerless AArch64 domain -----===//
//
// The table-point include is the fixed question set.  This program only
// serializes it; it never asks a legalizer for an answer.
//===----------------------------------------------------------------------===//

#include "llvm/ADT/SmallVector.h"
#include "llvm/CodeGenTypes/LowLevelType.h"
#include "llvm/CodeGen/TargetOpcodes.h"
#include "llvm/Support/raw_ostream.h"
#include <cstdint>
#include <set>
#include <cstdlib>

using namespace llvm;

struct AArch64TablePoint {
  unsigned Opcode;
  const char *Name;
  uint8_t NumTypes;
  LLT Types[3];
  LLT MemTy;
  uint64_t Align;
  bool HasMem;
};

#include "AArch64LegalizerTablePointsForTest.inc"

struct Config {
  const char *ID;
  bool HasSVE;
  bool HasBF16;
  bool HasFullFP16;
};

static const Config Configs[] = {
    {"baseline", false, false, false},
    {"small-cm", false, false, false},
    {"fullfp16", false, false, true},
    {"sve", true, false, true},
    {"bf16", false, true, false},
    {"cssc", false, false, false},
    {"rcpc3", false, false, false},
    {"lse", false, false, false},
    {"outline-atomics", false, false, false},
};

static bool typeIsAvailable(LLT Ty, const Config &C) {
  if (!Ty.isValid())
    return false;
  if (Ty.isVector() && Ty.isScalable() && !C.HasSVE)
    return false;
  if (Ty.isBFloat16() && !C.HasBF16)
    return false;
  if (Ty.isFloat() && Ty.getScalarSizeInBits() == 16 && !C.HasFullFP16 &&
      !C.HasBF16 && !C.HasSVE)
    return false;
  return true;
}

static std::string lltStr(LLT Ty) {
  if (!Ty.isValid())
    return "LLT_invalid";
  if (Ty.isPointer())
    return "p" + std::to_string(Ty.getAddressSpace()) + ":" +
           std::to_string(Ty.getSizeInBits());
  if (Ty.isVector()) {
    std::string Elem = lltStr(Ty.getElementType());
    return (Ty.isScalable() ? "nxv" : "v") +
           std::to_string(Ty.getElementCount().getKnownMinValue()) + Elem;
  }
  if (Ty.isBFloat16())
    return "bf16";
  if (Ty.isFloat())
    return "f" + std::to_string(Ty.getScalarSizeInBits());
  if (Ty.isInteger())
    return "i" + std::to_string(Ty.getScalarSizeInBits());
  return "s" + std::to_string(Ty.getScalarSizeInBits());
}

static std::string jsonString(StringRef S) {
  std::string Out = "\"";
  for (char C : S) {
    if (C == '\"' || C == '\\') {
      Out += '\\';
      Out += C;
    } else if (C == '\n') {
      Out += "\\n";
    } else {
      Out += C;
    }
  }
  Out += '"';
  return Out;
}

int main() {
  SmallVector<AArch64TablePoint, 0> Points;
  aArch64CollectTablePoints(Points, /*PointerBits=*/64);
  std::set<std::string> Seen;
  unsigned Counts[sizeof(Configs) / sizeof(Configs[0])] = {};

  for (const Config &C : Configs) {
    for (const AArch64TablePoint &P : Points) {
      bool Available = true;
      for (unsigned I = 0; I != P.NumTypes; ++I)
        Available &= typeIsAvailable(P.Types[I], C);
      if (P.HasMem)
        Available &= typeIsAvailable(P.MemTy, C);
      if (!Available)
        continue;

      std::string Query = "{\"config\":" + jsonString(C.ID) +
                          ",\"name\":" + jsonString(P.Name) +
                          ",\"types\":[";
      for (unsigned I = 0; I != P.NumTypes; ++I) {
        if (I)
          Query += ',';
        Query += jsonString(lltStr(P.Types[I]));
      }
      Query += "],\"mem\":";
      if (!P.HasMem)
        Query += "null";
      else
        Query += "[" + jsonString(lltStr(P.MemTy)) + "," +
                 std::to_string(P.Align) + "]";
      Query += ",\"imms\":[]}";
      if (Seen.insert(Query).second) {
        ++Counts[&C - Configs];
        outs() << Query << '\n';
      }
    }
  }
  unsigned Total = 0;
  for (unsigned Count : Counts)
    Total += Count;
  const char *Expected = std::getenv("AARCH64_EXPECTED_QUERIES");
  if (Expected && std::to_string(Total) != Expected) {
    errs() << "AArch64 domain size changed: got " << Total
           << ", expected " << Expected << '\n';
    return 1;
  }
  errs() << "AArch64 domain: " << Total << " unique queries\n";
  return 0;
}
