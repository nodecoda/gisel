/*===- TableGen'erated file -------------------------------------*- C++ -*-===*\
|*                                                                            *|
|* GlobalISel legalizer rule fragments                                        *|
|*                                                                            *|
|* Automatically generated file, do not edit!                                 *|
|*                                                                            *|
\*===----------------------------------------------------------------------===*/

  bool R_XLen_32 = XLen == 32;
  bool R_XLen_64 = XLen == 64;
  bool R_XLen_le_ELen = XLen <= ST.getELen();
  bool R_enableUnalignedScalarMem = ST.enableUnalignedScalarMem();
  bool R_getELen_64 = ST.getELen() == 64;
  bool R_hasStdExtA = ST.hasStdExtA();
  bool R_hasStdExtD = ST.hasStdExtD();
  bool R_hasStdExtF = ST.hasStdExtF();
  bool R_hasStdExtM = ST.hasStdExtM();
  bool R_hasStdExtP = ST.hasStdExtP();
  bool R_hasStdExtZbb = ST.hasStdExtZbb();
  bool R_hasStdExtZbc = ST.hasStdExtZbc();
  bool R_hasStdExtZbkb = ST.hasStdExtZbkb();
  bool R_hasStdExtZbkc = ST.hasStdExtZbkc();
  bool R_hasStdExtZfa = ST.hasStdExtZfa();
  bool R_hasStdExtZfh = ST.hasStdExtZfh();
  bool R_hasStdExtZfhmin = ST.hasStdExtZfhmin();
  bool R_hasStdExtZilsd = ST.hasStdExtZilsd();
  bool R_hasStdExtZmmul = ST.hasStdExtZmmul();
  bool R_hasVInstructions = ST.hasVInstructions();
  bool R_hasVInstructionsF64 = ST.hasVInstructionsF64();
  bool R_hasVInstructionsI64 = ST.hasVInstructionsI64();
  bool R_hasVendorXTHeadBb = ST.hasVendorXTHeadBb();
  bool R_is64Bit = ST.is64Bit();
  bool R_subtargetInfoHasZbb = STI.hasStdExtZbb();

  const LLT R_sXLen_lo = LLT::scalar(32);
  const LLT R_sXLen_hi = LLT::scalar(64);
  const LLT R_sDoubleXLen_lo = LLT::scalar(64);
  const LLT R_sDoubleXLen_hi = LLT::scalar(128);
  const LLT R_p0 = LLT::pointer(0, XLen);
  const LLT R_s1 = LLT::scalar(1);
  const LLT R_s8 = LLT::scalar(8);
  const LLT R_s16 = LLT::scalar(16);
  const LLT R_f16 = LLT::float16();
  const LLT R_s32 = LLT::scalar(32);
  const LLT R_s64 = LLT::scalar(64);
  const LLT R_s128 = LLT::scalar(128);
  const LLT R_nxv1s1 = LLT::scalable_vector(1, R_s1);
  const LLT R_nxv2s1 = LLT::scalable_vector(2, R_s1);
  const LLT R_nxv4s1 = LLT::scalable_vector(4, R_s1);
  const LLT R_nxv8s1 = LLT::scalable_vector(8, R_s1);
  const LLT R_nxv16s1 = LLT::scalable_vector(16, R_s1);
  const LLT R_nxv32s1 = LLT::scalable_vector(32, R_s1);
  const LLT R_nxv64s1 = LLT::scalable_vector(64, R_s1);
  const LLT R_nxv1s8 = LLT::scalable_vector(1, R_s8);
  const LLT R_nxv2s8 = LLT::scalable_vector(2, R_s8);
  const LLT R_nxv4s8 = LLT::scalable_vector(4, R_s8);
  const LLT R_nxv8s8 = LLT::scalable_vector(8, R_s8);
  const LLT R_nxv16s8 = LLT::scalable_vector(16, R_s8);
  const LLT R_nxv32s8 = LLT::scalable_vector(32, R_s8);
  const LLT R_nxv64s8 = LLT::scalable_vector(64, R_s8);
  const LLT R_nxv1s16 = LLT::scalable_vector(1, R_s16);
  const LLT R_nxv2s16 = LLT::scalable_vector(2, R_s16);
  const LLT R_nxv4s16 = LLT::scalable_vector(4, R_s16);
  const LLT R_nxv8s16 = LLT::scalable_vector(8, R_s16);
  const LLT R_nxv16s16 = LLT::scalable_vector(16, R_s16);
  const LLT R_nxv32s16 = LLT::scalable_vector(32, R_s16);
  const LLT R_nxv1s32 = LLT::scalable_vector(1, R_s32);
  const LLT R_nxv2s32 = LLT::scalable_vector(2, R_s32);
  const LLT R_nxv4s32 = LLT::scalable_vector(4, R_s32);
  const LLT R_nxv8s32 = LLT::scalable_vector(8, R_s32);
  const LLT R_nxv16s32 = LLT::scalable_vector(16, R_s32);
  const LLT R_nxv1s64 = LLT::scalable_vector(1, R_s64);
  const LLT R_nxv2s64 = LLT::scalable_vector(2, R_s64);
  const LLT R_nxv4s64 = LLT::scalable_vector(4, R_s64);
  const LLT R_nxv8s64 = LLT::scalable_vector(8, R_s64);
  const LLT R_nxv1p0 = LLT::scalable_vector(1, R_p0);
  const LLT R_nxv2p0 = LLT::scalable_vector(2, R_p0);
  const LLT R_nxv4p0 = LLT::scalable_vector(4, R_p0);
  const LLT R_nxv8p0 = LLT::scalable_vector(8, R_p0);
  const LLT R_nxv16p0 = LLT::scalable_vector(16, R_p0);
  const LLT R_sXLen = (R_XLen_64 ? R_s64 : R_s32);
  const LLT R_sDoubleXLen = (R_XLen_64 ? R_s128 : R_s64);
  const LLT R_maxScalar = (R_XLen_64 || R_hasStdExtD ? R_s64 : R_s32);

  getActionDefinitionsBuilder({G_ADD, G_SUB})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_sXLen); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64))); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_is64Bit) && ((Query.Types[0] == R_s32)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder({G_AND, G_OR, G_XOR})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_sXLen); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64))); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder({G_UADDE, G_UADDO, G_USUBE, G_USUBO, G_READ_REGISTER, G_WRITE_REGISTER})
      .lower();
  getActionDefinitionsBuilder({G_SADDE, G_SADDO, G_SSUBE, G_SSUBO})
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .lower();
  getActionDefinitionsBuilder({G_UADDSAT, G_SADDSAT, G_USUBSAT, G_SSUBSAT, G_SSHLSAT, G_USHLSAT})
      .lower();
  getActionDefinitionsBuilder({G_SHL, G_ASHR, G_LSHR})
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_sXLen}})(Query); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder({G_ZEXT, G_SEXT, G_ANYEXT})
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s16}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{R_s64, R_s16}, {R_s64, R_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && (((Query.Types[1] == R_nxv1s8 || Query.Types[1] == R_nxv2s8 || Query.Types[1] == R_nxv4s8 || Query.Types[1] == R_nxv8s8 || Query.Types[1] == R_nxv16s8 || Query.Types[1] == R_nxv32s8 || Query.Types[1] == R_nxv64s8 || Query.Types[1] == R_nxv1s16 || Query.Types[1] == R_nxv2s16 || Query.Types[1] == R_nxv4s16 || Query.Types[1] == R_nxv8s16 || Query.Types[1] == R_nxv16s16 || Query.Types[1] == R_nxv32s16 || Query.Types[1] == R_nxv1s32 || Query.Types[1] == R_nxv2s32 || Query.Types[1] == R_nxv4s32 || Query.Types[1] == R_nxv8s32 || Query.Types[1] == R_nxv16s32 || Query.Types[1] == R_nxv1s64 || Query.Types[1] == R_nxv2s64 || Query.Types[1] == R_nxv4s64 || Query.Types[1] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[1]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64)))); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((Query.Types[1] == R_nxv1s1 || Query.Types[1] == R_nxv2s1 || Query.Types[1] == R_nxv4s1 || Query.Types[1] == R_nxv8s1 || Query.Types[1] == R_nxv16s1 || Query.Types[1] == R_nxv32s1 || Query.Types[1] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64))); })
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder(G_TRUNC)
      .alwaysLegal();
  getActionDefinitionsBuilder(G_SEXT_INREG)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((Query.Types[0] == R_sXLen)) && (((R_subtargetInfoHasZbb) && (((((Query.Types[0]).getSizeInBits().getKnownMinValue() == 64)) && ((Query.Immediates[0] == 32))) || (LegalityPredicates::immInSet(0, {8, 16})(Query)))) || ((!(R_subtargetInfoHasZbb)) && ((((Query.Types[0]).getSizeInBits().getKnownMinValue() == 64)) && ((Query.Immediates[0] == 32))))); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .lower();
  getActionDefinitionsBuilder(G_MERGE_VALUES)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_XLen_32) && ((R_hasStdExtD) || (R_hasStdExtZilsd))) && (((Query.Types[0] == R_s64)) && ((Query.Types[1] == R_s32))); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, (R_XLen_64 ? 64 : 32))
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, (R_XLen_64 ? 64 : 32))
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder(G_UNMERGE_VALUES)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_XLen_32) && ((R_hasStdExtD) || (R_hasStdExtZilsd))) && (((Query.Types[1] == R_s64)) && ((Query.Types[0] == R_s32))); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, (R_XLen_64 ? 64 : 32))
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, (R_XLen_64 ? 64 : 32))
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen);
  getActionDefinitionsBuilder({G_FSHL, G_FSHR})
      .lower();
  getActionDefinitionsBuilder({G_ROTR, G_ROTL})
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasStdExtZbb) || (R_hasStdExtZbkb)) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_sXLen}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && ((R_hasStdExtZbb) || (R_hasStdExtZbkb))) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}})(Query)); })
      .lower();
  getActionDefinitionsBuilder(G_BITREVERSE)
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbkb) && ((Query.Types[0] == R_s8)); })
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .lower();
  getActionDefinitionsBuilder(G_BITCAST)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) || (((Query.Types[0] == R_nxv1s1 || Query.Types[0] == R_nxv2s1 || Query.Types[0] == R_nxv4s1 || Query.Types[0] == R_nxv8s1 || Query.Types[0] == R_nxv16s1 || Query.Types[0] == R_nxv32s1 || Query.Types[0] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64))))) && ((((Query.Types[1] == R_nxv1s8 || Query.Types[1] == R_nxv2s8 || Query.Types[1] == R_nxv4s8 || Query.Types[1] == R_nxv8s8 || Query.Types[1] == R_nxv16s8 || Query.Types[1] == R_nxv32s8 || Query.Types[1] == R_nxv64s8 || Query.Types[1] == R_nxv1s16 || Query.Types[1] == R_nxv2s16 || Query.Types[1] == R_nxv4s16 || Query.Types[1] == R_nxv8s16 || Query.Types[1] == R_nxv16s16 || Query.Types[1] == R_nxv32s16 || Query.Types[1] == R_nxv1s32 || Query.Types[1] == R_nxv2s32 || Query.Types[1] == R_nxv4s32 || Query.Types[1] == R_nxv8s32 || Query.Types[1] == R_nxv16s32 || Query.Types[1] == R_nxv1s64 || Query.Types[1] == R_nxv2s64 || Query.Types[1] == R_nxv4s64 || Query.Types[1] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[1]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64)))) || (((Query.Types[1] == R_nxv1s1 || Query.Types[1] == R_nxv2s1 || Query.Types[1] == R_nxv4s1 || Query.Types[1] == R_nxv8s1 || Query.Types[1] == R_nxv16s1 || Query.Types[1] == R_nxv32s1 || Query.Types[1] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64))))); });
  getActionDefinitionsBuilder(G_BSWAP)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasStdExtZbb) || (R_hasStdExtZbkb)) && ((Query.Types[0] == R_sXLen)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return (R_hasStdExtZbb) || (R_hasStdExtZbkb); }, 0, R_sXLen)
      .coreMaxScalar([=](const LegalityQuery &Query) { return (R_hasStdExtZbb) || (R_hasStdExtZbkb); }, 0, R_sXLen)
      .coreMaxScalar([=](const LegalityQuery &Query) { return !((R_hasStdExtZbb) || (R_hasStdExtZbkb)); }, 0, R_sXLen)
      .coreLowerIf([=](const LegalityQuery &Query) { return !((R_hasStdExtZbb) || (R_hasStdExtZbkb)); });
  getActionDefinitionsBuilder(G_CLMUL)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbkc) && ((Query.Types[0] == R_sXLen)); })
      .unsupported();
  getActionDefinitionsBuilder(G_CLMULH)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbkc) && ((Query.Types[0] == R_sXLen)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtZbkc)) && ((Query.Types[0] == R_s32)); })
      .unsupported();
  getActionDefinitionsBuilder(G_CLMULR)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbc) && ((Query.Types[0] == R_sXLen)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtZbc)) && ((Query.Types[0] == R_s32)); })
      .unsupported();
  getActionDefinitionsBuilder(G_CTLZ_ZERO_POISON)
      .coreMinScalar([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (R_hasVendorXTHeadBb); }, 0, R_sXLen)
      .coreMaxScalar([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (R_hasVendorXTHeadBb); }, 0, R_sXLen)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (R_hasVendorXTHeadBb); }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (R_hasVendorXTHeadBb); }, 1, 0)
      .coreMaxScalar([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (!(R_hasVendorXTHeadBb)); }, 0, R_sXLen)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (!(R_hasVendorXTHeadBb)); }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (!(R_hasVendorXTHeadBb)); }, 1, 0)
      .lower();
  getActionDefinitionsBuilder(G_CTTZ_ZERO_POISON)
      .coreMaxScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 0, R_sXLen)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 1, 0)
      .lower();
  getActionDefinitionsBuilder(G_CTLZ)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbb) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_sXLen}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbb) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}})(Query)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0, R_s32)
      .coreMaxScalar([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0, R_sXLen)
      .coreWidenScalarToNextPow2([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 1, 0)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((!(R_hasStdExtZbb)) && (R_hasVendorXTHeadBb)) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_sXLen}})(Query)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (R_hasVendorXTHeadBb); }, 0, R_sXLen)
      .coreMaxScalar([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (R_hasVendorXTHeadBb); }, 0, R_sXLen)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (R_hasVendorXTHeadBb); }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (R_hasVendorXTHeadBb); }, 1, 0)
      .coreMaxScalar([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (!(R_hasVendorXTHeadBb)); }, 0, R_sXLen)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (!(R_hasVendorXTHeadBb)); }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (!(R_hasVendorXTHeadBb)); }, 1, 0)
      .coreLowerIf([=](const LegalityQuery &Query) { return (!(R_hasStdExtZbb)) && (!(R_hasVendorXTHeadBb)); });
  getActionDefinitionsBuilder(G_CTTZ)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbb) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_sXLen}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbb) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}})(Query)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0, R_s32)
      .coreMaxScalar([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0, R_sXLen)
      .coreWidenScalarToNextPow2([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 1, 0)
      .coreMaxScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 0, R_sXLen)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 1, 0)
      .coreLowerIf([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); });
  getActionDefinitionsBuilder(G_CTLS)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtP) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_sXLen}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtP) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}})(Query)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtP; }, 0, R_s32)
      .coreMaxScalar([=](const LegalityQuery &Query) { return R_hasStdExtP; }, 0, R_sXLen)
      .coreWidenScalarToNextPow2([=](const LegalityQuery &Query) { return R_hasStdExtP; }, 0)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return R_hasStdExtP; }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return R_hasStdExtP; }, 1, 0)
      .coreMaxScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtP); }, 0, R_sXLen)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return !(R_hasStdExtP); }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return !(R_hasStdExtP); }, 1, 0)
      .coreLowerIf([=](const LegalityQuery &Query) { return !(R_hasStdExtP); });
  getActionDefinitionsBuilder(G_CTPOP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbb) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_sXLen}})(Query)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0, R_sXLen)
      .coreMaxScalar([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0, R_sXLen)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 1, 0)
      .coreWidenScalarToNextPow2([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 0, 8)
      .coreMinScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 0, R_s8)
      .coreMaxScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 0, R_sXLen)
      .coreMinScalarSameAs([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 1, 0)
      .coreMaxScalarSameAs([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); }, 1, 0)
      .coreLowerIf([=](const LegalityQuery &Query) { return !(R_hasStdExtZbb); });
  getActionDefinitionsBuilder(G_CONSTANT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_p0); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(R_is64Bit)) && ((Query.Types[0] == R_s32)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_is64Bit) && ((Query.Types[0] == R_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder(G_FREEZE)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_s16 || Query.Types[0] == R_s32 || Query.Types[0] == R_p0); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_is64Bit) && ((Query.Types[0] == R_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((Query.Types[0] == R_nxv1s1 || Query.Types[0] == R_nxv2s1 || Query.Types[0] == R_nxv4s1 || Query.Types[0] == R_nxv8s1 || Query.Types[0] == R_nxv16s1 || Query.Types[0] == R_nxv32s1 || Query.Types[0] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64))); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder({G_IMPLICIT_DEF, G_CONSTANT_FOLD_BARRIER})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_s32 || Query.Types[0] == R_sXLen || Query.Types[0] == R_p0); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((Query.Types[0] == R_nxv1s1 || Query.Types[0] == R_nxv2s1 || Query.Types[0] == R_nxv4s1 || Query.Types[0] == R_nxv8s1 || Query.Types[0] == R_nxv16s1 || Query.Types[0] == R_nxv32s1 || Query.Types[0] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64))); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder(G_ICMP)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_sXLen}, {R_sXLen, R_p0}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (((Query.Types[0] == R_nxv1s1 || Query.Types[0] == R_nxv2s1 || Query.Types[0] == R_nxv4s1 || Query.Types[0] == R_nxv8s1 || Query.Types[0] == R_nxv16s1 || Query.Types[0] == R_nxv32s1 || Query.Types[0] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && (((Query.Types[1] == R_nxv1s8 || Query.Types[1] == R_nxv2s8 || Query.Types[1] == R_nxv4s8 || Query.Types[1] == R_nxv8s8 || Query.Types[1] == R_nxv16s8 || Query.Types[1] == R_nxv32s8 || Query.Types[1] == R_nxv64s8 || Query.Types[1] == R_nxv1s16 || Query.Types[1] == R_nxv2s16 || Query.Types[1] == R_nxv4s16 || Query.Types[1] == R_nxv8s16 || Query.Types[1] == R_nxv16s16 || Query.Types[1] == R_nxv32s16 || Query.Types[1] == R_nxv1s32 || Query.Types[1] == R_nxv2s32 || Query.Types[1] == R_nxv4s32 || Query.Types[1] == R_nxv8s32 || Query.Types[1] == R_nxv16s32 || Query.Types[1] == R_nxv1s64 || Query.Types[1] == R_nxv2s64 || Query.Types[1] == R_nxv4s64 || Query.Types[1] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[1]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64)))); })
      .coreWidenScalarOrEltToNextPow2OrMinSize([](const LegalityQuery &) { return true; }, 1, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder(G_SELECT)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_sXLen}, {R_p0, R_sXLen}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && (((Query.Types[1] == R_nxv1s1 || Query.Types[1] == R_nxv2s1 || Query.Types[1] == R_nxv4s1 || Query.Types[1] == R_nxv8s1 || Query.Types[1] == R_nxv16s1 || Query.Types[1] == R_nxv32s1 || Query.Types[1] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64)))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_XLen_64) || (R_hasStdExtD)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s64, R_sXLen}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_maxScalar)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen);
  getActionDefinitionsBuilder(G_LOAD)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_enableUnalignedScalarMem) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s16, R_p0, R_s8, 8}, {R_s32, R_p0, R_s8, 8}, {R_s16, R_p0, R_s16, 8}, {R_s32, R_p0, R_s16, 8}, {R_s32, R_p0, R_s32, 8}, {R_p0, R_p0, R_sXLen, 8}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(R_enableUnalignedScalarMem)) && (R_XLen_64) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s16, R_p0, R_s8, 8}, {R_s32, R_p0, R_s8, 8}, {R_s16, R_p0, R_s16, 16}, {R_s32, R_p0, R_s16, 16}, {R_s32, R_p0, R_s32, 32}, {R_p0, R_p0, R_sXLen, 64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(R_enableUnalignedScalarMem)) && (R_XLen_32) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s16, R_p0, R_s8, 8}, {R_s32, R_p0, R_s8, 8}, {R_s16, R_p0, R_s16, 16}, {R_s32, R_p0, R_s16, 16}, {R_s32, R_p0, R_s32, 32}, {R_p0, R_p0, R_sXLen, 32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_XLen_64) && ((R_enableUnalignedScalarMem) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s64, R_p0, R_s8, 8}, {R_s64, R_p0, R_s16, 8}, {R_s64, R_p0, R_s32, 8}, {R_s64, R_p0, R_s64, 8}})(Query))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_XLen_64) && ((!(R_enableUnalignedScalarMem)) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s64, R_p0, R_s8, 8}, {R_s64, R_p0, R_s16, 16}, {R_s64, R_p0, R_s32, 32}, {R_s64, R_p0, R_s64, 64}})(Query))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((!(R_XLen_64)) && ((R_hasStdExtD) || (R_hasStdExtZilsd))) && ((R_enableUnalignedScalarMem) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s64, R_p0, R_s64, 8}})(Query))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((!(R_XLen_64)) && ((R_hasStdExtD) || (R_hasStdExtZilsd))) && ((!(R_enableUnalignedScalarMem)) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s64, R_p0, R_s64, 64}})(Query))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasVInstructions) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_nxv2s8, R_p0, R_nxv2s8, 8}, {R_nxv4s8, R_p0, R_nxv4s8, 8}, {R_nxv8s8, R_p0, R_nxv8s8, 8}, {R_nxv16s8, R_p0, R_nxv16s8, 8}, {R_nxv32s8, R_p0, R_nxv32s8, 8}, {R_nxv64s8, R_p0, R_nxv64s8, 8}, {R_nxv2s16, R_p0, R_nxv2s16, 16}, {R_nxv4s16, R_p0, R_nxv4s16, 16}, {R_nxv8s16, R_p0, R_nxv8s16, 16}, {R_nxv16s16, R_p0, R_nxv16s16, 16}, {R_nxv32s16, R_p0, R_nxv32s16, 16}, {R_nxv2s32, R_p0, R_nxv2s32, 32}, {R_nxv4s32, R_p0, R_nxv4s32, 32}, {R_nxv8s32, R_p0, R_nxv8s32, 32}, {R_nxv16s32, R_p0, R_nxv16s32, 32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasVInstructions) && (R_getELen_64)) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_nxv1s8, R_p0, R_nxv1s8, 8}, {R_nxv1s16, R_p0, R_nxv1s16, 16}, {R_nxv1s32, R_p0, R_nxv1s32, 32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasVInstructions) && (R_hasVInstructionsI64)) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_nxv1s64, R_p0, R_nxv1s64, 64}, {R_nxv2s64, R_p0, R_nxv2s64, 64}, {R_nxv4s64, R_p0, R_nxv4s64, 64}, {R_nxv8s64, R_p0, R_nxv8s64, 64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasVInstructions) && (((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_hasVInstructions) && (R_XLen_le_ELen)) && (((Query.Types[0] == R_nxv1p0 || Query.Types[0] == R_nxv2p0 || Query.Types[0] == R_nxv4p0 || Query.Types[0] == R_nxv8p0 || Query.Types[0] == R_nxv16p0)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)) && ((((Query.Types[0]).getNumElements() != 16)) || (((Query.Types[0]).getScalarSizeInBits() == 32))))); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreLowerIf([=](const LegalityQuery &Query) { return (!(((Query.MMODescrs[0]).MemoryTy).isByteSized())) || (!(llvm::isPowerOf2_32(((Query.MMODescrs[0]).MemoryTy).getSizeInBytes().getKnownMinValue()))); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .lower();
  getActionDefinitionsBuilder(G_STORE)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_enableUnalignedScalarMem) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s16, R_p0, R_s8, 8}, {R_s32, R_p0, R_s8, 8}, {R_s16, R_p0, R_s16, 8}, {R_s32, R_p0, R_s16, 8}, {R_s32, R_p0, R_s32, 8}, {R_p0, R_p0, R_sXLen, 8}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(R_enableUnalignedScalarMem)) && (R_XLen_64) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s16, R_p0, R_s8, 8}, {R_s32, R_p0, R_s8, 8}, {R_s16, R_p0, R_s16, 16}, {R_s32, R_p0, R_s16, 16}, {R_s32, R_p0, R_s32, 32}, {R_p0, R_p0, R_sXLen, 64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(R_enableUnalignedScalarMem)) && (R_XLen_32) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s16, R_p0, R_s8, 8}, {R_s32, R_p0, R_s8, 8}, {R_s16, R_p0, R_s16, 16}, {R_s32, R_p0, R_s16, 16}, {R_s32, R_p0, R_s32, 32}, {R_p0, R_p0, R_sXLen, 32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_XLen_64) && ((R_enableUnalignedScalarMem) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s64, R_p0, R_s8, 8}, {R_s64, R_p0, R_s16, 8}, {R_s64, R_p0, R_s32, 8}, {R_s64, R_p0, R_s64, 8}})(Query))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_XLen_64) && ((!(R_enableUnalignedScalarMem)) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s64, R_p0, R_s8, 8}, {R_s64, R_p0, R_s16, 16}, {R_s64, R_p0, R_s32, 32}, {R_s64, R_p0, R_s64, 64}})(Query))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((!(R_XLen_64)) && ((R_hasStdExtD) || (R_hasStdExtZilsd))) && ((R_enableUnalignedScalarMem) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s64, R_p0, R_s64, 8}})(Query))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((!(R_XLen_64)) && ((R_hasStdExtD) || (R_hasStdExtZilsd))) && ((!(R_enableUnalignedScalarMem)) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s64, R_p0, R_s64, 64}})(Query))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasVInstructions) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_nxv2s8, R_p0, R_nxv2s8, 8}, {R_nxv4s8, R_p0, R_nxv4s8, 8}, {R_nxv8s8, R_p0, R_nxv8s8, 8}, {R_nxv16s8, R_p0, R_nxv16s8, 8}, {R_nxv32s8, R_p0, R_nxv32s8, 8}, {R_nxv64s8, R_p0, R_nxv64s8, 8}, {R_nxv2s16, R_p0, R_nxv2s16, 16}, {R_nxv4s16, R_p0, R_nxv4s16, 16}, {R_nxv8s16, R_p0, R_nxv8s16, 16}, {R_nxv16s16, R_p0, R_nxv16s16, 16}, {R_nxv32s16, R_p0, R_nxv32s16, 16}, {R_nxv2s32, R_p0, R_nxv2s32, 32}, {R_nxv4s32, R_p0, R_nxv4s32, 32}, {R_nxv8s32, R_p0, R_nxv8s32, 32}, {R_nxv16s32, R_p0, R_nxv16s32, 32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasVInstructions) && (R_getELen_64)) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_nxv1s8, R_p0, R_nxv1s8, 8}, {R_nxv1s16, R_p0, R_nxv1s16, 16}, {R_nxv1s32, R_p0, R_nxv1s32, 32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasVInstructions) && (R_hasVInstructionsI64)) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_nxv1s64, R_p0, R_nxv1s64, 64}, {R_nxv2s64, R_p0, R_nxv2s64, 64}, {R_nxv4s64, R_p0, R_nxv4s64, 64}, {R_nxv8s64, R_p0, R_nxv8s64, 64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasVInstructions) && (((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_hasVInstructions) && (R_XLen_le_ELen)) && (((Query.Types[0] == R_nxv1p0 || Query.Types[0] == R_nxv2p0 || Query.Types[0] == R_nxv4p0 || Query.Types[0] == R_nxv8p0 || Query.Types[0] == R_nxv16p0)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)) && ((((Query.Types[0]).getNumElements() != 16)) || (((Query.Types[0]).getScalarSizeInBits() == 32))))); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreLowerIf([=](const LegalityQuery &Query) { return (!(((Query.MMODescrs[0]).MemoryTy).isByteSized())) || (!(llvm::isPowerOf2_32(((Query.MMODescrs[0]).MemoryTy).getSizeInBytes().getKnownMinValue()))); })
      .lower();
  getActionDefinitionsBuilder({G_SEXTLOAD, G_ZEXTLOAD})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_enableUnalignedScalarMem) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_sXLen, R_p0, R_s8, 8}, {R_sXLen, R_p0, R_s16, 8}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(R_enableUnalignedScalarMem)) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_sXLen, R_p0, R_s8, 8}, {R_sXLen, R_p0, R_s16, 16}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_XLen_64) && ((R_enableUnalignedScalarMem) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s64, R_p0, R_s32, 8}})(Query))); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_XLen_64) && ((!(R_enableUnalignedScalarMem)) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{R_s64, R_p0, R_s32, 32}})(Query))); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .lower();
  getActionDefinitionsBuilder({G_PTR_ADD, G_PTRMASK})
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_p0, R_sXLen}})(Query); });
  getActionDefinitionsBuilder(G_PTRTOINT)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_p0}})(Query); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder(G_INTTOPTR)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_p0, R_sXLen}})(Query); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen);
  getActionDefinitionsBuilder(G_BR)
      .alwaysLegal();
  getActionDefinitionsBuilder(G_BRCOND)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_sXLen); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder(G_BRJT)
      .coreCustomIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_p0, R_sXLen}})(Query); });
  getActionDefinitionsBuilder(G_BRINDIRECT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_p0); });
  getActionDefinitionsBuilder(G_PHI)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_p0 || Query.Types[0] == R_s32 || Query.Types[0] == R_sXLen); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder({G_GLOBAL_VALUE, G_JUMP_TABLE, G_CONSTANT_POOL})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_p0); });
  getActionDefinitionsBuilder(G_MUL)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZmmul) && ((Query.Types[0] == R_sXLen)); })
      .coreWidenScalarToNextPow2([=](const LegalityQuery &Query) { return R_hasStdExtZmmul; }, 0)
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtZmmul; }, 0, R_sXLen)
      .coreMaxScalar([=](const LegalityQuery &Query) { return R_hasStdExtZmmul; }, 0, R_sXLen)
      .coreLibcallIf([=](const LegalityQuery &Query) { return (!(R_hasStdExtZmmul)) && ((Query.Types[0] == R_sXLen || Query.Types[0] == R_sDoubleXLen)); })
      .coreWidenScalarToNextPow2([=](const LegalityQuery &Query) { return !(R_hasStdExtZmmul); }, 0)
      .coreMinScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtZmmul); }, 0, R_sXLen)
      .coreMaxScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtZmmul); }, 0, R_sDoubleXLen);
  getActionDefinitionsBuilder({G_SMULH, G_UMULH})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZmmul) && ((Query.Types[0] == R_sXLen)); })
      .coreLowerIf([=](const LegalityQuery &Query) { return R_hasStdExtZmmul; })
      .coreLowerIf([=](const LegalityQuery &Query) { return (!(R_hasStdExtZmmul)) && ((Query.Types[0] == R_sXLen)); });
  getActionDefinitionsBuilder({G_SMULO, G_UMULO})
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtZmmul; }, 0, R_sXLen)
      .coreLowerIf([=](const LegalityQuery &Query) { return R_hasStdExtZmmul; })
      .coreMinScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtZmmul); }, 0, R_sXLen)
      .coreWidenTo([=](const LegalityQuery &Query) { return (!(R_hasStdExtZmmul)) && ((Query.Types[0] == R_sXLen)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, R_sDoubleXLen); })
      .coreLowerIf([=](const LegalityQuery &Query) { return !(R_hasStdExtZmmul); });
  getActionDefinitionsBuilder({G_SDIV, G_UDIV, G_UREM})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtM) && ((Query.Types[0] == R_sXLen)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtM) && ((Query.Types[0] == R_s32)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_hasStdExtM) && ((Query.Types[0] == R_sDoubleXLen)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtM; }, 0, R_s32)
      .coreMaxScalar([=](const LegalityQuery &Query) { return R_hasStdExtM; }, 0, R_sDoubleXLen)
      .coreWidenScalarToNextPow2([=](const LegalityQuery &Query) { return R_hasStdExtM; }, 0)
      .coreLibcallIf([=](const LegalityQuery &Query) { return (!(R_hasStdExtM)) && ((Query.Types[0] == R_sXLen || Query.Types[0] == R_sDoubleXLen)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtM); }, 0, R_sXLen)
      .coreMaxScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtM); }, 0, R_sDoubleXLen)
      .coreWidenScalarToNextPow2([=](const LegalityQuery &Query) { return !(R_hasStdExtM); }, 0);
  getActionDefinitionsBuilder(G_SREM)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtM) && ((Query.Types[0] == R_sXLen)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_hasStdExtM) && ((Query.Types[0] == R_sDoubleXLen)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtM; }, 0, R_sXLen)
      .coreMaxScalar([=](const LegalityQuery &Query) { return R_hasStdExtM; }, 0, R_sDoubleXLen)
      .coreWidenScalarToNextPow2([=](const LegalityQuery &Query) { return R_hasStdExtM; }, 0)
      .coreLibcallIf([=](const LegalityQuery &Query) { return (!(R_hasStdExtM)) && ((Query.Types[0] == R_sXLen || Query.Types[0] == R_sDoubleXLen)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtM); }, 0, R_sXLen)
      .coreMaxScalar([=](const LegalityQuery &Query) { return !(R_hasStdExtM); }, 0, R_sDoubleXLen)
      .coreWidenScalarToNextPow2([=](const LegalityQuery &Query) { return !(R_hasStdExtM); }, 0);
  getActionDefinitionsBuilder({G_SDIVREM, G_UDIVREM})
      .lower();
  getActionDefinitionsBuilder(G_ABS)
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbb) && ((Query.Types[0] == R_sXLen)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0, R_sXLen)
      .lower();
  getActionDefinitionsBuilder({G_ABDS, G_ABDU})
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0, R_sXLen)
      .lower();
  getActionDefinitionsBuilder({G_UMAX, G_UMIN, G_SMAX, G_SMIN})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZbb) && ((Query.Types[0] == R_sXLen)); })
      .coreMinScalar([=](const LegalityQuery &Query) { return R_hasStdExtZbb; }, 0, R_sXLen)
      .lower();
  getActionDefinitionsBuilder({G_SCMP, G_UCMP})
      .lower();
  getActionDefinitionsBuilder(G_FRAME_INDEX)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_p0); });
  getActionDefinitionsBuilder({G_MEMCPY, G_MEMMOVE, G_MEMSET})
      .libcall();
  getActionDefinitionsBuilder({G_MEMCPY_INLINE, G_MEMSET_INLINE})
      .lower();
  getActionDefinitionsBuilder({G_DYN_STACKALLOC, G_STACKSAVE, G_STACKRESTORE})
      .lower();
  getActionDefinitionsBuilder({G_READCYCLECOUNTER, G_READSTEADYCOUNTER})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_is64Bit) && ((Query.Types[0] == R_s64)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (!(R_is64Bit)) && ((Query.Types[0] == R_s64)); });
  getActionDefinitionsBuilder({G_FADD, G_FSUB, G_FMUL, G_FDIV, G_FMA, G_FSQRT, G_FMAXNUM, G_FMINNUM, G_FMAXIMUMNUM, G_FMINIMUMNUM})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && ((Query.Types[0] == R_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && ((Query.Types[0] == R_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && ((Query.Types[0] == R_s16)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_s32 || Query.Types[0] == R_s64); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && ((Query.Types[0] == R_s128)); });
  getActionDefinitionsBuilder({G_FNEG, G_FABS})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && ((Query.Types[0] == R_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && ((Query.Types[0] == R_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && ((Query.Types[0] == R_s16)); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_s32 || Query.Types[0] == R_s64 || Query.Types[0] == R_s128); });
  getActionDefinitionsBuilder(G_FREM)
      .coreLibcallIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_s32 || Query.Types[0] == R_s64); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && ((Query.Types[0] == R_s128)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_s32)
      .scalarize(0);
  getActionDefinitionsBuilder(G_FCOPYSIGN)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && (LegalityPredicates::typePairInSet(0, 1, {{R_s64, R_s64}, {R_s32, R_s64}, {R_s64, R_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && (LegalityPredicates::typePairInSet(0, 1, {{R_s16, R_s16}, {R_s16, R_s32}, {R_s32, R_s16}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasStdExtZfh) && (R_hasStdExtD)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s16, R_s64}, {R_s64, R_s16}})(Query)); })
      .lower();
  getActionDefinitionsBuilder(G_FPTRUNC)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfhmin) && (LegalityPredicates::typePairInSet(0, 1, {{R_s16, R_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasStdExtZfhmin) && (R_hasStdExtD)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s16, R_s64}})(Query)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_s16, R_s32}, {R_s16, R_s64}, {R_s32, R_s64}})(Query); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s128}, {R_s64, R_s128}})(Query)); });
  getActionDefinitionsBuilder(G_FPEXT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && (LegalityPredicates::typePairInSet(0, 1, {{R_s64, R_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfhmin) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s16}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasStdExtZfhmin) && (R_hasStdExtD)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s64, R_s16}})(Query)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (!(R_hasStdExtZfhmin)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s16}})(Query)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (!((R_hasStdExtZfhmin) && (R_hasStdExtD))) && (LegalityPredicates::typePairInSet(0, 1, {{R_s64, R_s16}})(Query)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_s64, R_s32}})(Query); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{R_s128, R_s32}, {R_s128, R_s64}})(Query)); });
  getActionDefinitionsBuilder(G_FCMP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s16}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_s32)
      .coreLibcallIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s32}, {R_sXLen, R_s64}})(Query); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s128}})(Query)); });
  getActionDefinitionsBuilder(G_IS_FPCLASS)
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && (LegalityPredicates::typePairInSet(0, 1, {{R_s1, R_s32}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && (LegalityPredicates::typePairInSet(0, 1, {{R_s1, R_s64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && (LegalityPredicates::typePairInSet(0, 1, {{R_s1, R_s16}})(Query)); })
      .lower();
  getActionDefinitionsBuilder(G_FCONSTANT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && ((Query.Types[0] == R_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && ((Query.Types[0] == R_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfhmin) && ((Query.Types[0] == R_s16)); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_s32 || Query.Types[0] == R_s64 || Query.Types[0] == R_s128); });
  getActionDefinitionsBuilder({G_FPTOSI, G_FPTOUI})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s16}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtF)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtD)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtZfh)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s16}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_s32)
      .coreWidenTo([=](const LegalityQuery &Query) { return ((Query.Types[1] == R_f16)) && (!(R_hasStdExtZfh)) && ((R_is64Bit) || ((Query.Types[0] == R_s32))); }, 1, [=](const LegalityQuery &Query) { return std::make_pair(1, R_s32); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (!(R_hasStdExtZfhmin)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s64, R_f16}})(Query)); })
      .coreNarrowTo([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_s64, R_f16}})(Query); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, R_s32); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}, {R_s64, R_s32}, {R_s32, R_s64}, {R_s64, R_s64}})(Query); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s128}, {R_s64, R_s128}})(Query)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{R_s128, R_s32}, {R_s128, R_s64}, {R_s128, R_s128}})(Query)); });
  getActionDefinitionsBuilder({G_FPTOSI_SAT, G_FPTOUI_SAT})
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s32}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s16}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtF)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtD)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtZfh)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s16}})(Query)); })
      .coreWidenTo([=](const LegalityQuery &Query) { return (Query.Types[1] == R_s16); }, 1, [=](const LegalityQuery &Query) { return std::make_pair(1, R_s32); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (Query.Types[0].isScalar()) && (Query.Types[1].isScalar()); });
  getActionDefinitionsBuilder({G_LROUND, G_LLROUND})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s16}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtF)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtD)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_is64Bit) && (R_hasStdExtZfh)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s16}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_s32)
      .coreLibcallIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}, {R_s64, R_s32}, {R_s32, R_s64}, {R_s64, R_s64}, {R_s32, R_s128}, {R_s64, R_s128}})(Query); });
  getActionDefinitionsBuilder({G_INTRINSIC_LRINT, G_INTRINSIC_LLRINT})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_s16}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_s32)
      .coreLibcallIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}, {R_s64, R_s32}, {R_s32, R_s64}, {R_s64, R_s64}, {R_s32, R_s128}, {R_s64, R_s128}})(Query); });
  getActionDefinitionsBuilder({G_SITOFP, G_UITOFP})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_sXLen}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && (LegalityPredicates::typePairInSet(0, 1, {{R_s64, R_sXLen}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && (LegalityPredicates::typePairInSet(0, 1, {{R_s16, R_sXLen}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1)
      .coreWidenTo([=](const LegalityQuery &Query) { return (Query.Types[0].isScalar()) && (Query.Types[1].isScalar()) && (((Query.Types[1]).getSizeInBits().getKnownMinValue() < (R_XLen_64 ? 64 : 32))) && (((R_hasStdExtF) && (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 32))) || ((R_hasStdExtD) && (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 64))) || ((R_hasStdExtZfh) && (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 16)))); }, 1, [=](const LegalityQuery &Query) { return std::make_pair(1, R_sXLen); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_s32)
      .coreLibcallIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}, {R_s64, R_s32}, {R_s32, R_s64}, {R_s64, R_s64}})(Query); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{R_s128, R_s32}, {R_s128, R_s64}})(Query)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s128}, {R_s64, R_s128}, {R_s128, R_s128}})(Query)); });
  getActionDefinitionsBuilder({G_FCEIL, G_FFLOOR, G_FRINT, G_FNEARBYINT, G_INTRINSIC_TRUNC, G_INTRINSIC_ROUND, G_INTRINSIC_ROUNDEVEN})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfa) && ((Query.Types[0] == R_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasStdExtZfa) && (R_hasStdExtD)) && ((Query.Types[0] == R_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasStdExtZfa) && (R_hasStdExtZfh)) && ((Query.Types[0] == R_s16)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_s32 || Query.Types[0] == R_s64); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && ((Query.Types[0] == R_s128)); });
  getActionDefinitionsBuilder({G_FMAXIMUM, G_FMINIMUM})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfa) && ((Query.Types[0] == R_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasStdExtZfa) && (R_hasStdExtD)) && ((Query.Types[0] == R_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_hasStdExtZfa) && (R_hasStdExtZfh)) && ((Query.Types[0] == R_s16)); });
  getActionDefinitionsBuilder({G_FCOS, G_FSIN, G_FTAN, G_FPOW, G_FLOG, G_FLOG2, G_FLOG10, G_FEXP, G_FEXP2, G_FEXP10, G_FACOS, G_FASIN, G_FATAN, G_FATAN2, G_FCOSH, G_FSINH, G_FTANH, G_FMODF, G_FSINCOS})
      .coreLibcallIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_s32 || Query.Types[0] == R_s64); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && ((Query.Types[0] == R_s128)); });
  getActionDefinitionsBuilder({G_FPOWI, G_FLDEXP})
      .coreLibcallIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_s32, R_s32}, {R_s64, R_s32}})(Query); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (R_is64Bit) && ((Query.Types[0] == R_s128 || Query.Types[0] == R_s32)); });
  getActionDefinitionsBuilder(G_FCANONICALIZE)
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtF) && ((Query.Types[0] == R_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtD) && ((Query.Types[0] == R_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtZfh) && ((Query.Types[0] == R_s16)); });
  getActionDefinitionsBuilder(G_VASTART)
      .coreCustomIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_p0); });
  getActionDefinitionsBuilder(G_VAARG)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreLowerIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_p0}, {R_p0, R_p0}})(Query); });
  getActionDefinitionsBuilder(G_VSCALE)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreCustomIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_sXLen); });
  getActionDefinitionsBuilder(G_SPLAT_VECTOR)
      .coreLegalIf([=](const LegalityQuery &Query) { return (((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && ((Query.Types[1] == R_sXLen)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (((Query.Types[0] == R_nxv1s1 || Query.Types[0] == R_nxv2s1 || Query.Types[0] == R_nxv4s1 || Query.Types[0] == R_nxv8s1 || Query.Types[0] == R_nxv16s1 || Query.Types[0] == R_nxv32s1 || Query.Types[0] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && ((Query.Types[1] == R_s1)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((R_XLen_32) && ((R_hasVInstructionsF64) && (R_hasStdExtD))) && (((Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((Query.Types[1] == R_s64))); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((R_XLen_32) && (!((R_hasVInstructionsF64) && (R_hasStdExtD))) && (R_hasVInstructionsI64)) && (((Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((Query.Types[1] == R_s64))); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, R_sXLen);
  getActionDefinitionsBuilder(G_EXTRACT_SUBVECTOR)
      .coreBitcastToType([=](const LegalityQuery &Query) { return (((Query.Types[0] == R_nxv1s1 || Query.Types[0] == R_nxv2s1 || Query.Types[0] == R_nxv4s1 || Query.Types[0] == R_nxv8s1 || Query.Types[0] == R_nxv16s1 || Query.Types[0] == R_nxv32s1 || Query.Types[0] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && (((Query.Types[1] == R_nxv1s1 || Query.Types[1] == R_nxv2s1 || Query.Types[1] == R_nxv4s1 || Query.Types[1] == R_nxv8s1 || Query.Types[1] == R_nxv16s1 || Query.Types[1] == R_nxv32s1 || Query.Types[1] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64)))) && ((((Query.Types[0]).getElementType() == R_s1)) && (((Query.Types[0]).getNumElements() >= 8)) && (((Query.Types[1]).getNumElements() >= 8))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, ((Query.Types[0]).changeElementCount((Query.Types[0]).getElementCount().divideCoefficientBy(8))).changeElementType(R_s8)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return ((((Query.Types[0] == R_nxv1s1 || Query.Types[0] == R_nxv2s1 || Query.Types[0] == R_nxv4s1 || Query.Types[0] == R_nxv8s1 || Query.Types[0] == R_nxv16s1 || Query.Types[0] == R_nxv32s1 || Query.Types[0] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && (((Query.Types[1] == R_nxv1s1 || Query.Types[1] == R_nxv2s1 || Query.Types[1] == R_nxv4s1 || Query.Types[1] == R_nxv8s1 || Query.Types[1] == R_nxv16s1 || Query.Types[1] == R_nxv32s1 || Query.Types[1] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64))))) || ((((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && (((Query.Types[1] == R_nxv1s8 || Query.Types[1] == R_nxv2s8 || Query.Types[1] == R_nxv4s8 || Query.Types[1] == R_nxv8s8 || Query.Types[1] == R_nxv16s8 || Query.Types[1] == R_nxv32s8 || Query.Types[1] == R_nxv64s8 || Query.Types[1] == R_nxv1s16 || Query.Types[1] == R_nxv2s16 || Query.Types[1] == R_nxv4s16 || Query.Types[1] == R_nxv8s16 || Query.Types[1] == R_nxv16s16 || Query.Types[1] == R_nxv32s16 || Query.Types[1] == R_nxv1s32 || Query.Types[1] == R_nxv2s32 || Query.Types[1] == R_nxv4s32 || Query.Types[1] == R_nxv8s32 || Query.Types[1] == R_nxv16s32 || Query.Types[1] == R_nxv1s64 || Query.Types[1] == R_nxv2s64 || Query.Types[1] == R_nxv4s64 || Query.Types[1] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[1]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64))))); });
  getActionDefinitionsBuilder(G_INSERT_SUBVECTOR)
      .coreCustomIf([=](const LegalityQuery &Query) { return (((Query.Types[0] == R_nxv1s1 || Query.Types[0] == R_nxv2s1 || Query.Types[0] == R_nxv4s1 || Query.Types[0] == R_nxv8s1 || Query.Types[0] == R_nxv16s1 || Query.Types[0] == R_nxv32s1 || Query.Types[0] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && (((Query.Types[1] == R_nxv1s1 || Query.Types[1] == R_nxv2s1 || Query.Types[1] == R_nxv4s1 || Query.Types[1] == R_nxv8s1 || Query.Types[1] == R_nxv16s1 || Query.Types[1] == R_nxv32s1 || Query.Types[1] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64)))); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && (((Query.Types[1] == R_nxv1s8 || Query.Types[1] == R_nxv2s8 || Query.Types[1] == R_nxv4s8 || Query.Types[1] == R_nxv8s8 || Query.Types[1] == R_nxv16s8 || Query.Types[1] == R_nxv32s8 || Query.Types[1] == R_nxv64s8 || Query.Types[1] == R_nxv1s16 || Query.Types[1] == R_nxv2s16 || Query.Types[1] == R_nxv4s16 || Query.Types[1] == R_nxv8s16 || Query.Types[1] == R_nxv16s16 || Query.Types[1] == R_nxv32s16 || Query.Types[1] == R_nxv1s32 || Query.Types[1] == R_nxv2s32 || Query.Types[1] == R_nxv4s32 || Query.Types[1] == R_nxv8s32 || Query.Types[1] == R_nxv16s32 || Query.Types[1] == R_nxv1s64 || Query.Types[1] == R_nxv2s64 || Query.Types[1] == R_nxv4s64 || Query.Types[1] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[1]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[1]).getNumElements() != 1)) || (R_getELen_64)))); });
  getActionDefinitionsBuilder(G_ATOMIC_CMPXCHG_WITH_SUCCESS)
      .coreLowerIf([=](const LegalityQuery &Query) { return ((Query.Types[0] == R_s8 || Query.Types[0] == R_s16 || Query.Types[0] == R_s32 || Query.Types[0] == R_s64)) && ((Query.Types[2] == R_p0)); });
  getActionDefinitionsBuilder({G_ATOMIC_CMPXCHG, G_ATOMICRMW_ADD, G_ATOMICRMW_XCHG, G_ATOMICRMW_AND, G_ATOMICRMW_OR, G_ATOMICRMW_XOR})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtA) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_p0}})(Query)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (!(R_hasStdExtA)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s8, R_p0}, {R_s16, R_p0}, {R_s32, R_p0}, {R_s64, R_p0}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen);
  getActionDefinitionsBuilder(G_ATOMICRMW_SUB)
      .coreLibcallIf([=](const LegalityQuery &Query) { return (!(R_hasStdExtA)) && (LegalityPredicates::typePairInSet(0, 1, {{R_s8, R_p0}, {R_s16, R_p0}, {R_s32, R_p0}, {R_s64, R_p0}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .lower();
  getActionDefinitionsBuilder({G_ATOMICRMW_MAX, G_ATOMICRMW_MIN, G_ATOMICRMW_UMAX, G_ATOMICRMW_UMIN})
      .coreLegalIf([=](const LegalityQuery &Query) { return (R_hasStdExtA) && (LegalityPredicates::typePairInSet(0, 1, {{R_sXLen, R_p0}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, R_sXLen)
      .unsupported();
  getActionDefinitionsBuilder(G_PREFETCH)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == R_p0); });
  getActionDefinitionsBuilder(G_INSERT_VECTOR_ELT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (((Query.Types[0] == R_nxv1s8 || Query.Types[0] == R_nxv2s8 || Query.Types[0] == R_nxv4s8 || Query.Types[0] == R_nxv8s8 || Query.Types[0] == R_nxv16s8 || Query.Types[0] == R_nxv32s8 || Query.Types[0] == R_nxv64s8 || Query.Types[0] == R_nxv1s16 || Query.Types[0] == R_nxv2s16 || Query.Types[0] == R_nxv4s16 || Query.Types[0] == R_nxv8s16 || Query.Types[0] == R_nxv16s16 || Query.Types[0] == R_nxv32s16 || Query.Types[0] == R_nxv1s32 || Query.Types[0] == R_nxv2s32 || Query.Types[0] == R_nxv4s32 || Query.Types[0] == R_nxv8s32 || Query.Types[0] == R_nxv16s32 || Query.Types[0] == R_nxv1s64 || Query.Types[0] == R_nxv2s64 || Query.Types[0] == R_nxv4s64 || Query.Types[0] == R_nxv8s64)) && ((R_hasVInstructions) && ((((Query.Types[0]).getScalarSizeInBits() != 64)) || (R_hasVInstructionsI64)) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && (((Query.Types[0]).getElementType() == Query.Types[1])) && ((Query.Types[2] == R_sXLen)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (((Query.Types[0] == R_nxv1s1 || Query.Types[0] == R_nxv2s1 || Query.Types[0] == R_nxv4s1 || Query.Types[0] == R_nxv8s1 || Query.Types[0] == R_nxv16s1 || Query.Types[0] == R_nxv32s1 || Query.Types[0] == R_nxv64s1)) && ((R_hasVInstructions) && ((((Query.Types[0]).getNumElements() != 1)) || (R_getELen_64)))) && (((Query.Types[0]).getElementType() == Query.Types[1])) && ((Query.Types[2] == R_sXLen)); });
  getActionDefinitionsBuilder({G_INTRINSIC, G_INTRINSIC_W_SIDE_EFFECTS})
      .alwaysLegal();
  getActionDefinitionsBuilder(G_FENCE)
      .alwaysLegal();
  getActionDefinitionsBuilder({G_TRAP, G_DEBUGTRAP, G_UBSANTRAP})
      .alwaysLegal();
