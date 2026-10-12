"""
Shared request-schema hardening for the platform's dynamically-built per-transaction
Pydantic models (BP1/BP2/BP4/BP5's `TxnFeatures`, built via `pydantic.create_model()` from
each BP's own real `FEATURE_COLS`).

Real gap this closes (found 2026-10-12, Improvement 3 production-readiness pass): Pydantic's
`float` field type is standard IEEE-754 float, which genuinely accepts `NaN`, `Infinity`, and
`-Infinity` -- all three are valid Python floats, and FastAPI's JSON body parsing accepts the
non-standard-but-widely-supported `NaN`/`Infinity`/`-Infinity` JSON tokens Python's own
`json` module emits and parses by default. Before this module existed, a request such as
`{"hour": NaN, ...}` was accepted as a normal, successfully-validated request and reached
`champion_model.predict_proba()` -- confirmed empirically (not assumed) against BP1's real
service: it returned a normal 200 with a fabricated-looking score, not a 422 or any other
signal that the input was nonsensical. Whether a REAL trained model would silently use NaN as
a tree-split direction, raise inside sklearn, or do something else entirely is model-
dependent and not something to rely on -- the right place to reject this is at the API
boundary, once, for every BP that shares this request-schema pattern (HYPER build-once
reuse), not inside each model's own prediction code.

Usage: pass `__base__=FiniteFloatFieldsModel` to `pydantic.create_model(...)` alongside the
existing per-column `_FIELD_TYPES` dict. No other call-site change needed -- every float (and
Optional[float]) field on the resulting model is checked; `None` on an Optional[float] field
is untouched (that is a legitimate "this ratio was undefined" value some BPs already rely on
via FastAPI's own Optional[float] = None and is a quite different, permitted case from a
caller's NaN/Infinity, which model_validator-level allows to stay distinct)."""

from __future__ import annotations

import math

from pydantic import BaseModel, model_validator


class FiniteFloatFieldsModel(BaseModel):
    """Base class for a dynamically-built `create_model()` schema. Rejects any field whose
    *parsed* value is a non-finite float (NaN, +Infinity, -Infinity) with a clean validation
    error (FastAPI turns this into a 422, never a 500 or a silently-accepted request) --
    `None` on an Optional[float] field is left alone, since several BPs' own NaN-prone
    feature columns legitimately use `None` (JSON `null`) to mean "undefined", not "caller
    sent garbage"."""

    @model_validator(mode="after")
    def _reject_non_finite_float_fields(self) -> "FiniteFloatFieldsModel":
        non_finite_fields = [
            name
            for name, value in self.__dict__.items()
            if isinstance(value, float) and not math.isfinite(value)
        ]
        if non_finite_fields:
            raise ValueError(
                "Field(s) "
                f"{non_finite_fields} must be finite numbers (NaN/Infinity/-Infinity are "
                "not accepted transaction-feature values)."
            )
        return self


__all__ = ["FiniteFloatFieldsModel"]
