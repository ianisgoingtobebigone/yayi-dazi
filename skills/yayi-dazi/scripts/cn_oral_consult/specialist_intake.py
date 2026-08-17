from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


FACT_STATUSES = {
    "affirmed", "denied", "uncertain", "unknown", "not_applicable",
    "conflicted", "historical", "documented",
}
SOURCE_TYPES = {
    "user_current", "user_history", "clinician_record", "device_document",
    "third_party", "linked_module_fact", "system_state",
}
M00_LEVELS = {"E0", "E1", "U1", "N1", "S0", "NEEDS_CLARIFICATION"}
HALT_LEVELS = {"E0", "E1"}
ROUTE_STATUSES = {"confirmed", "provisional", "needs_clarification", "route_unresolved"}
MODULES = {f"M{index:02d}" for index in range(2, 8)}
PHOTO_METADATA_KEYS = {"provided", "media_ids", "source_type", "user_request", "m08_linked_fact_ids"}
PHOTO_OBSERVATION_KEYS = {"technical_quality", "visible_observations", "diagnosis", "assessment", "findings"}

DEPARTMENTS = {
    "M02": "牙体牙髓科或医院口腔科",
    "M03": "牙周科、口腔内科或医院口腔科",
    "M04": "口腔黏膜科、口腔内科或医院口腔科",
    "M05": "口腔修复科或医院口腔科",
    "M06": "口腔正畸科或医院口腔科",
    "M07": "口腔颌面外科或医院相应专科门诊",
}


class SpecialistContractError(ValueError):
    pass


def validate_safety(value: Mapping[str, Any] | None, *, module: str) -> dict[str, Any]:
    if not value:
        raise SpecialistContractError(f"{module}_REQUIRES_M00_RESULT")
    level = str(value.get("effective_level", ""))
    if level not in M00_LEVELS:
        raise SpecialistContractError(f"unsupported M00 effective_level: {level}")
    basis = value.get("basis_from_user", [])
    uncertainties = value.get("uncertainties", [])
    if not isinstance(basis, list) or not isinstance(uncertainties, list):
        raise SpecialistContractError("M00 basis_from_user and uncertainties must be lists")
    return {
        "effective_level": level,
        "risk_floor_level": value.get("risk_floor_level"),
        "next_state": value.get("next_state"),
        "basis_from_user": list(basis),
        "uncertainties": list(uncertainties),
        "user_message_zh": value.get("user_message_zh"),
        "time_to_care": value.get("time_to_care"),
        "destination": value.get("destination") or value.get("destination_types_zh"),
        "urgency_owned_by": "M00",
    }


def validate_facts(
    items: Sequence[Mapping[str, Any]], *, module: str, field_count: int
) -> list[dict[str, Any]]:
    allowed = {f"M01-FLD-{index:03d}" for index in range(1, 16)} | {
        f"{module}-FLD-{index:03d}" for index in range(1, field_count + 1)
    }
    result: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        field_id = str(item.get("field_id", ""))
        if field_id not in allowed:
            raise SpecialistContractError(f"fact {index} uses an unapproved field ID: {field_id}")
        status = str(item.get("value_status", item.get("status", "")))
        source = str(item.get("source_type", ""))
        if status not in FACT_STATUSES or source not in SOURCE_TYPES:
            raise SpecialistContractError(f"fact {field_id} has unsupported status or source_type")
        spans = item.get("basis_spans", [])
        if isinstance(spans, str):
            spans = [spans]
        if not isinstance(spans, Sequence):
            raise SpecialistContractError(f"fact {field_id} basis_spans must be a list")
        spans = [str(span).strip() for span in spans if str(span).strip()]
        if status not in {"unknown", "not_applicable"} and not spans:
            raise SpecialistContractError(f"fact {field_id} is missing basis_spans")
        if "value" not in item:
            raise SpecialistContractError(f"fact {field_id} is missing value")
        result.append({
            "field_id": field_id,
            "value_status": status,
            "value": item["value"],
            "source_type": source,
            "basis_spans": spans,
            "source_date": item.get("source_date"),
            "time_context": item.get("time_context"),
            "linked_fact_id": item.get("linked_fact_id"),
        })
    return result


