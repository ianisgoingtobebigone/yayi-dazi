from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


FIELD_ID_PATTERN = re.compile(r"M(?:0[1-8])-FLD-\d{3}")
SOURCE_TYPES = {"user_text", "user_photo", "existing_record", "user_correction"}
STATUSES = {"present", "denied", "unknown", "historical"}
PRODUCTION_ENABLED = False


class M01ContractError(ValueError):
    pass


@dataclass
class M01FactLedger:
    episode_id: str
    current: dict[str, dict[str, Any]] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    correction_events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, facts: Sequence[Mapping[str, Any]], *, turn_id: str) -> list[dict[str, Any]]:
        if not self.episode_id or not turn_id:
            raise M01ContractError("episode_id and turn_id are required")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(facts):
            field_id = str(item.get("field_id", ""))
            source_type = str(item.get("source_type", ""))
            status = str(item.get("status", ""))
            source_span = str(item.get("source_span", "")).strip()
            if not FIELD_ID_PATTERN.fullmatch(field_id) or field_id in seen:
                raise M01ContractError(f"fact {index} has an invalid or duplicate field_id")
            if source_type not in SOURCE_TYPES or status not in STATUSES:
                raise M01ContractError(f"fact {field_id} has an unsupported source_type or status")
            if source_type in {"user_text", "user_correction"} and not source_span:
                raise M01ContractError(f"fact {field_id} must preserve the user's source span")
            corrects = item.get("corrects_field_id")
            if source_type == "user_correction":
                if not isinstance(corrects, str) or corrects not in self.current:
                    raise M01ContractError(f"correction fact {field_id} requires an existing corrects_field_id")
            elif corrects is not None:
                raise M01ContractError("corrects_field_id is only valid for user_correction")
            fact = {
                "field_id": field_id,
                "value": item.get("value", "unknown"),
                "status": status,
                "source_type": source_type,
                "source_span": source_span,
                "observed_at": item.get("observed_at"),
                "uncertainty": item.get("uncertainty"),
                "corrects_field_id": corrects,
            }
            seen.add(field_id)
            if source_type == "user_correction":
                self.correction_events.append(
                    {
                        "turn_id": turn_id,
                        "original_fact": dict(self.current[str(corrects)]),
                        "correction_fact": dict(fact),
                        "requires_m00_correction_recalculation": True,
                    }
                )
            if previous := self.current.get(field_id):
                self.history.append({"turn_id": turn_id, "superseded_fact": dict(previous)})
            self.current[field_id] = fact
            self.history.append({"turn_id": turn_id, "recorded_fact": dict(fact)})
            normalized.append(fact)
        return normalized

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.update({"module": "M01", "production_enabled": False})
        return result
