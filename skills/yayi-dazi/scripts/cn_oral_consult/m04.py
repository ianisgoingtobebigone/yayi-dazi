from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .runtime_paths import data_path


CATALOG_PATH = data_path("m04_catalog.json")

M04_FIELD_IDS = {f"M04-FLD-{index:03d}" for index in range(1, 19)}
SHARED_FIELD_IDS = {f"M01-FLD-{index:03d}" for index in range(1, 16)}
ALLOWED_FACT_STATUSES = {"reported", "denied", "uncertain", "historical", "documented"}
ALLOWED_TASKS = {"case_support", "education", "record_explanation", "photo_observation"}
CONTINUABLE_LEVELS = {"N1", "S0"}
LIMITED_LEVELS = {"U1"}
HALT_LEVELS = {"E0", "E1"}

VISIBLE_PHOTO_ATTRIBUTES = {
    "site",
    "number_distribution",
    "symmetry",
    "color",
    "shape",
    "boundary_visibility",
    "surface_appearance",
    "visible_covering",
    "visible_elevation",
    "visible_surface_breakdown",
}
PHOTO_QUALITY_FIELDS = {"target_present", "focus", "exposure", "framing", "occlusion"}
PHOTO_QUALITY_VALUES = {"pass", "fail", "unknown"}

FORBIDDEN_USER_OUTPUT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?:你|您)(?:就是|得了|患有)", "把远程信息写成确诊"),
    (r"(?:已经|可以)?确诊", "把远程信息写成确诊"),
    (r"(?:可以|能够|基本)排除", "作出排除性结论"),
    (r"(?:最像|大概率|基本确定|肯定是)", "输出未经验证的个体概率或确定性"),
    (r"\b\d+(?:\.\d+)?\s*%", "输出未经验证的个体概率"),
    (r"(?:你|您)(?:必须|一定要)(?:做|查)", "把检查背景写成个体必做检查"),
    (r"\b(?:911|999|111)\b", "包含非中国本土紧急服务号码"),
    (r"(?:每日|一天)\s*\d+\s*次|\d+(?:\.\d+)?\s*(?:mg|毫克)", "包含个体药物剂量或频次"),
    (r"M04-(?:DIS|LSN|DXM|FLD)-\d{3}", "向用户暴露内部知识或字段编号"),
)


class M04ContractError(ValueError):
    """Raised when M04 is called without the evidence or safety contract it requires."""


@lru_cache(maxsize=1)
def load_m04_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _entry_id(entry: Mapping[str, Any]) -> str:
    for key in (
        "disease_knowledge_id",
        "lesion_knowledge_id",
        "diagnostic_or_examination_knowledge_id",
    ):
        if key in entry:
            return str(entry[key])
    raise M04ContractError("catalog entry has no supported knowledge ID")


def _entry_name(entry: Mapping[str, Any]) -> str:
    return str(entry.get("canonical_name_zh") or entry.get("entry_name_zh") or "")


def _entry_type(entry: Mapping[str, Any]) -> str:
    knowledge_id = _entry_id(entry)
    if "-DIS-" in knowledge_id:
        return "disease"
    if "-LSN-" in knowledge_id:
        return "lesion"
    return "diagnostic_method"