def group_facts(items: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups = {"affirmed": [], "denied": [], "uncertain_or_conflicted": [], "historical_or_documented": [], "not_for_user_display": []}
    for item in items:
        status = item["value_status"]
        if status == "affirmed":
            target = "affirmed"
        elif status == "denied":
            target = "denied"
        elif status in {"uncertain", "conflicted"}:
            target = "uncertain_or_conflicted"
        elif status in {"historical", "documented"}:
            target = "historical_or_documented"
        else:
            target = "not_for_user_display"
        groups[target].append(dict(item))
    return groups


def validate_route(value: Mapping[str, Any] | None, *, module: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if value.get("assembled_by") != "M11":
        raise SpecialistContractError(f"{module}_REQUIRES_M11_BUSINESS_ROUTE")
    forbidden = {"effective_level", "risk_floor_level", "time_to_care", "destination", "urgency"}
    if overlap := set(value) & forbidden:
        raise SpecialistContractError(f"M11 route must not alter M00 fields: {sorted(overlap)}")
    status = str(value.get("route_status", ""))
    primary, secondary = value.get("primary_module"), value.get("secondary_module")
    if status not in ROUTE_STATUSES:
        raise SpecialistContractError(f"unsupported route_status: {status}")
    if primary is not None and primary not in MODULES:
        raise SpecialistContractError("unsupported primary_module")
    if isinstance(secondary, list) or (secondary is not None and secondary not in MODULES):
        raise SpecialistContractError("M11 allows at most one valid secondary_module")
    if primary == secondary and primary is not None:
        raise SpecialistContractError("primary_module and secondary_module must differ")
    return {
        "primary_module": primary,
        "secondary_module": secondary,
        "route_status": status,
        "health_first": bool(value.get("health_first", False)),
        "offline_required": bool(value.get("offline_required", False)),
        "route_history": list(value.get("route_history", [])),
        "assembled_by": "M11",
        "module_is_owner": module in {primary, secondary},
    }


def register_photo(value: Mapping[str, Any] | None, *, module: str) -> dict[str, Any]:
    if not value or not value.get("provided"):
        return {"provided": False, "handoff_required": False, "handoff_target": None, "m08_linked_fact_ids": []}
    if overlap := set(value) & PHOTO_OBSERVATION_KEYS:
        raise SpecialistContractError(f"{module}_CANNOT_ACCEPT_PHOTO_OBSERVATIONS: {sorted(overlap)}")
    if unknown := set(value) - PHOTO_METADATA_KEYS:
        raise SpecialistContractError(f"unsupported photo metadata: {sorted(unknown)}")
    media_ids = value.get("media_ids", [])
    linked = value.get("m08_linked_fact_ids", [])
    if not isinstance(media_ids, list) or not media_ids or not all(str(item).strip() for item in media_ids):
        raise SpecialistContractError("photo media_ids must be a non-empty list")
    if not isinstance(linked, list) or not all(re.fullmatch(r"FACT-[A-Za-z0-9_-]+", str(item)) for item in linked):
        raise SpecialistContractError("invalid M08 linked fact IDs")
    return {
        "provided": True,
        "media_ids": [str(item) for item in media_ids],
        "source_type": str(value.get("source_type", "user_upload")),
        "user_request": str(value.get("user_request", "")),
        "handoff_required": not bool(linked),
        "handoff_target": "M08",
        "m08_linked_fact_ids": [str(item) for item in linked],
        "professional_image_interpretation_allowed": False,
        "image_may_lower_m00": False,
    }


def validate_question_blocks(blocks: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if len(blocks or []) > 1:
        raise SpecialistContractError("one turn may contain at most one question block")
    result: list[dict[str, Any]] = []
    for block in blocks or []:
        points = block.get("information_points", [])
        if not isinstance(points, list) or not 1 <= len(points) <= 3:
            raise SpecialistContractError("a question block requires one to three tightly related information points")
        if not bool(block.get("tightly_related")):
            raise SpecialistContractError("question block information points must be tightly related")
        result.append({"information_points": [str(item) for item in points], "tightly_related": True})
    return result


def department_handoff(route: Mapping[str, Any], *, module: str) -> dict[str, Any]:
    if route.get("route_status") in {"needs_clarification", "route_unresolved"} or route.get("primary_module") is None:
        return {"primary": "医院口腔科或口腔综合科", "secondary": None, "route_unresolved": True, "urgency_owned_by": "M00"}
    primary = str(route["primary_module"])
    secondary = route.get("secondary_module")
    return {
        "primary": DEPARTMENTS[primary],
        "secondary": DEPARTMENTS[str(secondary)] if secondary else None,
        "route_unresolved": False,
        "health_first": bool(route.get("health_first")),
        "current_module": module,
        "urgency_owned_by": "M00",
        "assembled_by": "M11",
    }


def build_offline_assessments(
    facts: Sequence[Mapping[str, Any]], *, mapping: Mapping[str, tuple[str, str, Sequence[str]]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for fact in facts:
        if fact["value_status"] not in {"affirmed", "uncertain", "conflicted", "historical", "documented"}:
            continue
        config = mapping.get(str(fact["field_id"]))
        if not config:
            continue
        rule_id, direction, must_not_infer = config
        result.append({
            "rule_id": rule_id,
            "status": "offline_required",
            "basis_spans": list(fact["basis_spans"]),
            "assessment_direction": direction,
            "urgency_owned_by": "M00",
            "must_not_infer": list(must_not_infer),
        })
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in result:
        unique[(item["rule_id"], item["assessment_direction"])] = item
    return list(unique.values())


def run_specialist(
    *,
    module: str,
    field_count: int,
    output_last: int,
    task: str,
    allowed_tasks: set[str],
    user_task: str,
    facts: Sequence[Mapping[str, Any]],
    safety_result: Mapping[str, Any] | None,
    route_result: Mapping[str, Any] | None,
    photo_context: Mapping[str, Any] | None,
    question_blocks: Sequence[Mapping[str, Any]] | None,
    safety_recheck_fact_ids: Sequence[str] | None,
    offline_mapping: Mapping[str, tuple[str, str, Sequence[str]]],
    safety_recheck_fields: set[str],
    capability_boundary_zh: str,
    prohibitions: Sequence[str],
) -> dict[str, Any]:
    if task not in allowed_tasks:
        raise SpecialistContractError(f"unsupported {module} task: {task}")
    safety = validate_safety(safety_result, module=module)
    checked_facts = validate_facts(facts, module=module, field_count=field_count)
    photo = register_photo(photo_context, module=module)
    questions = validate_question_blocks(question_blocks)
    trace = [
        {"event": "M00_RESULT_VERIFIED", "effective_level": safety["effective_level"]},
        {"event": f"M01_{module}_FACTS_VALIDATED", "fact_count": len(checked_facts)},
    ]
    base = {
        "schema_version": f"cn-dental-{module.lower()}.output.v1",
        "module": module,
        "task": task,
        "user_task": user_task,
        "safety": safety,
        "fact_groups": group_facts(checked_facts),
        "photo_registration": photo,
        "question_blocks": questions,
        "question_policy": {"max_blocks_this_turn": 1, "max_tightly_related_points_per_block": 3},
        "output_rule_ids": [f"{module}-OUT-001", f"{module}-OUT-{output_last:03d}"],
        "capability_boundary_zh": capability_boundary_zh,
        "production_enabled": False,
    }
    level = safety["effective_level"]
    if level in HALT_LEVELS:
        return {**base, "status": "halted_by_m00", "m11_route": None, "offline_assessment": [], "next_action": "execute_m00_route_and_halt", "trace": trace}
    if level == "NEEDS_CLARIFICATION":
        return {**base, "status": "waiting_for_m00_clarification", "m11_route": None, "offline_assessment": [], "next_action": "ask_only_m00_clarification", "trace": trace}
    if level == "U1":
        return {**base, "status": "limited_by_m00", "m11_route": None, "offline_assessment": [], "next_action": "show_m00_action_and_allow_at_most_one_destination_changing_question", "trace": trace}
    route = validate_route(route_result, module=module)
    if route is None:
        return {**base, "status": "awaiting_m11_business_route", "m11_route": None, "route_submission": {"candidate_modules": [module], "facts_only": True, "safety_owned_by": "M00"}, "offline_assessment": [], "next_action": "request_m11_business_route", "trace": trace}
    if route["route_status"] == "confirmed" and not route["module_is_owner"]:
        return {**base, "status": "routed_to_other_specialist", "m11_route": route, "offline_assessment": [], "department_handoff": department_handoff(route, module=module), "next_action": "return_control_to_m11_without_running_specialist", "trace": trace}
    if photo["provided"] and photo["handoff_required"]:
        return {**base, "status": "awaiting_m08_photo_handoff", "m11_route": route, "offline_assessment": [], "department_handoff": department_handoff(route, module=module), "next_action": "dispatch_photo_to_m08_then_return_via_m00", "trace": trace}
    offline = build_offline_assessments(checked_facts, mapping=offline_mapping)
    requested_recheck_ids = {str(item) for item in (safety_recheck_fact_ids or [])}
    known_facts = {str(item["field_id"]): item for item in checked_facts}
    if not requested_recheck_ids <= set(known_facts):
        raise SpecialistContractError("safety recheck fact IDs must exist in the current structured facts")
    if not requested_recheck_ids <= safety_recheck_fields:
        raise SpecialistContractError("safety recheck requested from a field outside the approved safety handoff set")
    safety_spans = [
        span
        for field_id in requested_recheck_ids
        for span in known_facts[field_id]["basis_spans"]
    ]
    return {
        **base,
        "status": "ready_for_base_model",
        "m11_route": route,
        "safety_recheck": {"required": bool(safety_spans), "requested_operation": "full_triage" if safety_spans else None, "basis_spans": safety_spans},
        "m00_recheck_required": bool(safety_spans),
        "offline_assessment": offline,
        "department_handoff": department_handoff(route, module=module),
        "model_handoff": {
            "base_model_required": True,
            "required_output_sections": ["M00安全行动", "有来源的事实摘要", "明确否认与不确定性", "线下未决事项", "中国化就诊方向", "能力边界"],
            "prohibitions": list(prohibitions),
            "next_guards": ["M11", "M00_FINAL_GUARD"],
        },
        "next_action": "base_model_synthesis_then_m11_review_and_m00_final_guard",
        "trace": trace + [{"event": "M11_ROUTE_VERIFIED", "primary": route["primary_module"], "secondary": route["secondary_module"]}],
    }


def guard_output(text: str, *, safety_level: str, internal_pattern: str, extra_patterns: Sequence[tuple[str, str]]) -> dict[str, Any]:
    patterns = [
        (r"(?:你|您)(?:就是|得了|患有)|(?:已经|可以)?确诊|(?:可以|能够|基本)排除", "确定诊断或排除"),
        (r"(?:最像|大概率|基本确定|肯定是)|\b\d+(?:\.\d+)?\s*%", "未经验证的个体概率"),
        (r"(?:自行|自己).{0,14}(?:敲|探|刺|挤|摇|磨|切|调整|停药|换药)", "危险自测、操作或用药调整"),
        (r"(?<!\d)(?:911|999|111)(?!\d)|(?:NHS|urgent care|海外急诊)", "境外医疗服务入口"),
        (internal_pattern, "内部编号"),
        *extra_patterns,
    ]
    violations = [{"reason": reason, "matched": match.group(0)} for pattern, reason in patterns if (match := re.search(pattern, text, re.I))]
    if safety_level in HALT_LEVELS and not re.search(r"立即|马上|急诊|尽快前往", text):
        violations.append({"reason": "缺少M00紧急行动", "matched": ""})
    if safety_level == "U1" and not re.search(r"24\s*小时|当天|尽快", text):
        violations.append({"reason": "缺少M00的24小时内行动", "matched": ""})
    return {"passed": not violations, "violations": violations, "next_action": "send_to_m00_final_guard" if not violations else "regenerate"}
