"""Unit tests for src/aml_riskiq/serving/_request_validation.py's FiniteFloatFieldsModel --
the shared base class that makes every BP1/2/4/5 TxnFeatures schema reject NaN/Infinity/
-Infinity float values at the API boundary (see that module's docstring for the real,
empirically-confirmed gap this closes: before it existed, BP1's real /score route accepted
a NaN feature value as a normal request and returned a fabricated-looking 200)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import create_model

SRC_PATH = str(Path(__file__).resolve().parents[2] / "src" / "aml_riskiq")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from serving._request_validation import FiniteFloatFieldsModel  # noqa: E402


@pytest.fixture()
def model_cls():
    return create_model(
        "SampleFeatures",
        __base__=FiniteFloatFieldsModel,
        required_float=(float, ...),
        optional_float=(float | None, None),
        name=(str, ...),
    )


def test_accepts_ordinary_finite_values(model_cls):
    instance = model_cls(required_float=1.5, optional_float=2.5, name="ok")
    assert instance.required_float == 1.5
    assert instance.optional_float == 2.5


def test_accepts_none_on_optional_float_field(model_cls):
    instance = model_cls(required_float=1.0, optional_float=None, name="ok")
    assert instance.optional_float is None


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_required_float(model_cls, bad_value):
    with pytest.raises(Exception) as excinfo:
        model_cls(required_float=bad_value, optional_float=None, name="ok")
    assert "required_float" in str(excinfo.value)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_optional_float_when_actually_set(model_cls, bad_value):
    """None is the legitimate 'undefined' sentinel for an Optional[float] field (several real
    BP feature columns rely on this) -- but a caller who actually supplies a non-finite value
    for that same field is still rejected, same as a required field."""
    with pytest.raises(Exception) as excinfo:
        model_cls(required_float=1.0, optional_float=bad_value, name="ok")
    assert "optional_float" in str(excinfo.value)


def test_non_float_fields_are_not_touched_by_the_finite_check(model_cls):
    instance = model_cls(required_float=1.0, optional_float=None, name="any string at all")
    assert instance.name == "any string at all"


def test_multiple_bad_fields_are_all_named_in_one_error(model_cls):
    model_cls2 = create_model(
        "TwoFloats",
        __base__=FiniteFloatFieldsModel,
        a=(float, ...),
        b=(float, ...),
    )
    with pytest.raises(Exception) as excinfo:
        model_cls2(a=float("nan"), b=float("inf"))
    message = str(excinfo.value)
    assert "a" in message and "b" in message
