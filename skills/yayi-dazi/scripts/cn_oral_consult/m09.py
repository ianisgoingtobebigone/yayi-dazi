from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .runtime_paths import data_path


DEFAULT_CATALOG_PATH = data_path("m09_catalog.json")
MODULE_PRODUCTION_ENABLED = False

ALLOWED_TASKS = {"treatment_background", "category_comparison", "maintenance_background"}
ALLOWED_REQUESTING_MODULES = {f"M{number:02d}" for number in range(2, 8)}
ALL_M00_LEVELS = {"E0", "E1", "U1", "N1", "S0", "NEEDS_CLARIFICATION"}
HALT_LEVELS = {"E0", "E1"}
MAX_CATEGORIES_PER_RESPONSE = 3
CATEGORY_ID_PATTERN = re.compile(r"^M09-TRT-(?:0[0-8][0-9]|090)$")
INTERNAL_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])M09-TRT-\d{3}(?![A-Za-z0-9])")

FORBIDDEN_OUTPUT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?:你|您).{0,16}(?:应该|必须|需要|首选|最适合|更适合).{0,20}(?:治疗|手术|拔牙|根管|种植|正畸|用药|激素|抗生素)", "替当前用户选择治疗"),
    (r"建议(?:你|您).{0,16}(?:做|接受|进行|选择|服用|使用|停用|改用)", "生成个人治疗或用药指令"),
    (r"(?:每天|每日|每次|一日).{0,12}\d+(?:\.\d+)?\s*(?:次|片|粒|毫克|mg|g|ml|mL)", "输出剂量或频次"),
    (r"(?:连用|疗程|服用|使用).{0,10}\d+\s*(?:天|周|月)", "输出个体疗程"),
    (r"(?:用|选择).{0,12}(?:某品牌|品牌|型号)|(?:弓丝|根管锉|种植体).{0,12}(?:型号|参数)", "输出品牌、器械或参数"),
    (r"(?:先|然后|再).{0,18}(?:切开|钻开|磨除|刮治|缝合|穿刺|拔除).{0,18}(?:然后|再|最后)", "输出操作步骤"),
    (r"(?:保证|肯定|一定).{0,12}(?:治好|有效|成功)|成功率\s*\d+(?:\.\d+)?\s*%", "作出疗效保证"),
    (r"(?:最便宜|性价比最高|按价格排序|价格越高越好)", "按价格替代临床比较"),
    (r"(?:你|您)(?:就是|得了|患有)|(?:已经|可以)?确诊|(?:可以|能够|基本)排除", "把治疗背景建立在远程确诊上"),
    (r"(?<!\d)(?:911|999|111)(?!\d)|(?:NHS|urgent care|海外急诊)", "包含境外医疗服务入口"),
    (INTERNAL_ID_PATTERN.pattern, "向用户暴露内部治疗类别编号"),
)


class M09ContractError(ValueError):
    """Raised when M09 is used outside the approved treatment-background contract."""


class M09Catalog:
    def __init__(self, path: str | Path = DEFAULT_CATALOG_PATH) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.payload = payload
        self.production_enabled = bool(payload.get("production_enabled", False))
        entries = payload.get("treatment_categories", [])
        if not isinstance(entries, list):
            raise M09ContractError("M09 catalog treatment_categories must be a list")
        self._entries = {str(item["treatment_category_id"]): dict(item) for item in entries}

    def get(self, category_id: str) -> dict[str, Any] | None:
        item = self._entries.get(category_id)
        return dict(item) if item else None

    def all(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._entries.values()]


