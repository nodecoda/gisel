/*===- TableGen'erated file -------------------------------------*- C++ -*-===*\
|*                                                                            *|
|* GlobalISel legalizer rule fragments                                        *|
|*                                                                            *|
|* Automatically generated file, do not edit!                                 *|
|*                                                                            *|
\*===----------------------------------------------------------------------===*/

  bool X_HasAVX = Subtarget.hasAVX();
  bool X_HasAVX2 = Subtarget.hasAVX2();
  bool X_HasAVX512 = Subtarget.hasAVX512();
  bool X_HasBMI = Subtarget.hasBMI();
  bool X_HasBWI = Subtarget.hasAVX512() && Subtarget.hasBWI();
  bool X_HasCMOV = Subtarget.canUseCMOV();
  bool X_HasDQI = Subtarget.hasAVX512() && Subtarget.hasDQI();
  bool X_HasLZCNT = Subtarget.hasLZCNT();
  bool X_HasPOPCNT = Subtarget.hasPOPCNT();
  bool X_HasSSE1 = Subtarget.hasSSE1();
  bool X_HasSSE2 = Subtarget.hasSSE2();
  bool X_HasSSE41 = Subtarget.hasSSE41();
  bool X_HasVLX = Subtarget.hasVLX();
  bool X_HasVPOPCNTDQ = Subtarget.hasVPOPCNTDQ();
  bool X_Is64Bit = Subtarget.is64Bit();
  bool X_UseX87 = !Subtarget.useSoftFloat() && Subtarget.hasX87();

  const LLT X_p0 = LLT::pointer(0, Subtarget.isTarget64BitLP64() ? 64 : 32);
  const LLT X_s1 = LLT::scalar(1);
  const LLT X_s8 = LLT::scalar(8);
  const LLT X_s16 = LLT::scalar(16);
  const LLT X_s32 = LLT::scalar(32);
  const LLT X_s64 = LLT::scalar(64);
  const LLT X_s80 = LLT::scalar(80);
  const LLT X_s128 = LLT::scalar(128);
  const LLT X_v2s32 = LLT::fixed_vector(2, 32);
  const LLT X_v4s8 = LLT::fixed_vector(4, 8);
  const LLT X_v16s8 = LLT::fixed_vector(16, 8);
  const LLT X_v8s16 = LLT::fixed_vector(8, 16);
  const LLT X_v4s32 = LLT::fixed_vector(4, 32);
  const LLT X_v2s64 = LLT::fixed_vector(2, 64);
  const LLT X_v2p0 = LLT::fixed_vector(2, X_p0);
  const LLT X_v32s8 = LLT::fixed_vector(32, 8);
  const LLT X_v16s16 = LLT::fixed_vector(16, 16);
  const LLT X_v8s32 = LLT::fixed_vector(8, 32);
  const LLT X_v4s64 = LLT::fixed_vector(4, 64);
  const LLT X_v4p0 = LLT::fixed_vector(4, X_p0);
  const LLT X_v64s8 = LLT::fixed_vector(64, 8);
  const LLT X_v32s16 = LLT::fixed_vector(32, 16);
  const LLT X_v16s32 = LLT::fixed_vector(16, 32);
  const LLT X_v8s64 = LLT::fixed_vector(8, 64);
  const LLT X_sel0 = (X_Is64Bit ? X_s64 : X_s32);
  const LLT X_sel1 = (X_HasAVX ? X_v32s8 : X_v16s8);
  const LLT X_sel2 = (X_HasAVX512 ? X_v64s8 : X_sel1);
  const LLT X_sel3 = (X_HasAVX ? X_v16s16 : X_v8s16);
  const LLT X_sel4 = (X_HasAVX512 ? X_v32s16 : X_sel3);
  const LLT X_sel5 = (X_HasAVX ? X_v8s32 : X_v4s32);
  const LLT X_sel6 = (X_HasAVX512 ? X_v16s32 : X_sel5);
  const LLT X_sel7 = (X_HasAVX ? X_v4s64 : X_v2s64);
  const LLT X_sel8 = (X_HasAVX512 ? X_v8s64 : X_sel7);
  const LLT X_sel9 = (X_HasSSE2 ? X_s64 : X_s32);
  const LLT X_sel10 = (X_UseX87 && !(X_HasSSE1) ? X_s16 : X_s32);
  const LLT X_sel11 = (X_HasCMOV ? X_s16 : X_s8);

  getActionDefinitionsBuilder({G_IMPLICIT_DEF, G_PHI, G_FREEZE, G_CONSTANT_FOLD_BARRIER})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_p0 || Query.Types[0] == X_s1 || Query.Types[0] == X_s8 || Query.Types[0] == X_s16 || Query.Types[0] == X_s32 || Query.Types[0] == X_s64); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_UseX87) && ((Query.Types[0] == X_s80)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && ((Query.Types[0] == X_s128)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && ((Query.Types[0] == X_v16s8 || Query.Types[0] == X_v8s16 || Query.Types[0] == X_v4s32 || Query.Types[0] == X_v2s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX) && ((Query.Types[0] == X_v32s8 || Query.Types[0] == X_v16s16 || Query.Types[0] == X_v8s32 || Query.Types[0] == X_v4s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && ((Query.Types[0] == X_v64s8 || Query.Types[0] == X_v32s16 || Query.Types[0] == X_v16s32 || Query.Types[0] == X_v8s64)); })
      .coreWidenScalarOrEltToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalarOrElt([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalarOrElt([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .coreMoreElementsToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s8)) && (((Query.Types[0]).getNumElements() < (X_v16s8).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X_v16s8).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s8)) && (((Query.Types[0]).getNumElements() > (X_sel2).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel2).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s16)) && (((Query.Types[0]).getNumElements() < (X_v8s16).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X_v8s16).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s16)) && (((Query.Types[0]).getNumElements() > (X_sel4).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel4).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s32)) && (((Query.Types[0]).getNumElements() < (X_v4s32).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X_v4s32).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s32)) && (((Query.Types[0]).getNumElements() > (X_sel6).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel6).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s64)) && (((Query.Types[0]).getNumElements() < (X_v2s64).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X_v2s64).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s64)) && (((Query.Types[0]).getNumElements() > (X_sel8).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel8).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_p0)) && (((Query.Types[0]).getNumElements() > (X_Is64Bit ? (X_sel8).getNumElements() : (X_sel6).getNumElements()))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_Is64Bit ? (X_sel8).getNumElements() : (X_sel6).getNumElements())), (Query.Types[0]).getElementType())); })
      .coreScalarizeIf([=](const LegalityQuery &Query) { return ((Query.Types[0]).getScalarSizeInBits() > 64); }, 0);
  getActionDefinitionsBuilder(G_CONSTANT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_p0 || Query.Types[0] == X_s8 || Query.Types[0] == X_s16 || Query.Types[0] == X_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && ((Query.Types[0] == X_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0);
  getActionDefinitionsBuilder({G_LROUND, G_LLROUND})
      .coreWidenTo([=](const LegalityQuery &Query) { return (Query.Types[1] == X_s16); }, 1, [=](const LegalityQuery &Query) { return std::make_pair(1, X_s32); })
      .libcall();
  getActionDefinitionsBuilder({G_FCOS, G_FCOSH, G_FACOS, G_FSIN, G_FSINH, G_FASIN, G_FTAN, G_FTANH, G_FATAN, G_FATAN2, G_FPOW, G_FEXP, G_FEXP2, G_FEXP10, G_FLOG, G_FLOG2, G_FLOG10, G_FPOWI, G_FSINCOS, G_FCEIL, G_FFLOOR})
      .libcall();
  getActionDefinitionsBuilder(G_FNEG)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_UseX87) && (!(X_HasSSE1))) && ((Query.Types[0] == X_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_UseX87) && (!(X_HasSSE2))) && ((Query.Types[0] == X_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_UseX87) && ((Query.Types[0] == X_s80)); })
      .lower();
  getActionDefinitionsBuilder(G_FSQRT)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasSSE1) || (X_UseX87)) && ((Query.Types[0] == X_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasSSE2) || (X_UseX87)) && ((Query.Types[0] == X_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_UseX87) && ((Query.Types[0] == X_s80)); });
  getActionDefinitionsBuilder({G_GET_ROUNDING, G_SET_ROUNDING})
      .coreCustomIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s32); });
  getActionDefinitionsBuilder(G_MERGE_VALUES)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 8)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s32)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((((Query.Types[0]).getSizeInBits().getKnownMinValue() == 16)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 32)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 64)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 128)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 256)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 512))) && ((((Query.Types[1]).getSizeInBits().getKnownMinValue() == 8)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 16)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 32)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 64)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 128)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 256))); });
  getActionDefinitionsBuilder(G_UNMERGE_VALUES)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s32)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((((Query.Types[1]).getSizeInBits().getKnownMinValue() == 16)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 32)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 64)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 128)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 256)) || (((Query.Types[1]).getSizeInBits().getKnownMinValue() == 512))) && ((((Query.Types[0]).getSizeInBits().getKnownMinValue() == 8)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 16)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 32)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 64)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 128)) || (((Query.Types[0]).getSizeInBits().getKnownMinValue() == 256))); });
  getActionDefinitionsBuilder({G_UMIN, G_UMAX, G_SMIN, G_SMAX})
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .lower();
  getActionDefinitionsBuilder({G_ADD, G_SUB})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s8 || Query.Types[0] == X_s16 || Query.Types[0] == X_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && ((Query.Types[0] == X_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && ((Query.Types[0] == X_v16s8 || Query.Types[0] == X_v8s16 || Query.Types[0] == X_v4s32 || Query.Types[0] == X_v2s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX2) && ((Query.Types[0] == X_v32s8 || Query.Types[0] == X_v16s16 || Query.Types[0] == X_v8s32 || Query.Types[0] == X_v4s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && ((Query.Types[0] == X_v16s32 || Query.Types[0] == X_v8s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasBWI) && ((Query.Types[0] == X_v64s8 || Query.Types[0] == X_v32s16)); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s8)) && (((Query.Types[0]).getNumElements() < 16)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(16, (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s16)) && (((Query.Types[0]).getNumElements() < 8)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(8, (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s32)) && (((Query.Types[0]).getNumElements() < 4)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(4, (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s64)) && (((Query.Types[0]).getNumElements() < 2)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(2, (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s8)) && (((Query.Types[0]).getNumElements() > (X_HasBWI ? 64 : (X_HasAVX2 ? 32 : 16)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_HasBWI ? 64 : (X_HasAVX2 ? 32 : 16))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s16)) && (((Query.Types[0]).getNumElements() > (X_HasBWI ? 32 : (X_HasAVX2 ? 16 : 8)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_HasBWI ? 32 : (X_HasAVX2 ? 16 : 8))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s32)) && (((Query.Types[0]).getNumElements() > (X_HasAVX512 ? 16 : (X_HasAVX2 ? 8 : 4)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_HasAVX512 ? 16 : (X_HasAVX2 ? 8 : 4))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s64)) && (((Query.Types[0]).getNumElements() > (X_HasAVX512 ? 8 : (X_HasAVX2 ? 4 : 2)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_HasAVX512 ? 8 : (X_HasAVX2 ? 4 : 2))), (Query.Types[0]).getElementType())); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .scalarize(0);
  getActionDefinitionsBuilder({G_UADDE, G_UADDO, G_USUBE, G_USUBO})
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X_s8, X_s8}, {X_s16, X_s8}, {X_s32, X_s8}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s8}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_s8)
      .scalarize(0);
  getActionDefinitionsBuilder(G_MUL)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s8 || Query.Types[0] == X_s16 || Query.Types[0] == X_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && ((Query.Types[0] == X_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && ((Query.Types[0] == X_v8s16)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE41) && ((Query.Types[0] == X_v4s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX2) && ((Query.Types[0] == X_v16s16 || Query.Types[0] == X_v8s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && ((Query.Types[0] == X_v16s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasDQI) && ((Query.Types[0] == X_v8s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasDQI) && (X_HasVLX)) && ((Query.Types[0] == X_v2s64 || Query.Types[0] == X_v4s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasBWI) && ((Query.Types[0] == X_v32s16)); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s16)) && (((Query.Types[0]).getNumElements() < 8)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(8, (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s32)) && (((Query.Types[0]).getNumElements() < 4)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector(4, (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s64)) && (((Query.Types[0]).getNumElements() < (X_HasVLX ? 2 : 8))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X_HasVLX ? 2 : 8), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s16)) && (((Query.Types[0]).getNumElements() > (X_HasBWI ? 32 : (X_HasAVX2 ? 16 : 8)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_HasBWI ? 32 : (X_HasAVX2 ? 16 : 8))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s32)) && (((Query.Types[0]).getNumElements() > (X_HasAVX512 ? 16 : (X_HasAVX2 ? 8 : 4)))); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_HasAVX512 ? 16 : (X_HasAVX2 ? 8 : 4))), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s64)) && (((Query.Types[0]).getNumElements() > 8)); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed(8), (Query.Types[0]).getElementType())); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .scalarize(0);
  getActionDefinitionsBuilder({G_SMULH, G_UMULH})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s8 || Query.Types[0] == X_s16 || Query.Types[0] == X_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && ((Query.Types[0] == X_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .scalarize(0);
  getActionDefinitionsBuilder({G_SDIV, G_SREM, G_UDIV, G_UREM})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s8 || Query.Types[0] == X_s16 || Query.Types[0] == X_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && ((Query.Types[0] == X_s64)); })
      .coreLibcallIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s64); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0);
  getActionDefinitionsBuilder({G_SHL, G_LSHR, G_ASHR})
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X_s8, X_s8}, {X_s16, X_s8}, {X_s32, X_s8}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s8}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_s8);
  getActionDefinitionsBuilder({G_AND, G_OR, G_XOR})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s8 || Query.Types[0] == X_s16 || Query.Types[0] == X_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && ((Query.Types[0] == X_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && ((Query.Types[0] == X_v16s8 || Query.Types[0] == X_v8s16 || Query.Types[0] == X_v4s32 || Query.Types[0] == X_v2s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX) && ((Query.Types[0] == X_v32s8 || Query.Types[0] == X_v16s16 || Query.Types[0] == X_v8s32 || Query.Types[0] == X_v4s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && ((Query.Types[0] == X_v64s8 || Query.Types[0] == X_v32s16 || Query.Types[0] == X_v16s32 || Query.Types[0] == X_v8s64)); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s8)) && (((Query.Types[0]).getNumElements() < (X_v16s8).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X_v16s8).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s8)) && (((Query.Types[0]).getNumElements() > (X_sel2).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel2).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s16)) && (((Query.Types[0]).getNumElements() < (X_v8s16).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X_v8s16).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s16)) && (((Query.Types[0]).getNumElements() > (X_sel4).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel4).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s32)) && (((Query.Types[0]).getNumElements() < (X_v4s32).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X_v4s32).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s32)) && (((Query.Types[0]).getNumElements() > (X_sel6).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel6).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreMoreTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s64)) && (((Query.Types[0]).getNumElements() < (X_v2s64).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::fixed_vector((X_v2s64).getNumElements(), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s64)) && (((Query.Types[0]).getNumElements() > (X_sel8).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel8).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .scalarize(0);
  getActionDefinitionsBuilder(G_ICMP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X_s8, X_s8}, {X_s8, X_s16}, {X_s8, X_s32}, {X_s8, X_s64}, {X_s8, X_p0}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(X_Is64Bit)) && (LegalityPredicates::typePairInSet(0, 1, {{X_s8, X_s8}, {X_s8, X_s16}, {X_s8, X_s32}, {X_s8, X_p0}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel0);
  getActionDefinitionsBuilder(G_BSWAP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && ((Query.Types[0] == X_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0);
  getActionDefinitionsBuilder(G_CTPOP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasPOPCNT) && (LegalityPredicates::typePairInSet(0, 1, {{X_s16, X_s16}, {X_s32, X_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasPOPCNT) && (X_Is64Bit)) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasVPOPCNTDQ) && (LegalityPredicates::typePairInSet(0, 1, {{X_v16s32, X_v16s32}, {X_v8s64, X_v8s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasVPOPCNTDQ) && (X_HasVLX)) && (LegalityPredicates::typePairInSet(0, 1, {{X_v4s32, X_v4s32}, {X_v8s32, X_v8s32}, {X_v2s64, X_v2s64}, {X_v4s64, X_v4s64}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel0)
      .coreMinScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1)
      .coreMaxScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1);
  getActionDefinitionsBuilder(G_CTLZ)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasLZCNT) && (LegalityPredicates::typePairInSet(0, 1, {{X_s16, X_s16}, {X_s32, X_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasLZCNT) && (X_Is64Bit)) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s64}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel0)
      .coreMinScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1)
      .coreMaxScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1);
  getActionDefinitionsBuilder(G_CTTZ_ZERO_POISON)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X_s16, X_s16}, {X_s32, X_s32}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s64}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel0)
      .coreMinScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1)
      .coreMaxScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1);
  getActionDefinitionsBuilder(G_CTTZ)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasBMI) && (LegalityPredicates::typePairInSet(0, 1, {{X_s16, X_s16}, {X_s32, X_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasBMI) && (X_Is64Bit)) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s64}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 16)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s16)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel0)
      .coreMinScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1)
      .coreMaxScalarSameAs([](const LegalityQuery &) { return true; }, 0, 1);
  getActionDefinitionsBuilder(G_BR)
      .alwaysLegal();
  getActionDefinitionsBuilder(G_BRCOND)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s1); });
  getActionDefinitionsBuilder(G_PTRTOINT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X_s1, X_p0}, {X_s8, X_p0}, {X_s16, X_p0}, {X_s32, X_p0}, {X_s64, X_p0}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(X_Is64Bit)) && (LegalityPredicates::typePairInSet(0, 1, {{X_s1, X_p0}, {X_s8, X_p0}, {X_s16, X_p0}, {X_s32, X_p0}})(Query)); })
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8);
  getActionDefinitionsBuilder(G_INTTOPTR)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X_p0, X_sel0}})(Query); });
  getActionDefinitionsBuilder(G_CONSTANT_POOL)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_p0); });
  getActionDefinitionsBuilder(G_PTR_ADD)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X_p0, X_s32}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X_p0, X_s64}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 32)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel0);
  getActionDefinitionsBuilder(G_FRAME_INDEX)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_p0); });
  getActionDefinitionsBuilder(G_GLOBAL_VALUE)
      .coreCustomIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_p0); });
  getActionDefinitionsBuilder(G_LOAD)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s8, X_p0, X_s8, 1}, {X_s16, X_p0, X_s16, 1}, {X_s32, X_p0, X_s32, 1}, {X_s80, X_p0, X_s80, 1}, {X_p0, X_p0, X_p0, 1}, {X_v4s8, X_p0, X_v4s8, 1}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s64, X_p0, X_s64, 1}, {X_v2s32, X_p0, X_v2s32, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE1) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_v4s32, X_p0, X_v4s32, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_v16s8, X_p0, X_v16s8, 1}, {X_v8s16, X_p0, X_v8s16, 1}, {X_v2s64, X_p0, X_v2s64, 1}, {X_v2p0, X_p0, X_v2p0, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_v32s8, X_p0, X_v32s8, 1}, {X_v16s16, X_p0, X_v16s16, 1}, {X_v8s32, X_p0, X_v8s32, 1}, {X_v4s64, X_p0, X_v4s64, 1}, {X_v4p0, X_p0, X_v4p0, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_v64s8, X_p0, X_v64s8, 1}, {X_v32s16, X_p0, X_v32s16, 1}, {X_v16s32, X_p0, X_v16s32, 1}, {X_v8s64, X_p0, X_v8s64, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s8, X_p0, X_s1, 1}, {X_s16, X_p0, X_s8, 1}, {X_s32, X_p0, X_s8, 1}, {X_s32, X_p0, X_s16, 1}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s64, X_p0, X_s8, 1}, {X_s64, X_p0, X_s16, 1}, {X_s64, X_p0, X_s32, 1}})(Query)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .scalarize(0);
  getActionDefinitionsBuilder(G_STORE)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s8, X_p0, X_s8, 1}, {X_s16, X_p0, X_s16, 1}, {X_s32, X_p0, X_s32, 1}, {X_s80, X_p0, X_s80, 1}, {X_p0, X_p0, X_p0, 1}, {X_v4s8, X_p0, X_v4s8, 1}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s64, X_p0, X_s64, 1}, {X_v2s32, X_p0, X_v2s32, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE1) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_v4s32, X_p0, X_v4s32, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_v16s8, X_p0, X_v16s8, 1}, {X_v8s16, X_p0, X_v8s16, 1}, {X_v2s64, X_p0, X_v2s64, 1}, {X_v2p0, X_p0, X_v2p0, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_v32s8, X_p0, X_v32s8, 1}, {X_v16s16, X_p0, X_v16s16, 1}, {X_v8s32, X_p0, X_v8s32, 1}, {X_v4s64, X_p0, X_v4s64, 1}, {X_v4p0, X_p0, X_v4p0, 1}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_v64s8, X_p0, X_v64s8, 1}, {X_v32s16, X_p0, X_v32s16, 1}, {X_v16s32, X_p0, X_v16s32, 1}, {X_v8s64, X_p0, X_v8s64, 1}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (Query.Types[0] != (Query.MMODescrs[0]).MemoryTy); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .scalarize(0);
  getActionDefinitionsBuilder(G_SEXTLOAD)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s16, X_p0, X_s8, 1}, {X_s32, X_p0, X_s8, 1}, {X_s32, X_p0, X_s16, 1}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s64, X_p0, X_s8, 1}, {X_s64, X_p0, X_s16, 1}, {X_s64, X_p0, X_s32, 1}})(Query)); });
  getActionDefinitionsBuilder(G_ZEXTLOAD)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s16, X_p0, X_s8, 1}, {X_s32, X_p0, X_s8, 1}, {X_s32, X_p0, X_s16, 1}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s64, X_p0, X_s8, 1}, {X_s64, X_p0, X_s16, 1}, {X_s64, X_p0, X_s32, 1}})(Query)); });
  getActionDefinitionsBuilder(G_FPEXTLOAD)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_UseX87) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s80, X_p0, X_s32, 1}, {X_s80, X_p0, X_s64, 1}, {X_s64, X_p0, X_s32, 1}})(Query)); });
  getActionDefinitionsBuilder(G_FPTRUNCSTORE)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_UseX87) && (LegalityPredicates::typePairAndMemDescInSet(0, 1, 0, {{X_s80, X_p0, X_s32, 1}, {X_s80, X_p0, X_s64, 1}, {X_s64, X_p0, X_s32, 1}})(Query)); });
  getActionDefinitionsBuilder(G_ANYEXT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s8 || Query.Types[0] == X_s16 || Query.Types[0] == X_s32 || Query.Types[0] == X_s128); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && ((Query.Types[0] == X_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel0)
      .scalarize(0);
  getActionDefinitionsBuilder({G_SEXT, G_ZEXT})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s8 || Query.Types[0] == X_s16 || Query.Types[0] == X_s32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && ((Query.Types[0] == X_s64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel0)
      .scalarize(0);
  getActionDefinitionsBuilder(G_TRUNC)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X_s1, X_s8}, {X_s1, X_s16}, {X_s1, X_s32}, {X_s1, X_s64}, {X_s1, X_s128}, {X_s8, X_s8}, {X_s8, X_s16}, {X_s8, X_s32}, {X_s8, X_s64}, {X_s8, X_s128}, {X_s16, X_s8}, {X_s16, X_s16}, {X_s16, X_s32}, {X_s16, X_s64}, {X_s16, X_s128}, {X_s32, X_s8}, {X_s32, X_s16}, {X_s32, X_s32}, {X_s32, X_s64}, {X_s32, X_s128}, {X_s64, X_s8}, {X_s64, X_s16}, {X_s64, X_s32}, {X_s64, X_s64}, {X_s64, X_s128}})(Query); });
  getActionDefinitionsBuilder(G_SEXT_INREG)
      .lower();
  getActionDefinitionsBuilder(G_FCONSTANT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s32 || Query.Types[0] == X_s64); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_UseX87) && ((Query.Types[0] == X_s80)); });
  getActionDefinitionsBuilder({G_FADD, G_FSUB, G_FMUL, G_FDIV})
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == X_s32 || Query.Types[0] == X_s64); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE1) && ((Query.Types[0] == X_v4s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && ((Query.Types[0] == X_v2s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX) && ((Query.Types[0] == X_v8s32 || Query.Types[0] == X_v4s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && ((Query.Types[0] == X_v16s32 || Query.Types[0] == X_v8s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_UseX87) && ((Query.Types[0] == X_s80)); });
  getActionDefinitionsBuilder(G_FABS)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_UseX87) && ((Query.Types[0] == X_s80)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_UseX87) && (!(X_Is64Bit))) && ((Query.Types[0] == X_s64)); })
      .lower();
  getActionDefinitionsBuilder(G_FCMP)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasSSE1) || (X_UseX87)) && ((Query.Types[0] == X_s8 || Query.Types[0] == X_s32)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasSSE2) || (X_UseX87)) && ((Query.Types[0] == X_s8 || Query.Types[0] == X_s64)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_UseX87) && ((Query.Types[0] == X_s8 || Query.Types[0] == X_s80)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_s8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel9)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1);
  getActionDefinitionsBuilder(G_FPEXT)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX) && (LegalityPredicates::typePairInSet(0, 1, {{X_v4s64, X_v4s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X_v8s64, X_v8s32}})(Query)); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (X_UseX87) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s32}, {X_s80, X_s32}, {X_s80, X_s64}})(Query)); })
      .libcall();
  getActionDefinitionsBuilder(G_FPTRUNC)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && (LegalityPredicates::typePairInSet(0, 1, {{X_s32, X_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX) && (LegalityPredicates::typePairInSet(0, 1, {{X_v4s32, X_v4s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X_v8s32, X_v8s64}})(Query)); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (X_UseX87) && (LegalityPredicates::typePairInSet(0, 1, {{X_s32, X_s64}, {X_s32, X_s80}, {X_s64, X_s80}})(Query)); });
  getActionDefinitionsBuilder(G_SITOFP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE1) && (LegalityPredicates::typePairInSet(0, 1, {{X_s32, X_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasSSE1) && (X_Is64Bit)) && (LegalityPredicates::typePairInSet(0, 1, {{X_s32, X_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasSSE2) && (X_Is64Bit)) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s64}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_sel10)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel0)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1)
      .coreCustomIf([=](const LegalityQuery &Query) { return (X_UseX87) && (LegalityPredicates::typePairInSet(0, 1, {{X_s32, X_s16}, {X_s32, X_s32}, {X_s32, X_s64}, {X_s64, X_s16}, {X_s64, X_s32}, {X_s64, X_s64}, {X_s80, X_s16}, {X_s80, X_s32}, {X_s80, X_s64}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel9)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0);
  getActionDefinitionsBuilder(G_FPTOSI)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE1) && (LegalityPredicates::typePairInSet(0, 1, {{X_s32, X_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasSSE1) && (X_Is64Bit)) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE2) && (LegalityPredicates::typePairInSet(0, 1, {{X_s32, X_s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasSSE2) && (X_Is64Bit)) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s64}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_sel10)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreCustomIf([=](const LegalityQuery &Query) { return (X_UseX87) && (LegalityPredicates::typePairInSet(0, 1, {{X_s16, X_s32}, {X_s16, X_s64}, {X_s16, X_s80}, {X_s32, X_s32}, {X_s32, X_s64}, {X_s32, X_s80}, {X_s64, X_s32}, {X_s64, X_s64}, {X_s64, X_s80}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel9)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1);
  getActionDefinitionsBuilder(G_UITOFP)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X_s32, X_s32}, {X_s32, X_s64}, {X_s64, X_s32}, {X_s64, X_s64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (!(X_HasAVX512)) && (((X_HasSSE1) && ((Query.Types[0] == X_s32))) || ((X_HasSSE2) && ((Query.Types[0] == X_s64)))) && ((Query.Types[1].isScalar()) && (((Query.Types[1]).getSizeInBits().getKnownMinValue() < (X_Is64Bit ? 64 : 32)))); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (!(X_HasAVX512)) && (((X_HasSSE1) && ((Query.Types[0] == X_s32))) || ((X_HasSSE2) && ((Query.Types[0] == X_s64)))) && ((X_Is64Bit) && ((Query.Types[1] == X_s64))); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel9)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel0)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1);
  getActionDefinitionsBuilder(G_FPTOUI)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X_s32, X_s32}, {X_s32, X_s64}, {X_s64, X_s32}, {X_s64, X_s64}})(Query)); })
      .coreCustomIf([=](const LegalityQuery &Query) { return (!(X_HasAVX512)) && (((X_HasSSE1) && ((Query.Types[1] == X_s32))) || ((X_HasSSE2) && ((Query.Types[1] == X_s64)))) && ((Query.Types[0].isScalar()) && (((Query.Types[0]).getSizeInBits().getKnownMinValue() < (X_Is64Bit ? 64 : 32)))); })
      .coreLowerIf([=](const LegalityQuery &Query) { return (!(X_HasAVX512)) && (((X_HasSSE1) && ((Query.Types[1] == X_s32))) || ((X_HasSSE2) && ((Query.Types[1] == X_s64)))) && ((X_Is64Bit) && ((Query.Types[0] == X_s64))); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_sel9)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 1);
  getActionDefinitionsBuilder(G_BUILD_VECTOR)
      .coreCustomIf([=](const LegalityQuery &Query) { return ((X_HasSSE1) && ((Query.Types[0] == X_v4s32))) || ((X_HasSSE2) && ((Query.Types[0] == X_v2s64 || Query.Types[0] == X_v8s16 || Query.Types[0] == X_v16s8))) || ((X_HasAVX) && ((Query.Types[0] == X_v4s64 || Query.Types[0] == X_v8s32 || Query.Types[0] == X_v16s16 || Query.Types[0] == X_v32s8))) || ((X_HasAVX512) && ((Query.Types[0] == X_v8s64 || Query.Types[0] == X_v16s32 || Query.Types[0] == X_v32s16 || Query.Types[0] == X_v64s8))); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s8)) && (((Query.Types[0]).getNumElements() > (X_sel2).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel2).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s16)) && (((Query.Types[0]).getNumElements() > (X_sel4).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel4).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s32)) && (((Query.Types[0]).getNumElements() > (X_sel6).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel6).getNumElements()), (Query.Types[0]).getElementType())); })
      .coreFewerTo([=](const LegalityQuery &Query) { return (Query.Types[0].isVector()) && (!(Query.Types[0].isScalableVector())) && (((Query.Types[0]).getElementType() == X_s64)) && (((Query.Types[0]).getNumElements() > (X_sel8).getNumElements())); }, 0, [=](const LegalityQuery &Query) { return std::make_pair(0, LLT::scalarOrVector(ElementCount::getFixed((X_sel8).getNumElements()), (Query.Types[0]).getElementType())); });
  getActionDefinitionsBuilder(G_EXTRACT)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasAVX) && (LegalityPredicates::typePairInSet(0, 1, {{X_v16s8, X_v32s8}, {X_v8s16, X_v16s16}, {X_v4s32, X_v8s32}, {X_v2s64, X_v4s64}})(Query))) || ((X_HasAVX512) && (LegalityPredicates::typePairInSet(0, 1, {{X_v16s8, X_v64s8}, {X_v32s8, X_v64s8}, {X_v8s16, X_v32s16}, {X_v16s16, X_v32s16}, {X_v4s32, X_v16s32}, {X_v8s32, X_v16s32}, {X_v2s64, X_v8s64}, {X_v4s64, X_v8s64}})(Query))); });
  getActionDefinitionsBuilder(G_INSERT)
      .coreLegalIf([=](const LegalityQuery &Query) { return ((X_HasAVX) && (LegalityPredicates::typePairInSet(1, 0, {{X_v16s8, X_v32s8}, {X_v8s16, X_v16s16}, {X_v4s32, X_v8s32}, {X_v2s64, X_v4s64}})(Query))) || ((X_HasAVX512) && (LegalityPredicates::typePairInSet(1, 0, {{X_v16s8, X_v64s8}, {X_v32s8, X_v64s8}, {X_v8s16, X_v32s16}, {X_v16s16, X_v32s16}, {X_v4s32, X_v16s32}, {X_v8s32, X_v16s32}, {X_v2s64, X_v8s64}, {X_v4s64, X_v8s64}})(Query))); });
  getActionDefinitionsBuilder(G_CONCAT_VECTORS)
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasSSE1) && (LegalityPredicates::typePairInSet(0, 1, {{X_v32s8, X_v16s8}, {X_v16s16, X_v8s16}, {X_v8s32, X_v4s32}, {X_v4s64, X_v2s64}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_HasAVX) && (LegalityPredicates::typePairInSet(0, 1, {{X_v64s8, X_v16s8}, {X_v64s8, X_v32s8}, {X_v32s16, X_v8s16}, {X_v32s16, X_v16s16}, {X_v16s32, X_v4s32}, {X_v16s32, X_v8s32}, {X_v8s64, X_v2s64}, {X_v8s64, X_v4s64}})(Query)); });
  getActionDefinitionsBuilder(G_SELECT)
      .coreLegalIf([=](const LegalityQuery &Query) { return LegalityPredicates::typePairInSet(0, 1, {{X_s16, X_s32}, {X_s32, X_s32}, {X_p0, X_s32}})(Query); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (!(X_HasCMOV)) && (LegalityPredicates::typePairInSet(0, 1, {{X_s8, X_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X_s64, X_s32}})(Query)); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (X_UseX87) && (LegalityPredicates::typePairInSet(0, 1, {{X_s80, X_s32}})(Query)); })
      .coreMinScalar([](const LegalityQuery &) { return true; }, 1, X_s32)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 1, X_s32)
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 8)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_sel11)
      .coreMaxScalar([](const LegalityQuery &) { return true; }, 0, X_sel0);
  getActionDefinitionsBuilder({G_MEMCPY, G_MEMMOVE, G_MEMSET})
      .libcall();
  getActionDefinitionsBuilder({G_DYN_STACKALLOC, G_STACKSAVE, G_STACKRESTORE})
      .lower();
  getActionDefinitionsBuilder(G_IS_FPCLASS)
      .coreLowerIf([=](const LegalityQuery &Query) { return (X_Is64Bit) && (LegalityPredicates::typePairInSet(0, 1, {{X_s1, X_s32}, {X_s1, X_s64}, {X_s1, X_s80}})(Query)); });
  getActionDefinitionsBuilder({G_INTRINSIC_ROUNDEVEN, G_INTRINSIC_TRUNC})
      .scalarize(0)
      .coreMinScalar([](const LegalityQuery &) { return true; }, 0, X_s32)
      .libcall();
  getActionDefinitionsBuilder({G_INTRINSIC, G_INTRINSIC_W_SIDE_EFFECTS})
      .alwaysLegal();
  getActionDefinitionsBuilder({G_TRAP, G_DEBUGTRAP, G_UBSANTRAP})
      .alwaysLegal();
  getActionDefinitionsBuilder(G_INVOKE_REGION_START)
      .alwaysLegal();
