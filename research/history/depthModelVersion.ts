// The depth model's format and study version: ONE number, read by whoever writes a depth model and by whoever reuses one.
//
// research/depthStudy.ts records it in every model it fits (`schema`); research/historyTwin.ts reuses a model that an earlier
// run fitted (workflow input depth_model_run) only when the file's `schema` (a model with no `schema` reads as 0) is exactly
// this number, so a change to the study or to what the simulator reads from the model (bump this number in the same commit)
// makes every older model refuse itself instead of being played with new code. Tests import the constant; none spells its value.
export const DEPTH_MODEL_SCHEMA = 1;