def _validate_safety_result(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        raise M09ContractError("M09_REQUIRES_M00_RESULT")
    level = str(value.get("effective_level", ""))
    if level not in ALL_M00_LEVELS:
        raise M09ContractError(f"unsupported M00 effective_level: {level}")
    basis = value.get("basis_from_user", [])
    if not isinstance(basis, list):
        raise M09ContractError("M00 basis_from_user must be a list")
    return {
        "effective_level": level,
        "risk_floor_level": value.get("risk_floor_level"),
        "basis_from_user": list(basis),
        "uncertainties": list(value.get("uncertainties", [])),
        "user_message_zh": value.get("user_message_zh"),
        "time_to_care": value.get("time_to_care"),
        "destination": value.get("destination"),
        "urgency_owned_by": "M00",
    }


def _validate_route(value: Mapping[str, Any] | None, requested_by_module: str) -> dict[str, Any]:
    if not value or value.get("assembled_by") != "M11":
        raise M09ContractError("M09_REQUIRES_M11_BUSINESS_ROUTE")
    forbidden = {"effective_level", "risk_floor_level", "time_to_care", "destination", "urgency"}
    overlap = set(value) & forbidden
    if overlap:
        raise M09ContractError(f"M11 route must not alter M00 fields: {sorted(overlap)}")
    primary = value.get("primary_module")
    secondary = value.get("secondary_module")
    if primary not in ALLOWED_REQUESTING_MODULES:
        raise M09ContractError(f"unsupported M11 primary_module: {primary}")
    if isinstance(secondary, list):
        raise M09ContractError("M11 may return at most one secondary_module")
    if secondary is not None and secondary not in ALLOWED_REQUESTING_MODULES:
        raise M09ContractError(f"unsupported M11 secondary_module: {secondary}")
    if requested_by_module not in {primary, secondary}:
        raise M09ContractError("requested_by_module must match the M11 primary or secondary module")
    return {
        "primary_module": primary,
        "secondary_module": secondary,
        "route_status": value.get("route_status"),
        "offline_required": bool(value.get("offline_required", False)),
        "assembled_by": "M11",
    }


def _base_envelope(status: str, task: str, safety: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "cn-dental-m09.output.v1",
        "module": "M09",
        "status": status,
        "task": task,
        "safety": dict(safety),
        "candidate_treatment_background": [],
        "blocked_categories": [],
        "next_guard": "M11",
        "m00_final_guard_required": True,
        "capability_boundary_zh": "本模块只提供非个体化治疗类别背景，不是诊断、处方或个人治疗方案",
    }


def _public_context(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "category_name_zh": item["canonical_name_zh"],
        "framing_zh": f"面诊后可能讨论的类别之一是{item['canonical_name_zh']}，具体取决于线下检查和专业共同决策。",
        "general_objectives": list(item.get("clinical_objectives", [])),
        "candidate_contexts_for_education": list(item.get("candidate_contexts_for_education", [])),
        "offline_decision_requirements": list(item.get("required_clinical_evidence", [])),
        "decision_dependencies": list(item.get("decision_dependencies", [])),
        "possible_alternatives": list(item.get("possible_alternatives", [])),
        "maintenance_or_follow_up": list(item.get("maintenance_or_follow_up", [])),
        "source_refs": list(item.get("source_refs", [])),
        "cannot_determine_for_current_user": [
            "是否适合该治疗类别",
            "具体药物、材料、器械、参数或操作方式",
            "预期疗效、风险、周期和费用",
        ],
        "retrieval_relation": "general_background_only",
    }


def run_m09(
    *,
    task: str,
    requested_by_module: str,
    category_ids: Sequence[str],
    safety_result: Mapping[str, Any] | None,
    route_result: Mapping[str, Any] | None,
    treatment_background_requested: bool,
    age_group: str = "adult",
    internal_preview: bool = False,
    catalog: M09Catalog | None = None,
) -> dict[str, Any]:
    """Build an M11-bound treatment-background package without choosing treatment."""
    if task not in ALLOWED_TASKS:
        raise M09ContractError(f"unsupported M09 task: {task}")
    if requested_by_module not in ALLOWED_REQUESTING_MODULES:
        raise M09ContractError(f"unsupported requesting module: {requested_by_module}")
    safety = _validate_safety_result(safety_result)
    level = safety["effective_level"]
    if level in HALT_LEVELS:
        result = _base_envelope("halted_by_m00", task, safety)
        result["next_guard"] = "M00"
        return result
    if level == "NEEDS_CLARIFICATION":
        result = _base_envelope("waiting_for_m00_clarification", task, safety)
        result["next_guard"] = "M00"
        return result
    if level == "U1":
        result = _base_envelope("urgent_routing_only", task, safety)
        result["next_guard"] = "M00"
        return result
    if age_group != "adult":
        return _base_envelope("out_of_adult_scope", task, safety)
    route = _validate_route(route_result, requested_by_module)
    if not treatment_background_requested:
        result = _base_envelope("treatment_background_not_requested", task, safety)
        result["route"] = route
        return result
    if not category_ids:
        raise M09ContractError("M09 requires at least one treatment category")
    if len(category_ids) > MAX_CATEGORIES_PER_RESPONSE:
        raise M09ContractError("M09 allows at most three tightly related categories per response")
    if len(set(category_ids)) != len(category_ids):
        raise M09ContractError("duplicate treatment category IDs")
    if any(not CATEGORY_ID_PATTERN.fullmatch(str(item)) for item in category_ids):
        raise M09ContractError("unsupported M09 treatment category ID")

    store = catalog or M09Catalog()
    if not internal_preview and not (MODULE_PRODUCTION_ENABLED and store.production_enabled):
        result = _base_envelope("module_disabled_pending_m12_evaluation", task, safety)
        result["route"] = route
        return result

    approved: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    for category_id in category_ids:
        item = store.get(str(category_id))
        if item is None:
            raise M09ContractError(f"unknown treatment category: {category_id}")
        if item.get("review_status") != "approved":
            blocked.append({"category_id": str(category_id), "reason": "not_approved"})
            continue
        if requested_by_module not in item.get("owning_modules", []):
            blocked.append({"category_id": str(category_id), "reason": "requesting_module_mismatch"})
            continue
        if item.get("adult_runtime_scope") == "out_of_adult_runtime":
            blocked.append({"category_id": str(category_id), "reason": "outside_adult_runtime_scope"})
            continue
        if not item.get("source_refs"):
            blocked.append({"category_id": str(category_id), "reason": "missing_source_refs"})
            continue
        approved.append(_public_context(item))

    result = _base_envelope("ready_for_m11_generation" if approved else "blocked_knowledge_context", task, safety)
    result["route"] = route
    result["candidate_treatment_background"] = approved
    result["blocked_categories"] = blocked
    result["generation_constraints"] = [
        "只使用条件式表达，不把类别写成当前用户选择",
        "先保留M00的紧迫度和就诊行动，再说明治疗背景",
        "不得补充目录和来源中没有的药物、器械、参数或操作",
        "输出后必须通过M11和M00最终复核",
    ]
    return result


def guard_user_output(text: str) -> None:
    compact = " ".join(str(text).split())
    for pattern, reason in FORBIDDEN_OUTPUT_PATTERNS:
        if re.search(pattern, compact, flags=re.IGNORECASE):
            raise M09ContractError(f"M09_OUTPUT_BLOCKED: {reason}")
    if "可能讨论" not in compact or not re.search(r"取决于.{0,18}(?:检查|评估|专业)", compact):
        raise M09ContractError("M09_OUTPUT_BLOCKED: missing conditional treatment framing")
    if not re.search(r"不是.{0,12}(?:个人治疗方案|诊断|处方)", compact):
        raise M09ContractError("M09_OUTPUT_BLOCKED: missing capability boundary")
