# src/models/
Model wrappers for this platform's real trained classifiers (BP1, BP2, BP4, BP5 -- each
its own champion selected via Stage A/B benchmarking, see each BP's own MODEL_CARD.md),
plus the shared CV harness (StratifiedKFold, seed=42, identical folds across models).
BP3 is rule-based (structural graph signals, no trained model, see its own RULE_CARD.md)
and BP6 is a pure read-only rollup of BP1-BP5's own already-computed figures -- neither
has a model wrapper here. Locked 6-BP scope (BP1-BP6); an earlier v1.0 8-BP draft
included a different BP6 (NLP/GenAI SAR narrative assistant) and two other BPs later
retired for lacking independent ground truth in this dataset -- see
claude/master-execution-plan.md for the full v1.0-to-v2.0 scope history.
