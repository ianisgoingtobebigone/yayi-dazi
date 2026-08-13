#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
SCRIPTS = SKILL_ROOT / "scripts"
DATA = SKILL_ROOT / "references" / "runtime-data"
MANIFEST = SKILL_ROOT / "references" / "runtime-manifest.json"
sys.path.insert(0, str(SCRIPTS))

from cn_oral_consult import (  # noqa: E402
    M01FactLedger,
    M09Catalog,
    M10Catalog,
    M11Orchestrator,
    calibrate_model_grader,
    deterministic_checks,
    full_triage,
    run_m02,
    run_m03,
    run_m04,
    run_m05,
    run_m06,
    run_m07,
    run_m08,
    run_m09,
    retrieve_m10,
)
from cn_oral_consult.m04 import CATALOG_PATH, M04KnowledgeStore  # noqa: E402
from cn_oral_consult.m08 import M08_RULES_PATH, load_m08_rules  # noqa: E402
from cn_oral_consult.m09 import DEFAULT_CATALOG_PATH as M09_PATH  # noqa: E402
from cn_oral_consult.m10 import DEFAULT_CATALOG_PATH as M10_PATH  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _route(primary: str, secondary: str | None = None) -> dict[str, Any]:
    modules = [primary] + ([secondary] if secondary else [])
    return {
        "primary_module": primary,
        "secondary_module": secondary,
        "route_status": "confirmed",
        "health_first": secondary == "M06" and primary != "M06",
        "offline_required": False,
        "retrieval_modules": modules,
        "route_history": [],
        "assembled_by": "M11",
    }


def _specialist_fact(module: str) -> dict[str, Any]:
    values = {
        "M02": ("M02-FLD-003", "冷水后仍不适一会儿"),
        "M03": ("M03-FLD-008", "感觉几颗牙有点松"),
        "M05": ("M05-FLD-006", "右下修复体吃东西时会晃"),
        "M06": ("M06-FLD-001", "上前牙不齐，希望改善笑容"),
        "M07": ("M07-FLD-001", "耳前关节响，张口时不舒服"),
    }
    field_id, value = values[module]
    return {
        "field_id": field_id,
        "value_status": "affirmed",
        "value": value,
        "source_type": "user_current",
        "basis_spans": [value],
    }


