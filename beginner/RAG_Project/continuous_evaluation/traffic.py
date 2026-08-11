"""Typed production-like traffic records for the continuous-evaluation lab."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_TRAFFIC_TYPES = {
    "synthetic_canary",
    "production_like_synthetic",
    "synthetic_security_canary",
    "synthetic_failure_fixture",
}


@dataclass(frozen=True)
class TrafficRequest:
    request_id: str
    traffic_type: str
    question: str
    approved_case_id: str | None = None
    risk_case_id: str | None = None
    controlled_context: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TrafficRequest":
        def required_text(name: str) -> str:
            raw = value.get(name)
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError(f"{name} must be a non-empty string")
            return raw.strip()

        traffic_type = required_text("traffic_type")
        if traffic_type not in ALLOWED_TRAFFIC_TYPES:
            raise ValueError(
                f"traffic_type must be one of {sorted(ALLOWED_TRAFFIC_TYPES)}"
            )

        def optional_text(name: str) -> str | None:
            raw = value.get(name)
            if raw is None:
                return None
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError(f"{name} must be null or a non-empty string")
            return raw.strip()

        request = cls(
            request_id=required_text("request_id"),
            traffic_type=traffic_type,
            question=required_text("question"),
            approved_case_id=optional_text("approved_case_id"),
            risk_case_id=optional_text("risk_case_id"),
            controlled_context=optional_text("controlled_context"),
        )
        if request.traffic_type == "synthetic_canary" and not request.approved_case_id:
            raise ValueError("synthetic_canary requires approved_case_id")
        if request.traffic_type == "synthetic_security_canary" and not request.risk_case_id:
            raise ValueError("synthetic_security_canary requires risk_case_id")
        if request.controlled_context and not request.risk_case_id:
            raise ValueError("controlled_context requires risk_case_id")
        return request

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "traffic_type": self.traffic_type,
            "question": self.question,
            "approved_case_id": self.approved_case_id,
            "risk_case_id": self.risk_case_id,
            "controlled_context": self.controlled_context,
        }


def load_traffic(path: Path) -> list[TrafficRequest]:
    requests: list[TrafficRequest] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise TypeError("row is not a JSON object")
            requests.append(TrafficRequest.from_dict(value))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid traffic row {line_number}: {exc}") from exc
    if not requests:
        raise ValueError("Traffic file is empty")
    ids = [request.request_id for request in requests]
    if len(ids) != len(set(ids)):
        raise ValueError("request_id values must be unique")
    return requests

