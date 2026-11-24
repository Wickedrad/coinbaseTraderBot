// The depth model file's schema number (research/depthStudy.ts writes it, research/history/depthSim.ts reads it, a cached model is
// reused only when it equals this). A model file without `schema` is schema 0 (the pooled four-asset tables of Nov 5 to Nov 22).
//   2  per-asset blocks (`byAsset`: shape and flow rows keyed by asset, and by a causal stress bucket inside the asset), the stress
//      edges per asset, the share of 15 s instants at which a book had an empty side (`gapShare`) and the real unquoted share of a whole
//      contract life (`lives`, per asset and pooled: what the empty-side draw is netted against)
//   3  an optional `calibration` block (research/history/depthCalibrate.ts, round R2): per asset, neutral-1 multipliers on the trade rate,
//      the trade size, the level sizes (and the best level's size on its own) and the quote-change rate, fitted on the FIT days. The simulator
//      reads one more block, so a schema-2 file (no calibration, and an older reader that would drop one silently) is refused, both ways.
// Bump it whenever the study's tables or the simulator's reading of them change in a way an older model file cannot feed.
//
// A CALIBRATION is a fit of the simulator it was fitted with (R2 fix round 1). The multipliers in `calibration` are numbers that make THIS fill-in, requote layer and
// feature code meet the real FIT days; a model reused (depth_model_run) under other code would carry numbers fitted to a different twin, with no later line saying so.
// So any change that moves the fill-in's stream for given multipliers has to bump DEPTH_MODEL_SCHEMA in the same commit, or be run with depth_model_run EMPTY so the
// model and its calibration are fitted again. That covers: research/history/depthSim.ts (the walk, the defaults DEFAULT_DEPTH_SIM_PARAMS, the resolution order),
// the fill-in's driver in research/goLiveTally.ts (streamFiller, fillQuotes), research/depthStudy.ts, the requote layer (REPLAY_VERSION) and the feature code (FEATURE_CODE_VERSION).
// The calibration stage also stamps three of these into the block (`calibration.code`: a hash of depthSim.ts with its comments and whitespace out, REPLAY_VERSION,
// FEATURE_CODE_VERSION) and the reuse check (research/historyTwin.ts checkDepthModelCalibration, the workflow's calibration-check step) REFUSES a block whose stamp is not this ref's, or has
// none. What the stamp cannot see (goLiveTally.ts's driver, the study) is covered only by this bump rule.
export const DEPTH_MODEL_SCHEMA = 3;
