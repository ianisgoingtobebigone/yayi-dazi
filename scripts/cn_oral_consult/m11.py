from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .m02 import run_m02
from .m03 import run_m03
from .m04 import run_m04
from .m05 import run_m05
from .m06 import run_m06
from .m07 import run_m07
from .m08 import run_m08
from .m09 import run_m09
from .m10 import retrieve_m10


SCHEMA_VERSION = "cn-dental-m11.output.v1"
MODULE_PRODUCTION_ENABLED = False

LEVEL_ORDER = {"S0": 0, "N1": 1, "U1": 2, "E1": 3, "E0": 4}
ALL_M00_LEVELS = set(LEVEL_ORDER) | {"NEEDS_CLARIFICATION"}
HALT_LEVELS = {"E0", "E1"}
SPECIALIST_MODULES = {f"M{number:02d}" for number in range(2, 8)}
AUXILIARY_MODULES = {"M08", "M09", "M10"}
ALL_CALLABLE_MODULES = SPECIALIST_MODULES | AUXILIARY_MODULES
ROUTE_STATUSES = {"confirmed", "needs_clarification", "route_unresolved"}
ENTRY_MODES = {"oral_health", "dentofacial_aesthetic", "mixed", "uncertain"}
FACT_SOURCE_TYPES = {"user_text", "user_photo", "existing_record", "user_correction"}
FACT_STATUSES = {"present", "denied", "unknown", "historical"}
CLAIM_SOURCE_TYPES = {
    "user_fact",
    "retrieved_evidence",
    "model_prior",
    "runtime_inference",
    "offline_required",
}
EVIDENCE_RELATIONS = {
    "supports",
    "conflicts",
    "missing_clinician_evidence",
    "context_only",
    "retrieval_gap",
}
FACT_ID_PATTERN = re.compile(r"M(?:0[1-8])-FLD-\d{3}")
INTERNAL_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])M(?:0[0-9]|1[0-2])-(?:FLD|DLG|FLO|RUL|OUT|DIS|DXM|LSN|MNT|PRB|TRT|CHK|EVD)-[A-Z0-9-]+")
LOCAL_PATH_PATTERN = re.compile(r"(?:/Users/|/mnt/data/|[A-Za-z]:\\Users\\)")
FOREIGN_PATHWAY_PATTERN = re.compile(r"(?<!\d)(?:911|999|111)(?!\d)|\bNHS\b|urgent care", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
MEDICAL_CONFIDENCE_PATTERN = re.compile(r"(?:患有|诊断|确诊|疾病).{0,12}\d{1,3}(?:\.\d+)?%")

FORBIDDEN_DRAFT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:已经|可以|基本|能够)?确诊(?:为|是)?|肯定是|就是.{0,10}(?:病|炎|癌)"), "远程内容不得作确定诊断"),
    (re.compile(r"(?:最适合你|你必须|你应该).{0,18}(?:拔牙|根管|正畸|手术|种植|用药)"), "不得选择个人治疗方案"),
    (re.compile(r"\d+(?:\.\d+)?\s*(?:mg|毫克|片|粒).{0,16}(?:每日|一天|每次|疗程)"), "不得提供个体药物剂量或疗程"),
    (re.compile(r"(?:自行|自己).{0,12}(?:调整|磨除|切开|放脓|复位|加力|摘除装置)"), "不得提供器械或操作步骤"),
    (re.compile(r"照片.{0,12}(?:确诊|证明|显示你患有|判断为)"), "普通照片不得用于确诊"),
)


class M11ContractError(ValueError):
    """Raised when a main-Agent request violates the approved orchestration contract."""


@dataclass
class M11EpisodeState:
    episode_id: str
    risk_floor_level: str | None = None
    clarification_used: bool = False
    turn_count: int = 0
    fact_ledger: dict[str, dict[str, Any]] = field(default_factory=dict)
    fact_history: list[dict[str, Any]] = field(default_factory=list)
    correction_events: list[dict[str, Any]] = field(default_factory=list)
    route_history: list[dict[str, Any]] = field(default_factory=list)
    current_route: dict[str, Any] | None = None
    route_clarification_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _more_urgent(left: str | None, right: str | None) -> str | None:
    values = [item for item in (left, right) if item in LEVEL_ORDER]
    return max(values, key=LEVEL_ORDER.__getitem__) if values else None