def _flatten_text(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from _flatten_text(child)
    elif isinstance(value, Sequence):
        for child in value:
            yield from _flatten_text(child)


def _query_text(parts: Iterable[str]) -> str:
    return " ".join(str(part).strip().lower() for part in parts if str(part).strip())


def _score_entry(entry: Mapping[str, Any], query: str) -> tuple[int, list[str]]:
    if not query:
        return 0, []

    score = 0
    matches: list[str] = []
    name = _entry_name(entry).lower()
    aliases = [str(item).lower() for item in entry.get("source_aliases", [])]
    terms = [str(item).lower() for item in entry.get("user_terms", [])]
    terms.extend(str(item).lower() for item in entry.get("retrieval_terms", []))

    if name and name in query:
        score += 20
        matches.append(name)
    for alias in aliases:
        if alias and alias in query:
            score += 14
            matches.append(alias)
    for term in terms:
        if term and term in query:
            score += 3
            matches.append(term)

    # Character bigrams provide a conservative fallback for common Chinese descriptions.
    compact_query = re.sub(r"\s+", "", query)
    if score == 0 and name:
        bigrams = {name[index : index + 2] for index in range(max(0, len(name) - 1))}
        overlap = [item for item in bigrams if item in compact_query]
        if overlap:
            score = len(overlap)
            matches.extend(sorted(overlap))
    return score, sorted(set(matches))


@dataclass(frozen=True)
class RetrievalRequest:
    query_basis: tuple[str, ...]
    task: str = "case_support"
    knowledge_types: tuple[str, ...] = ("disease", "lesion", "diagnostic_method")
    include_reviewed: bool = False
    adult_only: bool = True
    limit: int = 8


class M04KnowledgeStore:
    """Read-only, approval-gated retrieval over the reviewed M04 catalog."""

    def __init__(self, catalog: Mapping[str, Any] | None = None) -> None:
        self.catalog = dict(catalog or load_m04_catalog())

    def _entries(self) -> Iterable[Mapping[str, Any]]:
        yield from self.catalog["diseases"]
        yield from self.catalog["lesions"]
        yield from self.catalog["diagnostic_methods"]

    def retrieve(self, request: RetrievalRequest) -> list[dict[str, Any]]:
        if request.task not in ALLOWED_TASKS:
            raise M04ContractError(f"unsupported M04 task: {request.task}")
        if request.limit < 1 or request.limit > 20:
            raise M04ContractError("retrieval limit must be between 1 and 20")

        allowed_statuses = {"approved"}
        if request.include_reviewed:
            allowed_statuses.add("reviewed")
        allowed_types = set(request.knowledge_types)
        unknown_types = allowed_types - {"disease", "lesion", "diagnostic_method"}
        if unknown_types:
            raise M04ContractError(f"unsupported knowledge types: {sorted(unknown_types)}")

        query = _query_text(request.query_basis)
        scored: list[tuple[int, str, Mapping[str, Any], list[str]]] = []
        for entry in self._entries():
            if _entry_type(entry) not in allowed_types:
                continue
            if entry.get("review_status") not in allowed_statuses:
                continue
            if request.adult_only and entry.get("runtime_scope") == "out_of_adult_runtime":
                continue
            score, matched_terms = _score_entry(entry, query)
            if score:
                scored.append((score, _entry_id(entry), entry, matched_terms))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [self._project(entry, score, matched_terms, request.task, query) for score, _, entry, matched_terms in scored[: request.limit]]

    @staticmethod
    def _project(
        entry: Mapping[str, Any], score: int, matched_terms: list[str], task: str, query: str
    ) -> dict[str, Any]:
        entry_type = _entry_type(entry)
        policies = list(entry.get("user_disclosure_policy", []))
        name = _entry_name(entry)
        exact_named_education = task == "education" and (
            name.lower() in query
            or any(str(alias).lower() in query for alias in entry.get("source_aliases", []))
        )
        if entry_type == "disease":
            display_allowed = exact_named_education and "education" in policies
            if task == "case_support" and "qualified_differential" in policies and "internal_only" not in policies:
                display_allowed = True
        else:
            display_allowed = task in {"education", "record_explanation"}

        return {
            "knowledge_id": _entry_id(entry),
            "knowledge_type": entry_type,
            "name_zh": name,
            "retrieval_score_internal": score,
            "matched_terms_internal": matched_terms,
            "retrieval_relation": "context_only",
            "display_allowed": display_allowed,
            "definition_summary": entry.get("definition_summary"),
            "required_clinician_findings": list(entry.get("required_clinician_findings", [])),
            "diagnostic_method_ids": list(entry.get("diagnostic_method_ids", [])),
            "user_disclosure_policy": policies,
            "source_refs": list(entry.get("source_refs", [])),
            "must_not_infer": list(entry.get("must_not_infer", [])),
            "review_status": entry.get("review_status"),
        }


def validate_facts(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for index, fact in enumerate(facts):
        field_id = str(fact.get("field_id", ""))
        if field_id not in M04_FIELD_IDS | SHARED_FIELD_IDS:
            raise M04ContractError(f"fact {index} uses an unapproved field ID: {field_id}")
        status = str(fact.get("status", ""))
        if status not in ALLOWED_FACT_STATUSES:
            raise M04ContractError(f"fact {index} has unsupported status: {status}")
        basis_span = str(fact.get("basis_span", "")).strip()
        if not basis_span:
            raise M04ContractError(f"fact {index} is missing basis_span")
        if "value" not in fact:
            raise M04ContractError(f"fact {index} is missing value")
        validated.append(
            {
                "field_id": field_id,
                "status": status,
                "value": fact["value"],
                "basis_span": basis_span,
                "source": str(fact.get("source", "user_text")),
            }
        )
    return validated


def validate_photo_context(photo_context: Mapping[str, Any] | None) -> dict[str, Any]:
    if not photo_context or not photo_context.get("provided"):
        return {
            "provided": False,
            "usable_for_visible_description": False,
            "visible_observations_only": [],
            "unassessable_reasons": [],
        }

    quality = dict(photo_context.get("technical_quality", {}))
    unknown_quality_fields = set(quality) - PHOTO_QUALITY_FIELDS
    if unknown_quality_fields:
        raise M04ContractError(f"unsupported photo quality fields: {sorted(unknown_quality_fields)}")
    normalized_quality = {
        key: str(quality.get(key, "unknown")) for key in sorted(PHOTO_QUALITY_FIELDS)
    }
    for key, value in normalized_quality.items():
        if value not in PHOTO_QUALITY_VALUES:
            raise M04ContractError(f"photo quality {key} has unsupported value: {value}")

    usable = all(normalized_quality[key] == "pass" for key in ("target_present", "focus", "exposure", "framing"))
    observations: list[dict[str, Any]] = []
    for index, observation in enumerate(photo_context.get("visible_observations_only", [])):
        attribute = str(observation.get("attribute", ""))
        if attribute not in VISIBLE_PHOTO_ATTRIBUTES:
            raise M04ContractError(f"photo observation {index} uses non-visual attribute: {attribute}")
        if not str(observation.get("value", "")).strip():
            raise M04ContractError(f"photo observation {index} is missing a visible value")
        observations.append(
            {
                "attribute": attribute,
                "value": str(observation["value"]),
                "uncertainty": str(observation.get("uncertainty", "not_stated")),
                "source": "photo_visible_description",
            }
        )

    reasons = [str(item) for item in photo_context.get("unassessable_reasons", [])]
    if not usable:
        observations = []
        reasons.append("照片技术质量不足，未把可见候选写入事实层")
    return {
        "provided": True,
        "technical_quality": normalized_quality,
        "usable_for_visible_description": usable,
        "visible_observations_only": observations,
        "unassessable_reasons": sorted(set(reasons)),
        "limitations": [
            "照片只能提供可见描述，不能确认病损性质、病原、深度、质地或组织学结果",
            "照片不得降低M00已确定的紧迫度",
        ],
    }


def _validate_safety_result(safety_result: Mapping[str, Any] | None) -> dict[str, Any]:
    if not safety_result:
        raise M04ContractError("M04_REQUIRES_M00_RESULT")
    level = str(safety_result.get("effective_level", ""))
    if level not in HALT_LEVELS | LIMITED_LEVELS | CONTINUABLE_LEVELS | {"NEEDS_CLARIFICATION"}:
        raise M04ContractError(f"unsupported M00 effective_level: {level}")
    if not isinstance(safety_result.get("basis_from_user", []), list):
        raise M04ContractError("M00 basis_from_user must be a list")
    return {
        "effective_level": level,
        "risk_floor_level": safety_result.get("risk_floor_level"),
        "next_state": safety_result.get("next_state"),
        "basis_from_user": list(safety_result.get("basis_from_user", [])),
        "uncertainties": list(safety_result.get("uncertainties", [])),
    }


def run_m04(
    *,
    task: str,
    user_task: str,
    facts: Sequence[Mapping[str, Any]],
    safety_result: Mapping[str, Any] | None,
    photo_context: Mapping[str, Any] | None = None,
    include_reviewed: bool = False,
    knowledge_store: M04KnowledgeStore | None = None,
) -> dict[str, Any]:
    """Build an evidence package for the base model; it never returns a diagnosis itself."""
    if task not in ALLOWED_TASKS:
        raise M04ContractError(f"unsupported M04 task: {task}")
    safety = _validate_safety_result(safety_result)
    validated_facts = validate_facts(facts)
    validated_photo = validate_photo_context(photo_context)

    trace: list[dict[str, Any]] = [
        {"event": "M00_RESULT_VERIFIED", "effective_level": safety["effective_level"]},
        {"event": "M01_M04_FACTS_VALIDATED", "fact_count": len(validated_facts)},
    ]
    if validated_photo["provided"]:
        trace.append(
            {
                "event": "M08_PHOTO_CONTEXT_VALIDATED",
                "usable": validated_photo["usable_for_visible_description"],
            }
        )

    if safety["effective_level"] in HALT_LEVELS:
        return {
            "schema_version": "cn-dental-m04.output.v1",
            "module": "M04",
            "status": "halted_by_m00",
            "safety": safety,
            "facts": validated_facts,
            "photo_context": validated_photo,
            "retrieved_knowledge": [],
            "next_action": "execute_m00_route_without_continuing_m04",
            "trace": trace + [{"event": "M04_HALTED", "reason": safety["effective_level"]}],
        }
    if safety["effective_level"] == "NEEDS_CLARIFICATION":
        return {
            "schema_version": "cn-dental-m04.output.v1",
            "module": "M04",
            "status": "waiting_for_m00_clarification",
            "safety": safety,
            "facts": validated_facts,
            "photo_context": validated_photo,
            "retrieved_knowledge": [],
            "next_action": "ask_only_m00_clarification",
            "trace": trace + [{"event": "M04_PAUSED_FOR_M00_CLARIFICATION"}],
        }
    if safety["effective_level"] in LIMITED_LEVELS:
        return {
            "schema_version": "cn-dental-m04.output.v1",
            "module": "M04",
            "status": "limited_by_m00",
            "task": task,
            "user_task": user_task,
            "safety": safety,
            "facts": validated_facts,
            "photo_context": validated_photo,
            "retrieved_knowledge": [],
            "retrieval_gap": False,
            "model_handoff": {
                "base_model_required": True,
                "required_output_sections": ["M00紧迫度与就诊方向", "用户已提供事实", "能力边界"],
                "prohibitions": [
                    "不得继续疾病鉴别或普通M04问询",
                    "不得用背景知识延迟或稀释24小时内就诊建议",
                ],
            },
            "next_action": "limited_handoff_to_m11",
            "trace": trace + [{"event": "M04_LIMITED_BEFORE_RETRIEVAL", "reason": "U1"}],
        }

    query_basis = [user_task]
    query_basis.extend(str(fact["value"]) for fact in validated_facts if fact["status"] != "denied")
    query_basis.extend(item["value"] for item in validated_photo["visible_observations_only"])
    request = RetrievalRequest(
        query_basis=tuple(query_basis),
        task=task,
        include_reviewed=include_reviewed,
    )
    store = knowledge_store or M04KnowledgeStore()
    retrieved = store.retrieve(request)
    trace.append(
        {
            "event": "M10_RETRIEVAL_COMPLETED",
            "approval_mode": "reviewed_for_internal_evaluation" if include_reviewed else "approved_only",
            "result_count": len(retrieved),
        }
    )

    return {
        "schema_version": "cn-dental-m04.output.v1",
        "module": "M04",
        "status": "ready_for_base_model",
        "task": task,
        "user_task": user_task,
        "safety": safety,
        "facts": validated_facts,
        "photo_context": validated_photo,
        "retrieved_knowledge": retrieved,
        "retrieval_gap": not bool(retrieved),
        "model_handoff": {
            "base_model_required": True,
            "allowed_model_prior": "可用于理解原话、生成自然表达和提出待核对候选，但必须与检索证据分源",
            "required_output_sections": [
                "用户已提供事实",
                "不确定或缺失信息",
                "M00紧迫度与就诊方向",
                "有依据且符合披露策略的专业鉴别方向（如适用）",
                "需线下确认的证据",
                "能力边界",
            ],
            "prohibitions": [
                "不得把context_only检索命中写成支持当前个体诊断",
                "不得展示display_allowed=false的条目名称",
                "不得把照片写成病损性质、病原、深度、质地或组织学结论",
                "不得生成个体概率、确诊、排除性结论、处方、剂量或器械/手术操作",
                "U1状态只允许完成不会延误24小时内就诊的最小交接",
            ],
        },
        "next_action": "base_model_synthesis_then_m11_and_m00_final_guard",
        "trace": trace,
    }


def guard_user_output(text: str, *, safety_level: str) -> dict[str, Any]:
    """M11-style deterministic backstop for high-risk output classes."""
    violations: list[dict[str, str]] = []
    for pattern, reason in FORBIDDEN_USER_OUTPUT_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            violations.append({"pattern": pattern, "reason": reason})

    if safety_level in HALT_LEVELS and not any(
        token in text for token in ("急诊", "立即", "尽快前往", "马上前往")
    ):
        violations.append({"pattern": "m00_action_missing", "reason": "E0/E1输出未保留紧急行动"})
    if safety_level == "U1" and not any(token in text for token in ("24小时", "当天", "尽快")):
        violations.append({"pattern": "u1_time_missing", "reason": "U1输出未保留24小时内行动"})

    return {
        "passed": not violations,
        "violations": violations,
        "next_action": "send_to_m00_final_guard" if not violations else "regenerate_without_lowering_risk",
    }
