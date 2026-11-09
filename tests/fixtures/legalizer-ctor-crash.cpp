// A constructor with statements the importer cannot parse.  It must refuse
// them with their source line, not abort the run with a traceback.
RISCVLegalizerInfo::RISCVLegalizerInfo(const RISCVSubtarget &ST)
    : STI(ST) {
  const LLT s32 = LLT::scalar(32);
  auto &allowed = ST.isShader() ? AllShader : AllScalars;
  getActionDefinitionsBuilder(G_ADD).legalFor({s32});
}
