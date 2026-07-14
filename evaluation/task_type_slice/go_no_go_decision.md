# Story 4.1 evidence — general/knowledge/factual confusion ()

**Decision: NO-GO**  (trio_confusion_rate=0.0847 vs threshold=0.1500, PROVISIONAL)

- trio confusion rate (headline, trio->trio only): **0.0847**
- trio escape rate (trio->other; NOT fixed by merging): 0.1171
- true-trio rows / scored on: 2716 / 5451 (held-out 20%)
- misroute-flip rate (AD-9 token swap): 0.372 (204 flips)

## per-class (trio)
  - factual: precision=0.933 recall=0.868 f1=0.900 support=965
  - general: precision=0.455 recall=0.033 f1=0.062 support=150
  - knowledge: precision=0.630 recall=0.828 f1=0.715 support=1601

GO = merge justified (Epic 4.2 may proceed). NO-GO = halt Epic 4, keep the labels, no AD-9 retrain.

NOTE (misroute-flip): a *directional* token-sensitivity proxy — the model_router's router-native numerics (question_type_confidence, best_model_tier) are absent from this CSV and zero-filled, so the absolute flip rate is not calibrated; it isolates the task_type token only.

CAVEAT: task-type labels are weak (dataset-derived via build_question_type.py). This measures whether the classifier reproduces the weak labels, not whether the labels are the semantically wrong cut. Strong-suggestive, not proof.
