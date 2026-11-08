/*===- TableGen'erated file -------------------------------------*- C++ -*-===*\
|*                                                                            *|
|* GlobalISel legalizer rule fragments                                        *|
|*                                                                            *|
|* Automatically generated file, do not edit!                                 *|
|*                                                                            *|
\*===----------------------------------------------------------------------===*/

  bool Is64Bit = Subtarget.is64Bit();
  bool HasCMOV = Subtarget.canUseCMOV();
  bool HasSSE1 = Subtarget.hasSSE1();
  bool HasSSE2 = Subtarget.hasSSE2();
  bool HasSSE41 = Subtarget.hasSSE41();
  bool HasAVX = Subtarget.hasAVX();
  bool HasAVX2 = Subtarget.hasAVX2();
  bool HasAVX512 = Subtarget.hasAVX512();
  bool HasVLX = Subtarget.hasVLX();
  bool HasDQI = Subtarget.hasAVX512() && Subtarget.hasDQI();
  bool HasBWI = Subtarget.hasAVX512() && Subtarget.hasBWI();
  bool UseX87 = !Subtarget.useSoftFloat() && Subtarget.hasX87();
  bool HasPOPCNT = Subtarget.hasPOPCNT();
  bool HasVPOPCNTDQ = Subtarget.hasVPOPCNTDQ();
  bool HasLZCNT = Subtarget.hasLZCNT();
  bool HasBMI = Subtarget.hasBMI();

  const LLT X86_p0 = LLT::pointer(0, Subtarget.isTarget64BitLP64() ? 64 : 32);
  const LLT X86_s1 = LLT::scalar(1);
  const LLT X86_s8 = LLT::scalar(8);
  const LLT X86_s16 = LLT::scalar(16);
  const LLT X86_s32 = LLT::scalar(32);
  const LLT X86_s64 = LLT::scalar(64);
  const LLT X86_s80 = LLT::scalar(80);
  const LLT X86_s128 = LLT::scalar(128);
  const LLT X86_sMaxScalar = (Is64Bit ? X86_s64 : X86_s32);
  const LLT X86_v2s32 = LLT::fixed_vector(2, 32);
  const LLT X86_v4s8 = LLT::fixed_vector(4, 8);
  const LLT X86_v16s8 = LLT::fixed_vector(16, 8);
  const LLT X86_v8s16 = LLT::fixed_vector(8, 16);
  const LLT X86_v4s32 = LLT::fixed_vector(4, 32);
  const LLT X86_v2s64 = LLT::fixed_vector(2, 64);
  const LLT X86_v2p0 = LLT::fixed_vector(2, X86_p0);
  const LLT X86_v32s8 = LLT::fixed_vector(32, 8);
  const LLT X86_v16s16 = LLT::fixed_vector(16, 16);
  const LLT X86_v8s32 = LLT::fixed_vector(8, 32);
  const LLT X86_v4s64 = LLT::fixed_vector(4, 64);
  const LLT X86_v4p0 = LLT::fixed_vector(4, X86_p0);
  const LLT X86_v64s8 = LLT::fixed_vector(64, 8);
  const LLT X86_v32s16 = LLT::fixed_vector(32, 16);
  const LLT X86_v16s32 = LLT::fixed_vector(16, 32);
  const LLT X86_v8s64 = LLT::fixed_vector(8, 64);
  const LLT X86_s8MaxVector = (HasAVX512 ? X86_v64s8 : (HasAVX ? X86_v32s8 : X86_v16s8));
  const LLT X86_s16MaxVector = (HasAVX512 ? X86_v32s16 : (HasAVX ? X86_v16s16 : X86_v8s16));
  const LLT X86_s32MaxVector = (HasAVX512 ? X86_v16s32 : (HasAVX ? X86_v8s32 : X86_v4s32));
  const LLT X86_s64MaxVector = (HasAVX512 ? X86_v8s64 : (HasAVX ? X86_v4s64 : X86_v2s64));
  const LLT X86_s64OrS32 = (HasSSE2 ? X86_s64 : X86_s32);
  const LLT X86_X87OrS32 = (UseX87 && !(HasSSE1) ? X86_s16 : X86_s32);
  const LLT X86_CMOVOrS8 = (HasCMOV ? X86_s16 : X86_s8);

  // implicit/constants
  // 32/64-bits needs support for s64/s128 to handle cases:
  // s64 = EXTEND (G_IMPLICIT_DEF s32) -> s64 = G_IMPLICIT_DEF
  // s128 = EXTEND (G_IMPLICIT_DEF s32/s64) -> s128 = G_IMPLICIT_DEF
  getActionDefinitionsBuilder({G_IMPLICIT_DEF, G_PHI, G_FREEZE, G_CONSTANT_FOLD_BARRIER})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_p0 || Query.Types[0] == X86_s1 || Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32 || Query.Types[0] == X86_s64); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && ((Query.Types[0] == X86_s80)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s128)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && ((Query.Types[0] == X86_v16s8 || Query.Types[0] == X86_v8s16 || Query.Types[0] == X86_v4s32 || Query.Types[0] == X86_v2s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX) && ((Query.Types[0] == X86_v32s8 || Query.Types[0] == X86_v16s16 || Query.Types[0] == X86_v8s32 || Query.Types[0] == X86_v4s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && ((Query.Types[0] == X86_v64s8 || Query.Types[0] == X86_v32s16 || Query.Types[0] == X86_v16s32 || Query.Types[0] == X86_v8s64)); })
      .coreWidenScalarOrEltToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalarOrElt([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalarOrElt([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .coreMoreElementsToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s8)) && (((Query.Types[0]).getNumElements() < (X86_v16s8).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X86_v16s8).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s8)) && (((Query.Types[0]).getNumElements() > (X86_s8MaxVector).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X86_s8MaxVector).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s16)) && (((Query.Types[0]).getNumElements() < (X86_v8s16).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X86_v8s16).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s16)) && (((Query.Types[0]).getNumElements() > (X86_s16MaxVector).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X86_s16MaxVector).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s32)) && (((Query.Types[0]).getNumElements() < (X86_v4s32).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X86_v4s32).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s32)) && (((Query.Types[0]).getNumElements() > (X86_s32MaxVector).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X86_s32MaxVector).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s64)) && (((Query.Types[0]).getNumElements() < (X86_v2s64).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X86_v2s64).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s64)) && (((Query.Types[0]).getNumElements() > (X86_s64MaxVector).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X86_s64MaxVector).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_p0)) && (((Query.Types[0]).getNumElements() > ((Is64Bit) && (HasAVX512) ? 8 : ((Is64Bit) && (HasAVX) ? 4 : (Is64Bit ? 2 : (HasAVX512 ? 16 : (HasAVX ? 8 : 4))))))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed(((Is64Bit) && (HasAVX512) ? 8 : ((Is64Bit) && (HasAVX) ? 4 : (Is64Bit ? 2 : (HasAVX512 ? 16 : (HasAVX ? 8 : 4)))))), (Query.Types[0]).getElementType())); })
      .coreScalarizeIf([=](const LegalityQuery &Query) { return ((Query.Types[0]).getScalarSizeInBits() > 64); }, 0);
  getActionDefinitionsBuilder(G_CONSTANT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_p0 || Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar);
  getActionDefinitionsBuilder({G_LROUND, G_LLROUND})
      .coreMinScalar([=](const LegalityQuery &Query) { return (Query.Types[1] == X86_s16); }, 1, X86_s32)
      .libcall();
  getActionDefinitionsBuilder({G_FCOS, G_FCOSH, G_FACOS, G_FSIN, G_FSINH, G_FASIN, G_FTAN, G_FTANH, G_FATAN, G_FATAN2, G_FPOW, G_FEXP, G_FEXP2, G_FEXP10, G_FLOG, G_FLOG2, G_FLOG10, G_FPOWI, G_FSINCOS, G_FCEIL, G_FFLOOR})
      .libcall();
  getActionDefinitionsBuilder(G_FNEG)
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && (!(HasSSE1)) && ((Query.Types[0] == X86_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && (!(HasSSE2)) && ((Query.Types[0] == X86_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && ((Query.Types[0] == X86_s80)); })
      .lower();
  getActionDefinitionsBuilder(G_FSQRT)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((HasSSE1) || (UseX87)) && ((Query.Types[0] == X86_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((HasSSE2) || (UseX87)) && ((Query.Types[0] == X86_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && ((Query.Types[0] == X86_s80)); });
  getActionDefinitionsBuilder({G_GET_ROUNDING, G_SET_ROUNDING})
      .coreCustomIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s32); });
  getActionDefinitionsBuilder(G_MERGE_VALUES)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 8)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s32)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((((Query.Types[0]).getSizeInBits().getKnownMinValue() == 16)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 32)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 64)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 128)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 256)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 512))) && ((((Query.Types[1]).getSizeInBits().getKnownMinValue() == 8)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 16)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 32)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 64)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 128)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 256))); });
  getActionDefinitionsBuilder(G_UNMERGE_VALUES)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s32)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((((Query.Types[1]).getSizeInBits().getKnownMinValue() == 16)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 32)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 64)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 128)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 256)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 512))) && ((((Query.Types[0]).getSizeInBits().getKnownMinValue() == 8)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 16)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 32)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 64)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 128)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 256))); });
  getActionDefinitionsBuilder({G_UMIN, G_UMAX, G_SMIN, G_SMAX})
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .lower();
  // integer addition/subtraction
  getActionDefinitionsBuilder({G_ADD, G_SUB})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && ((Query.Types[0] == X86_v16s8 || Query.Types[0] == X86_v8s16 || Query.Types[0] == X86_v4s32 || Query.Types[0] == X86_v2s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX2) && ((Query.Types[0] == X86_v32s8 || Query.Types[0] == X86_v16s16 || Query.Types[0] == X86_v8s32 || Query.Types[0] == X86_v4s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && ((Query.Types[0] == X86_v16s32 || Query.Types[0] == X86_v8s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasBWI) && ((Query.Types[0] == X86_v64s8 || Query.Types[0] == X86_v32s16)); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s8)) && (((Query.Types[0]).getNumElements() < 16)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(16, (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s16)) && (((Query.Types[0]).getNumElements() < 8)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(8, (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s32)) && (((Query.Types[0]).getNumElements() < 4)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(4, (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s64)) && (((Query.Types[0]).getNumElements() < 2)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(2, (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s8)) && (((Query.Types[0]).getNumElements() > (HasBWI ? 64 : (HasAVX2 ? 32 : 16)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((HasBWI ? 64 : (HasAVX2 ? 32 : 16))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s16)) && (((Query.Types[0]).getNumElements() > (HasBWI ? 32 : (HasAVX2 ? 16 : 8)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((HasBWI ? 32 : (HasAVX2 ? 16 : 8))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s32)) && (((Query.Types[0]).getNumElements() > (HasAVX512 ? 16 : (HasAVX2 ? 8 : 4)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((HasAVX512 ? 16 : (HasAVX2 ? 8 : 4))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s64)) && (((Query.Types[0]).getNumElements() > (HasAVX512 ? 8 : (HasAVX2 ? 4 : 2)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((HasAVX512 ? 8 : (HasAVX2 ? 4 : 2))), (Query.Types[0]).getElementType())); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .scalarize(0);
  getActionDefinitionsBuilder({G_UADDE, G_UADDO, G_USUBE, G_USUBO})
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X86_s8, X86_s8}, {X86_s16, X86_s8}, {X86_s32, X86_s8}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s8}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_s8)
      .scalarize(0);
  // integer multiply
  getActionDefinitionsBuilder(G_MUL)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && ((Query.Types[0] == X86_v8s16)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE41) && ((Query.Types[0] == X86_v4s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX2) && ((Query.Types[0] == X86_v16s16 || Query.Types[0] == X86_v8s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && ((Query.Types[0] == X86_v16s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasDQI) && ((Query.Types[0] == X86_v8s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasDQI) && (HasVLX) && ((Query.Types[0] == X86_v2s64 || Query.Types[0] == X86_v4s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasBWI) && ((Query.Types[0] == X86_v32s16)); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s16)) && (((Query.Types[0]).getNumElements() < 8)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(8, (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s32)) && (((Query.Types[0]).getNumElements() < 4)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(4, (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s64)) && (((Query.Types[0]).getNumElements() < (HasVLX ? 2 : 8))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((HasVLX ? 2 : 8), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s16)) && (((Query.Types[0]).getNumElements() > (HasBWI ? 32 : (HasAVX2 ? 16 : 8)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((HasBWI ? 32 : (HasAVX2 ? 16 : 8))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s32)) && (((Query.Types[0]).getNumElements() > (HasAVX512 ? 16 : (HasAVX2 ? 8 : 4)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((HasAVX512 ? 16 : (HasAVX2 ? 8 : 4))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s64)) && (((Query.Types[0]).getNumElements() > 8)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed(8), (Query.Types[0]).getElementType())); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .scalarize(0);
  getActionDefinitionsBuilder({G_SMULH, G_UMULH})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .scalarize(0);
  // integer divisions
  getActionDefinitionsBuilder({G_SDIV, G_SREM, G_UDIV, G_UREM})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s64)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s64); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar);
  // integer shifts
  getActionDefinitionsBuilder({G_SHL, G_LSHR, G_ASHR})
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X86_s8, X86_s8}, {X86_s16, X86_s8}, {X86_s32, X86_s8}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s8}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_s8);
  // integer logic
  getActionDefinitionsBuilder({G_AND, G_OR, G_XOR})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && ((Query.Types[0] == X86_v16s8 || Query.Types[0] == X86_v8s16 || Query.Types[0] == X86_v4s32 || Query.Types[0] == X86_v2s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX) && ((Query.Types[0] == X86_v32s8 || Query.Types[0] == X86_v16s16 || Query.Types[0] == X86_v8s32 || Query.Types[0] == X86_v4s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && ((Query.Types[0] == X86_v64s8 || Query.Types[0] == X86_v32s16 || Query.Types[0] == X86_v16s32 || Query.Types[0] == X86_v8s64)); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s8)) && (((Query.Types[0]).getNumElements() < (X86_v16s8).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X86_v16s8).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s8)) && (((Query.Types[0]).getNumElements() > (X86_s8MaxVector).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X86_s8MaxVector).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s16)) && (((Query.Types[0]).getNumElements() < (X86_v8s16).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X86_v8s16).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s16)) && (((Query.Types[0]).getNumElements() > (X86_s16MaxVector).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X86_s16MaxVector).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s32)) && (((Query.Types[0]).getNumElements() < (X86_v4s32).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X86_v4s32).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s32)) && (((Query.Types[0]).getNumElements() > (X86_s32MaxVector).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X86_s32MaxVector).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s64)) && (((Query.Types[0]).getNumElements() < (X86_v2s64).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X86_v2s64).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s64)) && (((Query.Types[0]).getNumElements() > (X86_s64MaxVector).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X86_s64MaxVector).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .scalarize(0);
  getActionDefinitionsBuilder(G_ICMP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s8)) && ((Query.Types[1] == X86_s8 || Query.Types[1] == X86_s16 || Query.Types[1] == X86_s32 || Query.Types[1] == X86_s64 || Query.Types[1] == X86_p0)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(Is64Bit)) && ((Query.Types[0] == X86_s8)) && ((Query.Types[1] == X86_s8 || Query.Types[1] == X86_s16 || Query.Types[1] == X86_s32 || Query.Types[1] == X86_p0)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_sMaxScalar);
  // bswap
  getActionDefinitionsBuilder(G_BSWAP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar);
  // popcount
  getActionDefinitionsBuilder(G_CTPOP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasPOPCNT) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s16, X86_s16}, {X86_s32, X86_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasPOPCNT) && (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasVPOPCNTDQ) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v16s32, X86_v16s32}, {X86_v8s64, X86_v8s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasVPOPCNTDQ) && (HasVLX) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v4s32, X86_v4s32}, {X86_v8s32, X86_v8s32}, {X86_v2s64, X86_v2s64}, {X86_v4s64, X86_v4s64}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_sMaxScalar)
      .coreMinScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1)
      .coreMaxScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1);
  // count leading zeros (LZCNT)
  getActionDefinitionsBuilder(G_CTLZ)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasLZCNT) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s16, X86_s16}, {X86_s32, X86_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasLZCNT) && (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s64}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_sMaxScalar)
      .coreMinScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1)
      .coreMaxScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1);
  // count trailing zeros
  getActionDefinitionsBuilder(G_CTTZ_ZERO_POISON)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X86_s16, X86_s16}, {X86_s32, X86_s32}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s64}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_sMaxScalar)
      .coreMinScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1)
      .coreMaxScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1);
  getActionDefinitionsBuilder(G_CTTZ)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasBMI) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s16, X86_s16}, {X86_s32, X86_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasBMI) && (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s64}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_sMaxScalar)
      .coreMinScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1)
      .coreMaxScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1);
  getActionDefinitionsBuilder(G_BR)
      .alwaysLegal();
  getActionDefinitionsBuilder(G_BRCOND)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s1); });
  getActionDefinitionsBuilder(G_PTRTOINT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s1 || Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32 || Query.Types[0] == X86_s64)) && ((Query.Types[1] == X86_p0)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(Is64Bit)) && ((Query.Types[0] == X86_s1 || Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32)) && ((Query.Types[1] == X86_p0)); })
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8);
  getActionDefinitionsBuilder(G_INTTOPTR)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X86_p0, X86_sMaxScalar}})(Query); });
  getActionDefinitionsBuilder(G_CONSTANT_POOL)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_p0); });
  getActionDefinitionsBuilder(G_PTR_ADD)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X86_p0, X86_s32}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_p0, X86_s64}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_sMaxScalar);
  getActionDefinitionsBuilder(G_FRAME_INDEX)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_p0); });
  getActionDefinitionsBuilder(G_GLOBAL_VALUE)
      .coreCustomIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_p0); });
  // load/store: add more corner cases
  getActionDefinitionsBuilder(G_LOAD)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s8, X86_p0, X86_s8, 1}, {X86_s16, X86_p0, X86_s16, 1}, {X86_s32, X86_p0, X86_s32, 1}, {X86_s80, X86_p0, X86_s80, 1}, {X86_p0, X86_p0, X86_p0, 1}, {X86_v4s8, X86_p0, X86_v4s8, 1}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s64, X86_p0, X86_s64, 1}, {X86_v2s32, X86_p0, X86_v2s32, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE1) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_v4s32, X86_p0, X86_v4s32, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_v16s8, X86_p0, X86_v16s8, 1}, {X86_v8s16, X86_p0, X86_v8s16, 1}, {X86_v2s64, X86_p0, X86_v2s64, 1}, {X86_v2p0, X86_p0, X86_v2p0, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_v32s8, X86_p0, X86_v32s8, 1}, {X86_v16s16, X86_p0, X86_v16s16, 1}, {X86_v8s32, X86_p0, X86_v8s32, 1}, {X86_v4s64, X86_p0, X86_v4s64, 1}, {X86_v4p0, X86_p0, X86_v4p0, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_v64s8, X86_p0, X86_v64s8, 1}, {X86_v32s16, X86_p0, X86_v32s16, 1}, {X86_v16s32, X86_p0, X86_v16s32, 1}, {X86_v8s64, X86_p0, X86_v8s64, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s8, X86_p0, X86_s1, 1}, {X86_s16, X86_p0, X86_s8, 1}, {X86_s32, X86_p0, X86_s8, 1}, {X86_s32, X86_p0, X86_s16, 1}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s64, X86_p0, X86_s8, 1}, {X86_s64, X86_p0, X86_s16, 1}, {X86_s64, X86_p0, X86_s32, 1}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .scalarize(0);
  getActionDefinitionsBuilder(G_STORE)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s8, X86_p0, X86_s8, 1}, {X86_s16, X86_p0, X86_s16, 1}, {X86_s32, X86_p0, X86_s32, 1}, {X86_s80, X86_p0, X86_s80, 1}, {X86_p0, X86_p0, X86_p0, 1}, {X86_v4s8, X86_p0, X86_v4s8, 1}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s64, X86_p0, X86_s64, 1}, {X86_v2s32, X86_p0, X86_v2s32, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE1) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_v4s32, X86_p0, X86_v4s32, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_v16s8, X86_p0, X86_v16s8, 1}, {X86_v8s16, X86_p0, X86_v8s16, 1}, {X86_v2s64, X86_p0, X86_v2s64, 1}, {X86_v2p0, X86_p0, X86_v2p0, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_v32s8, X86_p0, X86_v32s8, 1}, {X86_v16s16, X86_p0, X86_v16s16, 1}, {X86_v8s32, X86_p0, X86_v8s32, 1}, {X86_v4s64, X86_p0, X86_v4s64, 1}, {X86_v4p0, X86_p0, X86_v4p0, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_v64s8, X86_p0, X86_v64s8, 1}, {X86_v32s16, X86_p0, X86_v32s16, 1}, {X86_v16s32, X86_p0, X86_v16s32, 1}, {X86_v8s64, X86_p0, X86_v8s64, 1}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (Query.Types[0] != (Query.MMODescrs[0]).MemoryTy); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .scalarize(0);
  getActionDefinitionsBuilder(G_SEXTLOAD)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s16, X86_p0, X86_s8, 1}, {X86_s32, X86_p0, X86_s8, 1}, {X86_s32, X86_p0, X86_s16, 1}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s64, X86_p0, X86_s8, 1}, {X86_s64, X86_p0, X86_s16, 1}, {X86_s64, X86_p0, X86_s32, 1}})(Query)); });
  getActionDefinitionsBuilder(G_ZEXTLOAD)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s16, X86_p0, X86_s8, 1}, {X86_s32, X86_p0, X86_s8, 1}, {X86_s32, X86_p0, X86_s16, 1}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s64, X86_p0, X86_s8, 1}, {X86_s64, X86_p0, X86_s16, 1}, {X86_s64, X86_p0, X86_s32, 1}})(Query)); });
  getActionDefinitionsBuilder(G_FPEXTLOAD)
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s80, X86_p0, X86_s32, 1}, {X86_s80, X86_p0, X86_s64, 1}, {X86_s64, X86_p0, X86_s32, 1}})(Query)); });
  getActionDefinitionsBuilder(G_FPTRUNCSTORE)
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X86_s80, X86_p0, X86_s32, 1}, {X86_s80, X86_p0, X86_s64, 1}, {X86_s64, X86_p0, X86_s32, 1}})(Query)); });
  // sext, zext, and anyext
  getActionDefinitionsBuilder(G_ANYEXT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32 || Query.Types[0] == X86_s128); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_sMaxScalar)
      .scalarize(0);
  getActionDefinitionsBuilder({G_SEXT, G_ZEXT})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == X86_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_sMaxScalar)
      .scalarize(0);
  getActionDefinitionsBuilder(G_TRUNC)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((Query.Types[0] == X86_s1 || Query.Types[0] == X86_s8 || Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32 || Query.Types[0] == X86_s64)) && ((Query.Types[1] == X86_s8 || Query.Types[1] == X86_s16 || Query.Types[1] == X86_s32 || Query.Types[1] == X86_s64 || Query.Types[1] == X86_s128)); });
  getActionDefinitionsBuilder(G_SEXT_INREG)
      .lower();
  // fp constants
  getActionDefinitionsBuilder(G_FCONSTANT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s32 || Query.Types[0] == X86_s64); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && ((Query.Types[0] == X86_s80)); });
  // fp arithmetic
  getActionDefinitionsBuilder({G_FADD, G_FSUB, G_FMUL, G_FDIV})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X86_s32 || Query.Types[0] == X86_s64); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE1) && ((Query.Types[0] == X86_v4s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && ((Query.Types[0] == X86_v2s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX) && ((Query.Types[0] == X86_v8s32 || Query.Types[0] == X86_v4s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && ((Query.Types[0] == X86_v16s32 || Query.Types[0] == X86_v8s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && ((Query.Types[0] == X86_s80)); });
  getActionDefinitionsBuilder(G_FABS)
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && ((Query.Types[0] == X86_s80)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && (!(Is64Bit)) && ((Query.Types[0] == X86_s64)); })
      .lower();
  // fp comparison
  getActionDefinitionsBuilder(G_FCMP)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((HasSSE1) || (UseX87)) && ((Query.Types[0] == X86_s8 || Query.Types[0] == X86_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((HasSSE2) || (UseX87)) && ((Query.Types[0] == X86_s8 || Query.Types[0] == X86_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && ((Query.Types[0] == X86_s8 || Query.Types[0] == X86_s80)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_s8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_s64OrS32)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1);
  // fp conversions
  getActionDefinitionsBuilder(G_FPEXT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v4s64, X86_v4s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v8s64, X86_v8s32}})(Query)); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (UseX87) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s32}, {X86_s80, X86_s32}, {X86_s80, X86_s64}})(Query)); })
      .libcall();
  getActionDefinitionsBuilder(G_FPTRUNC)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s32, X86_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v4s32, X86_v4s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v8s32, X86_v8s64}})(Query)); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (UseX87) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s32, X86_s64}, {X86_s32, X86_s80}, {X86_s64, X86_s80}})(Query)); });
  getActionDefinitionsBuilder(G_SITOFP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE1) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s32, X86_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE1) && (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s32, X86_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s64}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_X87OrS32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_sMaxScalar)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1)
      .coreCustomIf([=](const LegalityQuery &Query) { return (UseX87) && (((Query.Types[0] == X86_s32 || Query.Types[0] == X86_s64 || Query.Types[0] == X86_s80)) && ((Query.Types[1] == X86_s16 || Query.Types[1] == X86_s32 || Query.Types[1] == X86_s64))); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_s64OrS32)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0);
  getActionDefinitionsBuilder(G_FPTOSI)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE1) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s32, X86_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE1) && (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s32, X86_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE2) && (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s64}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_X87OrS32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreCustomIf([=](const LegalityQuery &Query) { return (UseX87) && (((Query.Types[0] == X86_s16 || Query.Types[0] == X86_s32 || Query.Types[0] == X86_s64)) && ((Query.Types[1] == X86_s32 || Query.Types[1] == X86_s64 || Query.Types[1] == X86_s80))); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_s64OrS32)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1);
  // For G_UITOFP and G_FPTOUI without AVX512, we have to custom legalize
  // types
  // <= s32 manually. Otherwise, in custom handler there is no way to
  // understand whether s32 is an original type and we need to promote it to
  // s64 or s32 is obtained after widening and we shouldn't widen it to s64.
  // 
  // For AVX512 we simply widen types as there is direct mapping from opcodes
  // to asm instructions.
  getActionDefinitionsBuilder(G_UITOFP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s32, X86_s32}, {X86_s32, X86_s64}, {X86_s64, X86_s32}, {X86_s64, X86_s64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (!(HasAVX512)) && (((HasSSE1) && ((Query.Types[0] == X86_s32))) || ((HasSSE2) && ((Query.Types[0] == X86_s64)))) && (((Query.Types[1]).getScalarSizeInBits() < (Is64Bit ? 64 : 32))); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (!(HasAVX512)) && (((HasSSE1) && ((Query.Types[0] == X86_s32))) || ((HasSSE2) && ((Query.Types[0] == X86_s64)))) && (Is64Bit) && ((Query.Types[1] == X86_s64)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_s64OrS32)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_sMaxScalar)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1);
  // TODO: replace with customized legalization using
  // specifics of cvttsd2si. The selection of this node requires
  // a vector type. Either G_SCALAR_TO_VECTOR is needed or more advanced
  // support of G_BUILD_VECTOR/G_INSERT_VECTOR_ELT is required beforehand.
  getActionDefinitionsBuilder(G_FPTOUI)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s32, X86_s32}, {X86_s32, X86_s64}, {X86_s64, X86_s32}, {X86_s64, X86_s64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (!(HasAVX512)) && (((HasSSE1) && ((Query.Types[1] == X86_s32))) || ((HasSSE2) && ((Query.Types[1] == X86_s64)))) && (((Query.Types[0]).getScalarSizeInBits() < (Is64Bit ? 64 : 32))); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (!(HasAVX512)) && (((HasSSE1) && ((Query.Types[1] == X86_s32))) || ((HasSSE2) && ((Query.Types[1] == X86_s64)))) && (Is64Bit) && ((Query.Types[0] == X86_s64)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_s64OrS32)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1);
  // vector ops
  // G_BUILD_VECTOR cannot be legalized by adding elements: the added
  // elements are undef, and narrowing the widened vector back to the
  // original type recreates the instruction being legalized, so the
  // legalizer would re-enqueue the same query forever.  Only clamp the
  // maximum number of elements; a narrow build vector is reported as
  // unsupported (and falls back to SelectionDAG) instead of looping.
  // Lowering non-constant narrow build vectors is tracked by #143099.
  getActionDefinitionsBuilder(G_BUILD_VECTOR)
      .coreCustomIf([=](const LegalityQuery &Query) { return ((HasSSE1) && ((Query.Types[0] == X86_v4s32))) || ((HasSSE2) && ((Query.Types[0] == X86_v2s64 || Query.Types[0] == X86_v8s16 || Query.Types[0] == X86_v16s8))) || ((HasAVX) && ((Query.Types[0] == X86_v4s64 || Query.Types[0] == X86_v8s32 || Query.Types[0] == X86_v16s16 || Query.Types[0] == X86_v32s8))) || ((HasAVX512) && ((Query.Types[0] == X86_v8s64 || Query.Types[0] == X86_v16s32 || Query.Types[0] == X86_v32s16 || Query.Types[0] == X86_v64s8))); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s8)) && (((Query.Types[0]).getNumElements() > (HasAVX512 ? 64 : (HasAVX ? 32 : 16)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((HasAVX512 ? 64 : (HasAVX ? 32 : 16))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s16)) && (((Query.Types[0]).getNumElements() > (HasAVX512 ? 32 : (HasAVX ? 16 : 8)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((HasAVX512 ? 32 : (HasAVX ? 16 : 8))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s32)) && (((Query.Types[0]).getNumElements() > (HasAVX512 ? 16 : (HasAVX ? 8 : 4)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((HasAVX512 ? 16 : (HasAVX ? 8 : 4))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X86_s64)) && (((Query.Types[0]).getNumElements() > (HasAVX512 ? 8 : (HasAVX ? 4 : 2)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((HasAVX512 ? 8 : (HasAVX ? 4 : 2))), (Query.Types[0]).getElementType())); });
  getActionDefinitionsBuilder(G_EXTRACT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v16s8, X86_v32s8}, {X86_v8s16, X86_v16s16}, {X86_v4s32, X86_v8s32}, {X86_v2s64, X86_v4s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v16s8, X86_v64s8}, {X86_v32s8, X86_v64s8}, {X86_v8s16, X86_v32s16}, {X86_v16s16, X86_v32s16}, {X86_v4s32, X86_v16s32}, {X86_v8s32, X86_v16s32}, {X86_v2s64, X86_v8s64}, {X86_v4s64, X86_v8s64}})(Query)); })
      .unsupported();
  getActionDefinitionsBuilder(G_INSERT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v32s8, X86_v16s8}, {X86_v16s16, X86_v8s16}, {X86_v8s32, X86_v4s32}, {X86_v4s64, X86_v2s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v64s8, X86_v16s8}, {X86_v64s8, X86_v32s8}, {X86_v32s16, X86_v8s16}, {X86_v32s16, X86_v16s16}, {X86_v16s32, X86_v4s32}, {X86_v16s32, X86_v8s32}, {X86_v8s64, X86_v2s64}, {X86_v8s64, X86_v4s64}})(Query)); })
      .unsupported();
  // todo: only permit dst types up to max legal vector register size?
  getActionDefinitionsBuilder(G_CONCAT_VECTORS)
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasSSE1) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v32s8, X86_v16s8}, {X86_v16s16, X86_v8s16}, {X86_v8s32, X86_v4s32}, {X86_v4s64, X86_v2s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (HasAVX) && (LegalityPredicates::typePairInSet(0, 1, {{X86_v64s8, X86_v16s8}, {X86_v64s8, X86_v32s8}, {X86_v32s16, X86_v8s16}, {X86_v32s16, X86_v16s16}, {X86_v16s32, X86_v4s32}, {X86_v16s32, X86_v8s32}, {X86_v8s64, X86_v2s64}, {X86_v8s64, X86_v4s64}})(Query)); });
  // todo: vectors and address spaces
  getActionDefinitionsBuilder(G_SELECT)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X86_s16, X86_s32}, {X86_s32, X86_s32}, {X86_p0, X86_s32}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(HasCMOV)) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s8, X86_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s64, X86_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (UseX87) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s80, X86_s32}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X86_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X86_s32)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_CMOVOrS8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X86_sMaxScalar);
  // memory intrinsics
  getActionDefinitionsBuilder({G_MEMCPY, G_MEMMOVE, G_MEMSET})
      .libcall();
  getActionDefinitionsBuilder({G_DYN_STACKALLOC, G_STACKSAVE, G_STACKRESTORE})
      .lower();
  // fp intrinsics
  // fpclass for i686 is disabled for llvm issue #171992
  getActionDefinitionsBuilder(G_IS_FPCLASS)
      .coreLowerIf([=](const LegalityQuery &Query) { return (Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X86_s1, X86_s32}, {X86_s1, X86_s64}, {X86_s1, X86_s80}})(Query)); });
  getActionDefinitionsBuilder({G_INTRINSIC_ROUNDEVEN, G_INTRINSIC_TRUNC})
      .scalarize(0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X86_s32)
      .libcall();
  getActionDefinitionsBuilder({G_INTRINSIC, G_INTRINSIC_W_SIDE_EFFECTS})
      .alwaysLegal();
  getActionDefinitionsBuilder({G_TRAP, G_DEBUGTRAP, G_UBSANTRAP})
      .alwaysLegal();
  getActionDefinitionsBuilder(G_INVOKE_REGION_START)
      .alwaysLegal();
