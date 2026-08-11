"""Stable, risk-aware selection for reference-free semantic evaluation."""

from __future__ import annotations

import hashlib

from .traffic import TrafficRequest


ALWAYS_EVALUATE = {
    "synthetic_canary",
    "synthetic_security_canary",
    "synthetic_failure_fixture",
}


def semantic_selection(
    request: TrafficRequest, sample_rate: float
) -> tuple[bool, str]:
    if not 0.0 <= sample_rate <= 1.0:
        raise ValueError("sample_rate must be between 0 and 1")
    if request.traffic_type in ALWAYS_EVALUATE:
        return True, f"100% evaluation for {request.traffic_type}"
    digest = hashlib.sha256(request.request_id.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(2**64)
    selected = bucket < sample_rate
    return selected, (
        f"stable risk-adjusted sample at rate {sample_rate:.3f}; "
        f"bucket={bucket:.6f}"
    )