def evaluate() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assets = manifest.get("assets", [])
    checks["manifest_v2_covers_m00_to_m12"] = (
        manifest.get("schema_version") == "cn-oral-consult.runtime-manifest.v2"
        and manifest.get("module_coverage") == [f"M{number:02d}" for number in range(13)]
    )
    checks["all_manifest_assets_match_sha256"] = all(
        (SKILL_ROOT / item["path"]).is_file() and _sha256(SKILL_ROOT / item["path"]) == item["sha256"]
        for item in assets
    )
    checks["runtime_loads_only_bundled_catalog_paths"] = all(
        DATA in path.parents for path in (CATALOG_PATH, M08_RULES_PATH, M09_PATH, M10_PATH)
    )

    safety = full_triage(
        {
            "raw_user_text": "冷热不适已经三天",
            "ordinary_signals": {"pain_over_two_days": "yes"},
            "basis_by_signal": {"pain_over_two_days": "已经三天"},
        }
    )
    e0 = full_triage(
        {
            "raw_user_text": "现在喘不上气",
            "critical_signals": {"breathing_difficulty": "yes"},
            "basis_by_signal": {"breathing_difficulty": "喘不上气"},
        }
    )
    floor = full_triage(
        {
            "raw_user_text": "后来轻一点了",
            "prior_risk_floor_level": "U1",
            "ordinary_signals": {
                "mild_short_and_self_resolving": "yes",
                "all_upgrade_signals_denied": "yes",
                "understands_escalation_conditions": "yes",
            },
        }
    )
    checks["m00_triage_and_non_downgrade_work"] = (
        safety["effective_level"] == "N1" and e0["effective_level"] == "E0" and floor["effective_level"] == "U1"
    )

    ledger = M01FactLedger(episode_id="SELF-CHECK")
    ledger.record(
        [{"field_id": "M02-FLD-003", "value": "冷热不适", "status": "present", "source_type": "user_text", "source_span": "冷热不适"}],
        turn_id="T1",
    )
    ledger.record(
        [{"field_id": "M02-FLD-004", "value": "刚才表述有误", "status": "present", "source_type": "user_correction", "source_span": "刚才表述有误", "corrects_field_id": "M02-FLD-003"}],
        turn_id="T2",
    )
    checks["m01_ledger_preserves_correction_history"] = len(ledger.history) == 2 and len(ledger.correction_events) == 1

    m02 = run_m02(task="intake_support", user_task="冷热不适", facts=[_specialist_fact("M02")], safety_result=safety, route_result=_route("M02"))
    m03 = run_m03(task="intake_support", user_task="牙齿松动感", facts=[_specialist_fact("M03")], safety_result=safety, route_result=_route("M03"))
    m04 = run_m04(
        task="education",
        user_task="嘴里反复出现破损",
        facts=[{"field_id": "M04-FLD-003", "status": "reported", "value": "舌边有一处白色变化", "basis_span": "舌边有一处白色变化", "source": "user_text"}],
        safety_result=safety,
    )
    m05 = run_m05(task="intake_support", user_task="修复体松动", facts=[_specialist_fact("M05")], safety_result=safety, route_result=_route("M05"))
    m06 = run_m06(task="intake_support", user_task="牙齿排列美观", facts=[_specialist_fact("M06")], safety_result=safety, route_result=_route("M06"))
    m07 = run_m07(task="intake_support", user_task="关节响", facts=[_specialist_fact("M07")], safety_result=safety, route_result=_route("M07"), consultation_branch="tmj")
    checks["m02_to_m07_representative_calls_run"] = all(
        item.get("module") == module and item.get("status") == "ready_for_base_model"
        for module, item in zip(("M02", "M03", "M04", "M05", "M06", "M07"), (m02, m03, m04, m05, m06, m07), strict=True)
    )

    quality = {
        "file_integrity": 100, "target_coverage": 100, "focus_detail": 100, "exposure_color": 100,
        "view_pose": 100, "perspective": 100, "obstruction": 100, "comparability": 100,
    }
    m08 = run_m08(
        task="single_tooth_or_area",
        requested_by_module="M02",
        media={"media_id": "MEDIA-SELF-CHECK", "source_type": "user_upload", "user_goal": "记录可见变化"},
        quality_components=quality,
        observations=[],
        safety_result=safety,
        route_result=_route("M02"),
        consent_record={"authorized_source": True, "current_consultation_consent": True, "purpose_notice_acknowledged": True, "retention_notice_days": 30},
    )
    rules = load_m08_rules()
    checks["m08_uses_complete_bundled_rule_catalog"] = (
        m08.get("rules_schema_version") == rules.get("schema_version")
        and len(rules["task_codes"]) == 17
        and len(rules["rules"]) == 93
    )

    m09 = run_m09(
        task="treatment_background", requested_by_module="M05", category_ids=["M09-TRT-001"],
        safety_result=safety, route_result=_route("M05"), treatment_background_requested=True, internal_preview=True,
    )
    checks["m09_loads_all_90_treatment_categories"] = len(M09Catalog().all()) == 90 and m09["status"] == "ready_for_m11_generation"

    m10 = retrieve_m10(
        task="clinical_evidence", query="冷热敏感三天", fact_basis_spans=["冷热敏感已经三天"],
        fact_field_ids=["M02-FLD-003"], requested_by_module="M02", safety_result=safety,
        route_result=_route("M02"), entry_types=["DIS", "DXM", "PRB"], internal_preview=True,
    )
    m10_store = M10Catalog()
    checks["m10_loads_complete_unified_index"] = (
        len(m10_store.records) == 495 and len(m10_store.chunks) == 495 and bool(m10["retrieval_results"])
    )

    orchestrator = M11Orchestrator()
    m11 = orchestrator.process_turn(
        session_id="S1", episode_id="E1", turn_id="T1", raw_user_text="冷热不适已经三天",
        safety_result=safety,
        facts=[{"field_id": "M02-FLD-003", "value": "冷热不适", "status": "present", "source_type": "user_text", "source_span": "冷热不适"}],
        route_candidates=[{"module": "M02", "relevance_score_0_to_100": 92, "basis_spans": ["冷热不适"], "health_signal": True}],
        entry_mode="oral_health",
    )
    checks["m11_orchestrator_runs_with_bundled_adapters"] = m11["status"] == "ready_for_base_model" and m11["route"]["primary_module"] == "M02"

    eval_spec = json.loads((DATA / "m12_eval_spec.json").read_text(encoding="utf-8"))
    eval_contract = json.loads((DATA / "m12_eval_contract_v2_candidate.json").read_text(encoding="utf-8"))
    sample_case = {"reference_label": {"effective_level": "N1", "acceptable_primary_modules": ["M02"], "required_secondary_modules": [], "required_fact_spans": ["冷热不适"]}}
    sample_output = {"text": "仅凭远程信息不能确定原因，建议到医院口腔科评估。用户描述冷热不适。", "effective_level": "N1", "primary_module": "M02", "facts": ["冷热不适"]}
    m12 = deterministic_checks(sample_case, sample_output)
    calibration = calibrate_model_grader([{"human_label": "pass", "model_label": "pass"}])
    checks["m12_evaluator_and_bundled_contracts_run"] = (
        m12["passed"]
        and calibration["expert_reference_standard_decision_allowed"] is False
        and eval_spec["clinical_validity_claim_allowed"] is False
        and eval_contract["model_execution_authorized"] is False
    )

    counts = {
        "m04_entries": sum(len(M04KnowledgeStore().catalog[key]) for key in ("diseases", "lesions", "diagnostic_methods")),
        "m08_rules": len(rules["rules"]),
        "m09_categories": len(M09Catalog().all()),
        "m10_records": len(m10_store.records),
        "m10_chunks": len(m10_store.chunks),
    }
    checks["catalog_counts_match_approved_totals"] = counts == {"m04_entries": 142, "m08_rules": 93, "m09_categories": 90, "m10_records": 495, "m10_chunks": 495}
    checks["production_and_clinical_claims_remain_disabled"] = (
        manifest.get("production_enabled") is False and manifest.get("clinical_validity_claim_allowed") is False
    )
    return {
        "schema_version": "cn-oral-consult.full-runtime-self-check.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "check_count": len(checks),
        "passed_check_count": sum(checks.values()),
        "catalog_counts": counts,
        "module_coverage": manifest.get("module_coverage"),
        "production_enabled": False,
        "clinical_validity_claim_allowed": False,
    }


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)
