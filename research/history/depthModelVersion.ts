// The depth model file's schema number (research/depthStudy.ts writes it, research/history/depthSim.ts reads it, a cached model is
// reused only when it equals this). A model file without `schema` is schema 0 (the pooled four-asset tables of Nov 5 to Nov 22).
//   2  per-asset blocks (`byAsset`: shape and flow rows keyed by asset, and by a causal stress bucket inside the asset), the stress
//      edges per asset, the share of 15 s instants at which a book had an empty side (`gapShare`) and the real unquoted share of a whole
//      contract life (`lives`, per asset and pooled: what the empty-side draw is netted against)
// Bump it whenever the study's tables or the simulator's reading of them change in a way an older model file cannot feed.
export const DEPTH_MODEL_SCHEMA = 2;
