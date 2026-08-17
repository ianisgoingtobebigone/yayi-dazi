#!/usr/bin/env python3
"""Compact JSON CLI over the bundled M00-M12 runtime package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


SCRIPTS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS))

from cn_oral_consult.m00 import ALL_LEVELS, full_triage  # noqa: E402
from cn_oral_consult.m10 import retrieve_m10  # noqa: E402
from cn_oral_consult.m11 import assemble_route as assemble_m11_route  # noqa: E402
from cn_oral_consult.privacy import evaluate_data_processing_gate  # noqa: E402
from full_runtime_self_check import evaluate as full_self_check  # noqa: E402


class RuntimeContractError(ValueError):
    pass


def triage(payload: Mapping[str, Any]) -> dict[str, Any]:
    return full_triage(payload)


def route(payload: Mapping[str, Any]) -> dict[str, Any]:
    safety = payload.get("safety_result")
    if not isinstance(safety, Mapping) or safety.get("effective_level") not in ALL_LEVELS:
        raise RuntimeContractError("route requires a current safety_result")
    level = str(safety["effective_level"])
    if level in {"E0", "E1", "U1", "NEEDS_CLARIFICATION"}:
        return {
            "schema_version": "cn-dental-m11.route.v1",
            "primary_module": None,
            "secondary_module": None,
            "route_status": "suspended_by_m00",
            "retrieval_modules": [],
            "health_first": payload.get("entry_mode") == "mixed",
            "route_uncertainty": ["普通专业分道由当前安全状态暂停"],
            "assembled_by": "M11",
            "production_enabled": False,
        }
    result = assemble_m11_route(payload.get("candidates"), entry_mode=str(payload.get("entry_mode", "")))
    result.update({"schema_version": "cn-dental-m11.route.v1", "production_enabled": False})
    return result


def retrieve(payload: Mapping[str, Any]) -> dict[str, Any]:
    route_result = payload.get("route_result")
    requested_module = str(payload.get("requested_by_module") or (route_result or {}).get("primary_module", ""))
    task = str(payload.get("task", "clinical_evidence"))
    default_entry_types = {
        "clinical_evidence": ["DIS", "LSN", "PRB"],
        "diagnostic_method_background": ["DXM"],
        "treatment_background": ["TRT"],
        "maintenance_background": ["MNT"],
    }
    return retrieve_m10(
        task=task,
        query=str(payload.get("query", "")),
        fact_basis_spans=payload.get("fact_basis_spans", []),
        fact_field_ids=payload.get("fact_field_ids", []),
        requested_by_module=requested_module,
        safety_result=payload.get("safety_result"),
        route_result=route_result,
        entry_types=payload.get("entry_types", default_entry_types.get(task, [])),
        audience=str(payload.get("audience", "public")),
        internal_preview=True,
    )


def data_governance(payload: Mapping[str, Any]) -> dict[str, Any]:
    return evaluate_data_processing_gate(payload)


def self_check() -> dict[str, Any]:
    return full_self_check()


def _read_payload(path: str | None) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8")) if path else json.load(sys.stdin)
    if not isinstance(payload, Mapping):
        raise RuntimeContractError("input JSON must be an object")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="cn-oral-consult bundled runtime")
    parser.add_argument("operation", choices=("data-governance", "triage", "route", "retrieve", "self-check"))
    parser.add_argument("--input", help="UTF-8 JSON file; omit to read JSON from stdin")
    args = parser.parse_args(argv)
    try:
        result = self_check() if args.operation == "self-check" else {
            "data-governance": data_governance,
            "triage": triage,
            "route": route,
            "retrieve": retrieve,
        }[args.operation](_read_payload(args.input))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") != "failed" else 1
    except (RuntimeContractError, ValueError, TypeError, FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"status": "contract_error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