def validate_safety_result(value: Mapping[str, Any] | None, *, prior_floor: str | None = None) -> dict[str, Any]:
    if not value:
        raise M11ContractError("M11_REQUIRES_CURRENT_M00_RESULT")
    effective = str(value.get("effective_level", ""))
    if effective not in ALL_M00_LEVELS:
        raise M11ContractError(f"unsupported M00 effective_level: {effective}")
    floor = value.get("risk_floor_level")
    if floor is not None and str(floor) not in LEVEL_ORDER:
        raise M11ContractError("unsupported M00 risk_floor_level")
    floor = str(floor) if floor is not None else None
    candidate = str(value.get("candidate_level", ""))
    if candidate not in ALL_M00_LEVELS:
        raise M11ContractError(f"unsupported M00 candidate_level: {candidate}")
    basis = value.get("basis_from_user", [])
    uncertainties = value.get("uncertainties", [])
    if not isinstance(basis, list) or not isinstance(uncertainties, list):
        raise M11ContractError("M00 basis_from_user and uncertainties must be lists")
    required_floor = _more_urgent(prior_floor, floor)
    if effective in LEVEL_ORDER and required_floor and LEVEL_ORDER[effective] < LEVEL_ORDER[required_floor]:
        raise M11ContractError("M00 effective_level is lower than the recorded risk floor")
    if effective == "NEEDS_CLARIFICATION" and prior_floor in HALT_LEVELS:
        raise M11ContractError("clarification cannot reopen ordinary flow after an E0/E1 floor")
    if effective == "NEEDS_CLARIFICATION" and candidate != "NEEDS_CLARIFICATION":
        raise M11ContractError("M00 clarification requires a matching candidate_level")
    if effective in LEVEL_ORDER and candidate in LEVEL_ORDER:
        expected = _more_urgent(candidate, required_floor)
        if effective != expected:
            raise M11ContractError("M00 effective_level must equal the more urgent candidate and risk floor")
    return {
        "candidate_level": candidate,
        "risk_floor_level": required_floor,
        "effective_level": effective,
        "next_state": value.get("next_state"),
        "dialogue_action": value.get("dialogue_action"),
        "time_to_care": value.get("time_to_care"),
        "destination": value.get("destination") or value.get("destination_types_zh"),
        "basis_from_user": list(basis),
        "uncertainties": list(uncertainties),
        "clarification_question_zh": value.get("clarification_question_zh"),
        "user_message_zh": value.get("user_message_zh"),
        "reviewed_by": "M00",
    }


def validate_facts(items: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items or []):
        field_id = str(item.get("field_id", ""))
        if not FACT_ID_PATTERN.fullmatch(field_id):
            raise M11ContractError(f"fact {index} requires an M01-M08 field_id")
        if field_id in seen:
            raise M11ContractError(f"duplicate fact field_id in one turn: {field_id}")
        seen.add(field_id)
        source_type = str(item.get("source_type", ""))
        status = str(item.get("status", ""))
        if source_type not in FACT_SOURCE_TYPES or status not in FACT_STATUSES:
            raise M11ContractError(f"fact {field_id} has unsupported source_type or status")
        source_span = str(item.get("source_span", "")).strip()
        if source_type in {"user_text", "user_correction"} and not source_span:
            raise M11ContractError(f"fact {field_id} must preserve the user's source span")
        corrects_field_id = item.get("corrects_field_id")
        if source_type == "user_correction":
            if not isinstance(corrects_field_id, str) or not FACT_ID_PATTERN.fullmatch(corrects_field_id):
                raise M11ContractError(f"correction fact {field_id} requires a valid corrects_field_id")
        elif corrects_field_id is not None:
            raise M11ContractError(f"fact {field_id} may use corrects_field_id only for user_correction")
        facts.append(
            {
                "field_id": field_id,
                "value": item.get("value", "unknown"),
                "status": status,
                "source_type": source_type,
                "source_span": source_span,
                "observed_at": item.get("observed_at"),
                "uncertainty": item.get("uncertainty"),
                "corrects_field_id": corrects_field_id,
            }
        )
    return facts


def assemble_route(
    candidates: Sequence[Mapping[str, Any]] | None,
    *,
    entry_mode: str,
    prior_route: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate model-proposed business routes; scores rank routing only, not medicine."""
    if entry_mode not in ENTRY_MODES:
        raise M11ContractError(f"unsupported entry_mode: {entry_mode}")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(candidates or []):
        module = str(item.get("module", ""))
        if module not in SPECIALIST_MODULES:
            raise M11ContractError(f"route candidate {index} must be M02-M07")
        score = item.get("relevance_score_0_to_100")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= float(score) <= 100:
            raise M11ContractError(f"route candidate {module} requires a numeric 0-100 relevance score")
        spans = item.get("basis_spans", [])
        if not isinstance(spans, list) or not spans or not all(str(span).strip() for span in spans):
            raise M11ContractError(f"route candidate {module} requires user-text basis_spans")
        normalized.append(
            {
                "module": module,
                "relevance_score_0_to_100": round(float(score), 2),
                "score_meaning": "business_routing_relevance_only_not_medical_confidence",
                "basis_spans": [str(span) for span in spans],
                "health_signal": bool(item.get("health_signal", module != "M06")),
                "cross_module_required": bool(item.get("cross_module_required", False)),
                "offline_required": bool(item.get("offline_required", False)),
            }
        )
    normalized.sort(key=lambda item: (-item["relevance_score_0_to_100"], item["module"]))

    if not normalized:
        return {
            "primary_module": None,
            "secondary_module": None,
            "route_status": "route_unresolved",
            "health_first": entry_mode == "mixed",
            "offline_required": False,
            "retrieval_modules": [],
            "route_candidates": [],
            "route_uncertainty": ["没有具备用户原话依据的专业模块候选"],
            "route_history": list((prior_route or {}).get("route_history", [])),
            "assembled_by": "M11",
        }

    health_candidates = [item for item in normalized if item["health_signal"] and item["module"] != "M06"]
    if entry_mode == "mixed" and not health_candidates:
        return {
            "primary_module": None,
            "secondary_module": "M06" if any(item["module"] == "M06" for item in normalized) else None,
            "route_status": "needs_clarification",
            "health_first": True,
            "offline_required": any(item["offline_required"] for item in normalized),
            "retrieval_modules": [],
            "route_candidates": normalized,
            "route_uncertainty": ["混合需求尚未确定健康问题所属专业模块"],
            "route_history": list((prior_route or {}).get("route_history", [])),
            "assembled_by": "M11",
        }

    ordered = health_candidates + [item for item in normalized if item not in health_candidates] if entry_mode == "mixed" else normalized
    primary = ordered[0]
    second = next((item for item in ordered[1:] if item["module"] != primary["module"]), None)
    ambiguous = bool(second and abs(primary["relevance_score_0_to_100"] - second["relevance_score_0_to_100"]) <= 5.0)
    if ambiguous and not primary["cross_module_required"] and not second["cross_module_required"]:
        return {
            "primary_module": None,
            "secondary_module": None,
            "route_status": "needs_clarification",
            "health_first": entry_mode == "mixed",
            "offline_required": primary["offline_required"] or second["offline_required"],
            "retrieval_modules": [],
            "route_candidates": normalized,
            "route_uncertainty": ["前两项路由工程相关度差值不超过5.0，需要一次改变分道的澄清"],
            "route_history": list((prior_route or {}).get("route_history", [])),
            "assembled_by": "M11",
        }

    secondary = None
    if second and second["relevance_score_0_to_100"] >= 60.0 and (
        primary["cross_module_required"] or second["cross_module_required"] or entry_mode == "mixed"
    ):
        secondary = second["module"]
    modules = [primary["module"]] + ([secondary] if secondary else [])
    history = list((prior_route or {}).get("route_history", []))
    history.append({"primary_module": primary["module"], "secondary_module": secondary, "reason_spans": primary["basis_spans"]})
    return {
        "primary_module": primary["module"],
        "secondary_module": secondary,
        "route_status": "confirmed",
        "health_first": entry_mode == "mixed",
        "offline_required": any(item["offline_required"] for item in normalized if item["module"] in modules),
        "retrieval_modules": modules,
        "route_candidates": normalized,
        "route_uncertainty": [],
        "route_history": history,
        "assembled_by": "M11",
    }


def build_execution_plan(
    *,
    safety: Mapping[str, Any],
    route: Mapping[str, Any],
    photo_requested: bool,
    treatment_background_requested: bool,
    literature_requested: bool,
) -> dict[str, Any]:
    level = str(safety["effective_level"])
    steps: list[dict[str, Any]] = [
        {"step": "M00_CURRENT_TURN_RECHECK", "importance": "safety_critical"},
        {"step": "M01_FACT_LEDGER_UPDATE", "importance": "integrity_critical"},
    ]
    if level in HALT_LEVELS:
        steps.append({"step": "EXECUTE_M00_ROUTE_AND_HALT", "importance": "safety_critical"})
    elif level == "NEEDS_CLARIFICATION":
        steps.append({"step": "ASK_ONE_M00_CLARIFICATION", "importance": "safety_critical"})
    elif level == "U1":
        steps.extend(
            [
                {"step": "SHOW_M00_ACTION_WITHOUT_DELAY", "importance": "safety_critical"},
                {"step": "OPTIONAL_ONE_DESTINATION_CHANGING_QUESTION", "importance": "safety_critical"},
            ]
        )
    elif route.get("route_status") != "confirmed":
        steps.append({"step": "ASK_ONE_ROUTE_CHANGING_QUESTION", "importance": "core"})
    else:
        for module in (route.get("primary_module"), route.get("secondary_module")):
            if module:
                steps.append({"step": f"CALL_{module}", "importance": "clinical_core"})
        if photo_requested:
            steps.extend(
                [
                    {"step": "CALL_M08", "importance": "conditional_safety_critical"},
                    {"step": "RETURN_NEW_IMAGE_FACTS_TO_M00", "importance": "safety_critical"},
                ]
            )
        steps.append({"step": "CALL_M10_CLINICAL_EVIDENCE", "importance": "evidence_core"})
        if literature_requested:
            steps.append({"step": "CALL_M10_LITERATURE_RECOMMENDATION", "importance": "conditional_support"})
        if treatment_background_requested:
            steps.append({"step": "CALL_M09", "importance": "conditional_boundary_sensitive"})
        steps.extend(
            [
                {"step": "CALL_BASE_MODEL_FOR_DRAFT", "importance": "core"},
                {"step": "M11_FACT_SOURCE_BOUNDARY_REVIEW", "importance": "integrity_critical"},
                {"step": "M00_FINAL_GUARD", "importance": "safety_critical"},
            ]
        )
    return {
        "steps": steps,
        "question_policy": {"max_blocks_this_turn": 1, "max_tightly_related_points_per_block": 3},
        "ordinary_modules_suspended": level in HALT_LEVELS | {"U1", "NEEDS_CLARIFICATION"},
        "production_enabled": False,
        "production_gate": "M12_NOT_COMPLETED",
    }


def build_model_packet(
    *,
    raw_user_text: str,
    facts: Sequence[Mapping[str, Any]],
    safety: Mapping[str, Any],
    route: Mapping[str, Any],
    module_outputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "cn-dental-m11.model-request.v1",
        "base_model_required": True,
        "raw_user_text": raw_user_text,
        "user_facts": [dict(item) for item in facts],
        "m00_safety": dict(safety),
        "business_route": dict(route),
        "module_context": [dict(item) for item in module_outputs],
        "required_claim_source_types": sorted(CLAIM_SOURCE_TYPES),
        "required_output_sections": ["安全行动", "用户事实摘要", "不确定性与线下确认事项", "就诊方向", "能力边界"],
        "conditional_sections": ["照片可见征象与局限", "治疗类别背景", "文献推荐"],
        "prohibitions": [
            "不得确诊或输出疾病概率",
            "不得选择个人治疗方案、药物剂量疗程或器械手术步骤",
            "不得把模型既有知识伪装成教材或指南来源",
            "不得把unknown写成no或把未见照片写成征象不存在",
            "不得输出内部编号、本地文件路径、教材页面或境外服务入口",
        ],
        "retrieved_content_trust": "reference_only",
        "next_guard": "M11",
    }


def review_model_draft(
    draft: Mapping[str, Any],
    *,
    facts: Sequence[Mapping[str, Any]],
    safety: Mapping[str, Any],
) -> dict[str, Any]:
    text = str(draft.get("text", "")).strip()
    claims = draft.get("claims", [])
    violations: list[dict[str, Any]] = []
    if not text:
        violations.append({"code": "EMPTY_DRAFT", "reason": "基础模型草稿为空"})
    if not isinstance(claims, list):
        raise M11ContractError("draft claims must be a list")
    if not claims:
        violations.append({"code": "CLAIM_PROVENANCE_MISSING", "reason": "草稿未提交可审核的主张来源记录"})
    known_fact_ids = {str(item["field_id"]) for item in facts}
    reviewed_claims: list[dict[str, Any]] = []
    for index, claim in enumerate(claims):
        source_type = str(claim.get("source_type", ""))
        claim_text = str(claim.get("text", "")).strip()
        if source_type not in CLAIM_SOURCE_TYPES or not claim_text:
            violations.append({"code": "INVALID_CLAIM", "claim_index": index, "reason": "主张缺少文本或来源类型"})
            continue
        field_ids = [str(item) for item in claim.get("fact_field_ids", [])]
        source_refs = list(claim.get("source_refs", []))
        relation = claim.get("relation_to_user_facts")
        if source_type == "user_fact" and (not field_ids or not set(field_ids) <= known_fact_ids):
            violations.append({"code": "UNTRACEABLE_USER_FACT", "claim_index": index, "reason": "用户事实无法回到M01-M08字段"})
        if source_type == "retrieved_evidence":
            if not source_refs:
                violations.append({"code": "MISSING_EVIDENCE_SOURCE", "claim_index": index, "reason": "检索证据没有来源"})
            if relation not in EVIDENCE_RELATIONS:
                violations.append({"code": "MISSING_EVIDENCE_RELATION", "claim_index": index, "reason": "证据与用户事实关系未显式确定"})
        if source_type in {"model_prior", "runtime_inference"} and source_refs:
            violations.append({"code": "MODEL_PRIOR_DISGUISED_AS_SOURCE", "claim_index": index, "reason": "模型补充推理不得携带伪来源"})
        if source_type == "runtime_inference" and not claim.get("uncertainty_zh"):
            violations.append({"code": "UNLABELED_INFERENCE", "claim_index": index, "reason": "运行推断未表达不确定性"})
        reviewed_claims.append(
            {
                "text": claim_text,
                "source_type": source_type,
                "fact_field_ids": field_ids,
                "source_refs": source_refs,
                "relation_to_user_facts": relation,
                "uncertainty_zh": claim.get("uncertainty_zh"),
            }
        )

    for pattern, reason in FORBIDDEN_DRAFT_PATTERNS:
        if match := pattern.search(text):
            violations.append({"code": "BOUNDARY_VIOLATION", "reason": reason, "matched": match.group(0)})
    for pattern, code, reason in (
        (INTERNAL_ID_PATTERN, "INTERNAL_ID_EXPOSED", "不得展示内部编号"),
        (LOCAL_PATH_PATTERN, "LOCAL_PATH_EXPOSED", "不得展示内部文件路径"),
        (FOREIGN_PATHWAY_PATTERN, "NON_CHINA_PATHWAY", "不得展示境外服务入口或电话号码"),
        (PHONE_PATTERN, "PERSONAL_DATA_EXPOSED", "不得输出个人电话号码"),
        (MEDICAL_CONFIDENCE_PATTERN, "MEDICAL_CONFIDENCE_INVENTED", "不得给出疾病或诊断置信百分比"),
    ):
        if match := pattern.search(text):
            violations.append({"code": code, "reason": reason, "matched": match.group(0)})

    level = str(safety["effective_level"])
    if level in HALT_LEVELS and not re.search(r"立即|马上|急诊|尽快前往", text):
        violations.append({"code": "M00_ACTION_MISSING", "reason": "E0/E1草稿未保留紧急行动"})
    if level == "U1" and not re.search(r"24\s*小时|当天|尽快", text):
        violations.append({"code": "M00_ACTION_MISSING", "reason": "U1草稿未保留24小时内行动"})
    if level not in HALT_LEVELS and not re.search(r"不能|无法|待确认|需.{0,4}(?:面诊|检查)|不能替代", text):
        violations.append({"code": "UNCERTAINTY_MISSING", "reason": "草稿未明确远程不确定性或线下确认边界"})

    passed = not violations
    return {
        "passed": passed,
        "status": "ready_for_m00_final_guard" if passed else "regenerate_required",
        "violations": violations,
        "reviewed_claims": reviewed_claims,
        "approved_text": text if passed else None,
        "m00_final_guard_request": {
            "operation": "final_guard",
            "draft_text": text if passed else None,
            "risk_floor_level": safety.get("risk_floor_level"),
            "effective_level": level,
        },
        "reviewed_by": "M11",
    }


def validate_final_guard(value: Mapping[str, Any] | None, *, safety: Mapping[str, Any]) -> dict[str, Any]:
    if not value:
        return {"passed": False, "status": "awaiting_m00_final_guard", "user_output": None}
    if value.get("operation") != "final_guard" or value.get("reviewed_by") != "M00":
        raise M11ContractError("final guard must be returned by M00")
    if not bool(value.get("passed")):
        return {"passed": False, "status": "blocked_by_m00_final_guard", "user_output": None}
    final_level = str(value.get("effective_level", ""))
    expected = str(safety["effective_level"])
    floor = safety.get("risk_floor_level")
    if final_level not in LEVEL_ORDER or (expected in LEVEL_ORDER and LEVEL_ORDER[final_level] < LEVEL_ORDER[expected]):
        raise M11ContractError("M00 final guard lowered the current effective level")
    if floor in LEVEL_ORDER and LEVEL_ORDER[final_level] < LEVEL_ORDER[str(floor)]:
        raise M11ContractError("M00 final guard lowered the recorded risk floor")
    return {"passed": True, "status": "release_blocked_pending_m12", "user_output": None, "effective_level": final_level}


class M11Orchestrator:
    """Stateful, safety-first coordinator. It prepares and audits; the base model writes."""

    def __init__(self, adapters: Mapping[str, Callable[..., dict[str, Any]]] | None = None) -> None:
        self.states: dict[str, M11EpisodeState] = {}
        self.adapters: dict[str, Callable[..., dict[str, Any]]] = {
            "M02": run_m02,
            "M03": run_m03,
            "M04": run_m04,
            "M05": run_m05,
            "M06": run_m06,
            "M07": run_m07,
            "M08": run_m08,
            "M09": run_m09,
            "M10": retrieve_m10,
        }
        self.adapters.update(adapters or {})

    def reset(self, session_id: str) -> None:
        self.states.pop(session_id, None)

    @staticmethod
    def _update_fact_ledger(state: M11EpisodeState, facts: Sequence[Mapping[str, Any]], *, turn_id: str) -> None:
        """Keep current facts and an append-only audit trail; corrections never erase the original."""
        available = set(state.fact_ledger) | {str(item["field_id"]) for item in facts}
        for fact in facts:
            fact_id = str(fact["field_id"])
            corrects = fact.get("corrects_field_id")
            if fact["source_type"] == "user_correction":
                if corrects not in available or corrects not in state.fact_ledger:
                    raise M11ContractError(f"correction fact {fact_id} refers to an unavailable prior fact")
                state.correction_events.append(
                    {
                        "turn_id": turn_id,
                        "original_fact": dict(state.fact_ledger[str(corrects)]),
                        "correction_fact": dict(fact),
                        "requires_m00_correction_recalculation": True,
                    }
                )
            previous = state.fact_ledger.get(fact_id)
            if previous is not None:
                state.fact_history.append({"turn_id": turn_id, "superseded_fact": dict(previous)})
            state.fact_ledger[fact_id] = dict(fact)
            state.fact_history.append({"turn_id": turn_id, "recorded_fact": dict(fact)})

    @staticmethod
    def _validate_call_sequence(calls: Sequence[Mapping[str, Any]]) -> None:
        modules = [str(item.get("module", "")) for item in calls]
        if "M08" in modules:
            image_index = modules.index("M08")
            if any(module in {"M09", "M10"} for module in modules[:image_index]):
                raise M11ContractError("M08 must run before M09/M10 so new image facts can return to M00")
        if "M09" in modules and "M10" in modules and modules.index("M09") < modules.index("M10"):
            raise M11ContractError("M10 evidence must run before M09 treatment background")

    def _execute_calls(
        self,
        calls: Sequence[Mapping[str, Any]],
        *,
        safety: Mapping[str, Any],
        route: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None, list[str]]:
        outputs: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        m00_recheck_reason: str | None = None
        deferred_modules: list[str] = []
        allowed = {route.get("primary_module"), route.get("secondary_module")} | AUXILIARY_MODULES
        for call_index, call in enumerate(calls):
            module = str(call.get("module", ""))
            if module not in allowed or module not in ALL_CALLABLE_MODULES:
                raise M11ContractError(f"module call is outside the confirmed M11 route: {module}")
            adapter = self.adapters.get(module)
            if adapter is None:
                failures.append(
                    {
                        "module": module,
                        "status": "adapter_not_available_without_safety_downgrade",
                        "attempts": 0,
                        "error_class": "AdapterNotAvailable",
                        "fallback": "preserve_M00_action_and_recommend_professional_assessment",
                    }
                )
                continue
            kwargs = dict(call.get("kwargs", {}))
            kwargs["safety_result"] = safety
            if module != "M04":
                kwargs["route_result"] = route
            attempts = 0
            while True:
                attempts += 1
                try:
                    result = adapter(**kwargs)
                    if not isinstance(result, dict):
                        raise TypeError("module output must be a mapping")
                    outputs.append(result)
                    if bool(result.get("m00_recheck_required")):
                        m00_recheck_reason = "image_facts" if module == "M08" else "structured_safety_facts"
                        deferred_modules = [str(item.get("module", "")) for item in calls[call_index + 1 :]]
                    break
                except Exception as exc:  # adapter boundary: errors are converted to safe, non-sensitive records
                    is_contract_error = exc.__class__.__name__.endswith("ContractError") or isinstance(exc, (TypeError, ValueError))
                    if attempts == 1 and not is_contract_error:
                        continue
                    failures.append(
                        {
                            "module": module,
                            "status": "failed_without_safety_downgrade",
                            "attempts": attempts,
                            "error_class": exc.__class__.__name__,
                            "fallback": "preserve_M00_action_and_recommend_professional_assessment",
                        }
                    )
                    break
            if m00_recheck_reason:
                break
        return outputs, failures, m00_recheck_reason, deferred_modules

    def process_turn(
        self,
        *,
        session_id: str,
        episode_id: str,
        turn_id: str,
        raw_user_text: str,
        safety_result: Mapping[str, Any] | None,
        facts: Sequence[Mapping[str, Any]] | None,
        route_candidates: Sequence[Mapping[str, Any]] | None,
        entry_mode: str,
        module_calls: Sequence[Mapping[str, Any]] | None = None,
        photo_requested: bool = False,
        treatment_background_requested: bool = False,
        literature_requested: bool = False,
        model_draft: Mapping[str, Any] | None = None,
        final_guard_result: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not session_id or not episode_id or not turn_id or not str(raw_user_text).strip():
            raise M11ContractError("session_id, episode_id, turn_id and raw_user_text are required")
        state = self.states.get(session_id)
        if state is None or state.episode_id != episode_id:
            state = M11EpisodeState(episode_id=episode_id)
            self.states[session_id] = state
        safety = validate_safety_result(safety_result, prior_floor=state.risk_floor_level)
        if safety["effective_level"] in LEVEL_ORDER:
            state.risk_floor_level = _more_urgent(state.risk_floor_level, str(safety["effective_level"]))
            safety["risk_floor_level"] = state.risk_floor_level
        validated_facts = validate_facts(facts)
        self._update_fact_ledger(state, validated_facts, turn_id=turn_id)
        route = assemble_route(route_candidates, entry_mode=entry_mode, prior_route=state.current_route)
        ordinary_flow_allowed = safety["effective_level"] not in HALT_LEVELS | {"U1", "NEEDS_CLARIFICATION"}
        if route["route_status"] == "needs_clarification" and ordinary_flow_allowed:
            if state.route_clarification_used:
                route["route_status"] = "route_unresolved"
                route["route_uncertainty"].append("一次分道澄清已使用，保留不确定性并转通用口腔专业评估")
            else:
                state.route_clarification_used = True
        state.current_route = route
        state.route_history = list(route["route_history"])
        state.turn_count += 1
        if safety["effective_level"] == "NEEDS_CLARIFICATION":
            if state.clarification_used:
                raise M11ContractError("M00 clarification may be used only once for the same ambiguous danger signal")
            state.clarification_used = True

        plan = build_execution_plan(
            safety=safety,
            route=route,
            photo_requested=photo_requested,
            treatment_background_requested=treatment_background_requested,
            literature_requested=literature_requested,
        )
        calls = list(module_calls or [])
        self._validate_call_sequence(calls)
        if safety["effective_level"] in HALT_LEVELS | {"U1", "NEEDS_CLARIFICATION"} and calls:
            raise M11ContractError("ordinary module calls are forbidden at the current M00 level")
        if route["route_status"] != "confirmed" and calls:
            raise M11ContractError("module calls require a confirmed M11 route")
        if calls:
            module_outputs, module_failures, m00_recheck_reason, deferred_modules = self._execute_calls(
                calls, safety=safety, route=route
            )
        else:
            module_outputs, module_failures, m00_recheck_reason, deferred_modules = [], [], None, []
        if m00_recheck_reason and (model_draft is not None or final_guard_result is not None):
            raise M11ContractError("new structured safety facts must return to M00 before model drafting or final guard")
        packet = None
        if not m00_recheck_reason:
            packet = build_model_packet(
                raw_user_text=raw_user_text,
                facts=list(state.fact_ledger.values()),
                safety=safety,
                route=route,
                module_outputs=module_outputs,
            )
        draft_review = review_model_draft(model_draft, facts=list(state.fact_ledger.values()), safety=safety) if model_draft else None
        final_guard = None
        if draft_review and draft_review["passed"]:
            final_guard = validate_final_guard(final_guard_result, safety=safety)
        status = "ready_for_base_model"
        if safety["effective_level"] in HALT_LEVELS:
            status = "halted_by_m00"
        elif safety["effective_level"] == "NEEDS_CLARIFICATION":
            status = "waiting_for_m00_clarification"
        elif safety["effective_level"] == "U1":
            status = "m00_urgent_action_only"
        elif route["route_status"] != "confirmed":
            status = "waiting_for_route_clarification"
            if route["route_status"] == "route_unresolved":
                status = "route_unresolved_after_one_clarification"
        elif m00_recheck_reason:
            status = "waiting_for_m00_image_recheck" if m00_recheck_reason == "image_facts" else "waiting_for_m00_structured_fact_recheck"
        elif module_failures:
            status = "degraded_without_safety_downgrade"
        elif draft_review and not draft_review["passed"]:
            status = "draft_regeneration_required"
        elif final_guard:
            status = final_guard["status"]
        return {
            "schema_version": SCHEMA_VERSION,
            "module": "M11",
            "status": status,
            "episode_state": state.to_dict(),
            "safety": safety,
            "facts": list(state.fact_ledger.values()),
            "route": route,
            "execution_plan": plan,
            "module_outputs": module_outputs,
            "module_failures": module_failures,
            "deferred_module_calls": deferred_modules,
            "m00_recheck_required": bool(m00_recheck_reason),
            "m00_recheck_reason": m00_recheck_reason,
            "model_request": packet,
            "draft_review": draft_review,
            "final_guard": final_guard,
            "user_output": None,
            "production_enabled": MODULE_PRODUCTION_ENABLED,
            "release_gate": "M12_REQUIRED",
            "trace": [
                {"event": "M00_CURRENT_TURN_VERIFIED", "turn_id": turn_id, "effective_level": safety["effective_level"]},
                {"event": "M01_FACT_LEDGER_UPDATED", "fact_count": len(state.fact_ledger)},
                {"event": "M11_ROUTE_ASSEMBLED", "route_status": route["route_status"]},
                {"event": "M11_PLAN_BUILT", "step_count": len(plan["steps"])},
                *(
                    [{"event": "M08_NEW_FACTS_RETURNED_TO_M00", "deferred_modules": deferred_modules}]
                    if m00_recheck_reason == "image_facts"
                    else []
                ),
                *(
                    [{"event": "SPECIALIST_SAFETY_FACTS_RETURNED_TO_M00", "deferred_modules": deferred_modules}]
                    if m00_recheck_reason == "structured_safety_facts"
                    else []
                ),
            ],
        }
