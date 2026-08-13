from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


M07_FIELD_IDS = {f"M07-FLD-{index:03d}" for index in range(1, 25)}
SHARED_FIELD_IDS = {f"M01-FLD-{index:03d}" for index in range(1, 16)}
ALLOWED_FACT_STATUSES = {"affirmed", "denied", "uncertain", "unknown", "not_applicable", "conflicted", "historical", "documented"}
ALLOWED_SOURCE_TYPES = {"user_current", "user_history", "clinician_record", "device_document", "third_party", "linked_module_fact", "system_state"}
ALLOWED_TASKS = {"intake_support", "problem_education", "assessment_explanation", "category_comparison", "record_explanation", "photo_observation", "department_navigation", "cross_specialty_summary"}
ALLOWED_BRANCHES = {"tmj", "infection", "trauma", "salivary", "mass", "neuro", "cross_specialty"}
ALLOWED_MODULES = {f"M{index:02d}" for index in range(2, 9)}
ALLOWED_ROUTE_STATUSES = {"confirmed", "provisional", "needs_clarification", "route_unresolved"}
ALL_M00_LEVELS = {"E0", "E1", "U1", "N1", "S0", "NEEDS_CLARIFICATION"}
HALT_LEVELS = {"E0", "E1"}

PHOTO_METADATA_KEYS = {"provided", "media_ids", "source_type", "user_request", "requested_views", "m08_linked_fact_ids"}
PHOTO_OBSERVATION_KEYS = {"technical_quality", "visible_observations", "diagnosis", "assessment", "findings", "fracture", "deep_space_infection", "tumor_nature", "joint_disc", "salivary_internal", "nerve_localization", "radiology_interpretation"}
ALLOWED_PHOTO_TASKS = {"face_frontal_rest", "face_profile", "local_external_swelling", "intraoral_visible_area", "mouth_open_closed_comparison", "wound_or_device_area", "report_page"}

KNOWLEDGE_ID_PATTERN = re.compile(r"^(?:M07-(?:DIS|DXM|PRB)-\d{3}|M09-TRT-0(?:3[9]|4[0-9]|5[0-4]))$")
INTERNAL_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:M07-(?:FLD|DLG|FLO|RUL|OUT|DIS|DXM|PRB)|M09-TRT)-[A-Z0-9-]*\d{3}(?![A-Za-z0-9])")

DEPARTMENTS = {
    "M02": ("牙体牙髓科", "医院口腔科或口腔综合科"),
    "M03": ("牙周科", "医院口腔科或口腔综合科"),
    "M04": ("口腔黏膜科或口腔内科", "医院口腔科或口腔综合科"),
    "M05": ("口腔修复科", "医院口腔科或口腔综合科"),
    "M06": ("口腔正畸科", "医院口腔科或口腔综合科"),
    "M07": ("口腔颌面外科", "医院口腔科或口腔综合科现场分诊"),
}

BRANCH_DEPARTMENTS = {
    "tmj": "口腔颌面外科、颞下颌关节专病门诊或医院相应专科",
    "infection": "口腔颌面外科",
    "trauma": "口腔颌面外科；是否进入综合医院急诊由M00决定",
    "salivary": "口腔颌面外科或唾液腺专病门诊",
    "mass": "口腔颌面外科或口腔颌面头颈肿瘤相关门诊",
    "neuro": "口腔颌面外科或神经内科，由主要事实决定",
    "cross_specialty": "综合医院相关专科或医院口腔科现场分诊",
}

FORBIDDEN_OUTPUT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?:你|您)(?:就是|得了|患有)", "把远程信息写成确诊"),
    (r"(?:已经|可以)?确诊|(?:可以|能够|基本)排除", "作出确诊或排除性结论"),
    (r"(?:最像|大概率|基本确定|肯定是)|\b\d+(?:\.\d+)?\s*%", "输出未经验证的个体概率"),
    (r"(?:你|您).{0,12}(?:是|属于).{0,12}(?:良性|恶性|癌|肉瘤)", "远程判断肿物性质"),
    (r"(?:照片|图片).{0,12}(?:看出|确定|证明).{0,18}(?:骨折|深部感染|间隙感染|关节盘移位|良性|恶性|神经损伤)", "用普通照片判断深部或病理性质"),
    (r"(?:你|您).{0,20}(?:需要|必须|应该|首选|建议).{0,18}(?:切开引流|穿刺|复位|固定|活检|手术|放疗|化疗)", "替当前用户选择侵入性检查或治疗"),
    (r"建议(?:你|您).{0,16}(?:做|接受|进行).{0,12}(?:切开引流|穿刺|复位|固定|活检|手术|放疗|化疗)", "替当前用户选择侵入性检查或治疗"),
    (r"建议(?:你|您).{0,16}(?:切开引流|穿刺|复位|固定|活检|手术|放疗|化疗)", "替当前用户选择侵入性检查或治疗"),
    (r"建议(?:你|您).{0,16}(?:吃|服用|使用|停用).{0,16}(?:抗生素|止痛药|激素|卡马西平)", "提供个体药物决定"),
    (r"(?:你|您).{0,12}(?:应该|必须|需要|首选).{0,12}(?:吃|服用|使用|停用).{0,16}(?:抗生素|止痛药|激素|卡马西平)", "提供个体药物决定"),
    (r"(?:自行|自己).{0,16}(?:挤|挑破|穿刺|切开|复位|掰回|按摩肿块|热敷|调整固定)", "提供危险的自行操作"),
    (r"(?<!\d)(?:911|999|111)(?!\d)|(?:NHS|urgent care|海外急诊)", "包含境外医疗服务入口"),
    (INTERNAL_ID_PATTERN.pattern, "向用户暴露内部编号"),
)


class M07ContractError(ValueError):
    """Raised when M07 is used outside its approved contract."""


def _validate_safety_result(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        raise M07ContractError("M07_REQUIRES_M00_RESULT")
    level = str(value.get("effective_level", ""))
    if level not in ALL_M00_LEVELS:
        raise M07ContractError(f"unsupported M00 effective_level: {level}")
    basis = value.get("basis_from_user", [])
    if not isinstance(basis, list):
        raise M07ContractError("M00 basis_from_user must be a list")
    return {
        "effective_level": level,
        "risk_floor_level": value.get("risk_floor_level"),
        "next_state": value.get("next_state"),
        "basis_from_user": list(basis),
        "uncertainties": list(value.get("uncertainties", [])),
        "user_message_zh": value.get("user_message_zh"),
        "time_to_care": value.get("time_to_care"),
        "destination": value.get("destination"),
        "urgency_owned_by": "M00",
    }


def validate_facts(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for index, fact in enumerate(facts):
        field_id = str(fact.get("field_id", ""))
        if field_id not in M07_FIELD_IDS | SHARED_FIELD_IDS:
            raise M07ContractError(f"fact {index} uses an unapproved field ID: {field_id}")
        status = str(fact.get("value_status", fact.get("status", "")))
        if status not in ALLOWED_FACT_STATUSES:
            raise M07ContractError(f"fact {index} has unsupported status: {status}")
        source_type = str(fact.get("source_type", ""))
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise M07ContractError(f"fact {index} has unsupported source_type: {source_type}")
        spans = fact.get("basis_spans", [])
        if isinstance(spans, str):
            spans = [spans]
        if not isinstance(spans, Sequence):
            raise M07ContractError(f"fact {index} basis_spans must be a list")
        spans = [str(item).strip() for item in spans if str(item).strip()]
        if status not in {"unknown", "not_applicable"} and not spans:
            raise M07ContractError(f"fact {index} is missing basis_spans")
        if "value" not in fact:
            raise M07ContractError(f"fact {index} is missing value")
        result.append({
            "field_id": field_id,
            "value_status": status,
            "value": fact["value"],
            "source_type": source_type,
            "basis_spans": spans,
            "source_date": fact.get("source_date"),
            "linked_fact_id": fact.get("linked_fact_id"),
        })
    return result


def group_facts(facts: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups = {"affirmed": [], "denied": [], "uncertain_or_conflicted": [], "historical_or_documented": [], "not_for_user_display": []}
    for fact in facts:
        status = fact["value_status"]
        target = "affirmed" if status == "affirmed" else "denied" if status == "denied" else "uncertain_or_conflicted" if status in {"uncertain", "conflicted"} else "historical_or_documented" if status in {"historical", "documented"} else "not_for_user_display"
        groups[target].append(dict(fact))
    return groups


def register_photo_context(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value or not value.get("provided"):
        return {"provided": False, "handoff_required": False, "handoff_target": None, "m07_observations": [], "m08_linked_fact_ids": []}
    prohibited = set(value) & PHOTO_OBSERVATION_KEYS
    if prohibited:
        raise M07ContractError(f"M07_CANNOT_ACCEPT_PHOTO_OBSERVATIONS: {sorted(prohibited)}")
    unknown = set(value) - PHOTO_METADATA_KEYS
    if unknown:
        raise M07ContractError(f"unsupported M07 photo metadata: {sorted(unknown)}")
    media_ids = value.get("media_ids", [])
    if not isinstance(media_ids, list) or not media_ids or not all(str(item).strip() for item in media_ids):
        raise M07ContractError("photo media_ids must be a non-empty list")
    views = value.get("requested_views", [])
    if not isinstance(views, list) or any(str(item) not in ALLOWED_PHOTO_TASKS for item in views):
        raise M07ContractError("photo requested_views contains an unsupported M08 task")
    linked = value.get("m08_linked_fact_ids", [])
    if not isinstance(linked, list) or any(not re.fullmatch(r"FACT-[A-Za-z0-9_-]+", str(item)) for item in linked):
        raise M07ContractError("invalid M08 linked fact IDs")
    return {
        "provided": True,
        "media_ids": [str(item) for item in media_ids],
        "source_type": str(value.get("source_type", "user_upload")),
        "user_request": str(value.get("user_request", "")),
        "requested_views": [str(item) for item in views],
        "handoff_required": not bool(linked),
        "handoff_target": "M08",
        "m07_observations": [],
        "m08_linked_fact_ids": [str(item) for item in linked],
        "limitations": [
            "M07只定义图像任务并登记M08关联事实，不生成图像观察",
            "普通照片不能判断深部感染、骨折、关节盘、腺体内部、病理性质或神经损伤部位",
            "照片不得降低M00紧迫度或否定用户感受",
        ],
    }


def validate_m11_route(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if value.get("assembled_by") != "M11":
        raise M07ContractError("M07_REQUIRES_M11_BUSINESS_ROUTE")
    forbidden = {"effective_level", "risk_floor_level", "time_to_care", "destination", "urgency"}
    overlap = set(value) & forbidden
    if overlap:
        raise M07ContractError(f"M11 route must not alter M00 safety fields: {sorted(overlap)}")
    status = str(value.get("route_status", ""))
    if status not in ALLOWED_ROUTE_STATUSES:
        raise M07ContractError(f"unsupported M11 route_status: {status}")
    primary = value.get("primary_module")
    secondary = value.get("secondary_module")
    if primary is not None and str(primary) not in ALLOWED_MODULES:
        raise M07ContractError(f"unsupported primary_module: {primary}")
    if isinstance(secondary, list):
        raise M07ContractError("M11 may return at most one secondary_module")
    if secondary is not None and str(secondary) not in ALLOWED_MODULES:
        raise M07ContractError(f"unsupported secondary_module: {secondary}")
    if primary == secondary and primary is not None:
        raise M07ContractError("primary_module and secondary_module must differ")
    if primary is None and status not in {"needs_clarification", "route_unresolved"}:
        raise M07ContractError("primary_module may be null only when routing remains unresolved")
    history = value.get("route_history", [])
    if not isinstance(history, list):
        raise M07ContractError("route_history must be a list")
    return {"primary_module": str(primary) if primary is not None else None, "secondary_module": str(secondary) if secondary is not None else None, "route_status": status, "offline_required": bool(value.get("offline_required", False)), "route_history": list(history), "assembled_by": "M11"}


def build_department_handoff(route: Mapping[str, Any], branch: str | None) -> dict[str, Any]:
    primary = route.get("primary_module")
    if primary is None or route.get("route_status") in {"needs_clarification", "route_unresolved"}:
        return {"ordinary_candidates_only": True, "primary": "医院口腔科或口腔综合科", "fallback": "由现场检查后分诊", "secondary": None, "route_unresolved": True, "urgency_owned_by": "M00", "assembled_by": "M11"}
    primary_name, fallback = DEPARTMENTS.get(str(primary), ("医院口腔科或口腔综合科", "由现场检查后分诊"))
    if primary == "M07" and branch in BRANCH_DEPARTMENTS:
        primary_name = BRANCH_DEPARTMENTS[branch]
    secondary = route.get("secondary_module")
    secondary_name = DEPARTMENTS[str(secondary)][0] if secondary in DEPARTMENTS and secondary != "M08" else None
    return {"ordinary_candidates_only": True, "primary": primary_name, "fallback": fallback, "secondary": secondary_name, "route_unresolved": False, "urgency_owned_by": "M00", "assembled_by": "M11"}


def gate_knowledge_context(items: Sequence[Mapping[str, Any]] | None, *, task: str, branch: str | None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    approved, blocked = [], []
    for index, item in enumerate(items or []):
        knowledge_id = str(item.get("knowledge_id", ""))
        if not KNOWLEDGE_ID_PATTERN.fullmatch(knowledge_id):
            raise M07ContractError(f"knowledge item {index} uses unsupported knowledge ID: {knowledge_id}")
        if item.get("review_status") != "approved":
            blocked.append({"knowledge_id": knowledge_id, "reason": "not_approved"})
            continue
        refs = item.get("source_refs", [])
        if not isinstance(refs, list) or not refs:
            blocked.append({"knowledge_id": knowledge_id, "reason": "missing_source_refs"})
            continue
        tasks = item.get("eligible_tasks")
        if tasks is not None and (not isinstance(tasks, list) or task not in tasks):
            blocked.append({"knowledge_id": knowledge_id, "reason": "task_mismatch"})
            continue
        item_branch = item.get("consultation_branch")
        if branch and item_branch and item_branch != branch:
            blocked.append({"knowledge_id": knowledge_id, "reason": "branch_mismatch"})
            continue
        if item.get("runtime_scope") == "out_of_adult_runtime":
            blocked.append({"knowledge_id": knowledge_id, "reason": "outside_adult_runtime_scope"})
            continue
        approved.append({"knowledge_id": knowledge_id, "name_zh": str(item.get("name_zh", "")), "summary": item.get("summary"), "source_refs": list(refs), "must_not_infer": list(item.get("must_not_infer", [])), "retrieval_relation": "context_only", "review_status": "approved"})
    return approved, blocked


def _envelope(*, status: str, task: str, user_task: str, safety: Mapping[str, Any], facts: Sequence[Mapping[str, Any]], photo: Mapping[str, Any], branch: str | None, trace: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "cn-dental-m07.output.v1",
        "module": "M07",
        "status": status,
        "task": task,
        "user_task": user_task,
        "consultation_branch": branch,
        "output_rule_ids": ["M07-OUT-001", "M07-OUT-030"],
        "safety": dict(safety),
        "fact_groups": group_facts(facts),
        "photo_registration": dict(photo),
        "capability_boundary_zh": "本输出不是诊断、影像或病理判读、个人用药或口腔颌面外科治疗方案",
        "trace": [dict(item) for item in trace],
    }


def run_m07(*, task: str, user_task: str, facts: Sequence[Mapping[str, Any]], safety_result: Mapping[str, Any] | None, route_result: Mapping[str, Any] | None = None, age_group: str = "adult", consultation_branch: str | None = None, photo_context: Mapping[str, Any] | None = None, knowledge_context: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Build a constrained M07 evidence package without diagnosing or selecting treatment."""
    if task not in ALLOWED_TASKS:
        raise M07ContractError(f"unsupported M07 task: {task}")
    if consultation_branch is not None and consultation_branch not in ALLOWED_BRANCHES:
        raise M07ContractError(f"unsupported M07 consultation branch: {consultation_branch}")
    safety = _validate_safety_result(safety_result)
    validated_facts = validate_facts(facts)
    photo = register_photo_context(photo_context)
    trace = [{"event": "M00_RESULT_VERIFIED", "effective_level": safety["effective_level"]}, {"event": "M01_M07_FACTS_VALIDATED", "fact_count": len(validated_facts)}]

    if age_group != "adult":
        result = _envelope(status="out_of_adult_scope", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, branch=None, trace=trace + [{"event": "ADULT_SCOPE_NOT_CONFIRMED"}])
        result.update({"m11_route": None, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": {"primary": "医院口腔科、口腔颌面外科或具备资质的相关专业人员", "note": "成人首版规则不用于未成年人个体判断"}, "next_action": "age_scope_handoff_without_applying_m07_rules"})
        return result
    if safety["effective_level"] in HALT_LEVELS:
        result = _envelope(status="halted_by_m00", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, branch=None, trace=trace + [{"event": "M07_HALTED"}])
        result.update({"m11_route": None, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": None, "next_action": "execute_m00_route_without_continuing_m07"})
        return result
    if safety["effective_level"] == "NEEDS_CLARIFICATION":
        result = _envelope(status="waiting_for_m00_clarification", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, branch=None, trace=trace + [{"event": "M07_PAUSED_FOR_M00_CLARIFICATION"}])
        result.update({"m11_route": None, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": None, "next_action": "ask_only_m00_clarification"})
        return result
    if safety["effective_level"] == "U1":
        result = _envelope(status="limited_by_m00", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, branch=None, trace=trace + [{"event": "M07_LIMITED_BEFORE_KNOWLEDGE"}])
        result.update({"m11_route": None, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": {"ordinary_candidates_only": False, "primary": safety.get("destination"), "urgency_owned_by": "M00"}, "next_action": "limited_handoff_to_m11_then_m00_final_guard"})
        return result

    route = validate_m11_route(route_result)
    if route is None:
        result = _envelope(status="awaiting_m11_business_route", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, branch=None, trace=trace + [{"event": "M11_ROUTE_REQUIRED"}])
        result.update({"m11_route": None, "route_submission": {"candidate_modules": ["M02", "M04", "M07"], "safety_owned_by": "M00", "facts_only": True}, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": None, "next_action": "request_m11_business_route_without_recalculating_safety"})
        return result
    routed_modules = {route.get("primary_module"), route.get("secondary_module")}
    if "M07" not in routed_modules:
        result = _envelope(status="routed_out_of_m07", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, branch=None, trace=trace + [{"event": "M11_ROUTED_TO_OTHER_MODULE", "primary_module": route.get("primary_module")}])
        result.update({"m11_route": route, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": build_department_handoff(route, None), "next_action": "continue_m11_selected_module_without_m07_knowledge"})
        return result
    if consultation_branch is None:
        result = _envelope(status="awaiting_m07_branch_selection", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, branch=None, trace=trace + [{"event": "M07_BRANCH_REQUIRED"}])
        result.update({"m11_route": route, "candidate_branches": sorted(ALLOWED_BRANCHES), "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": build_department_handoff(route, None), "next_action": "select_one_branch_from_existing_facts_or_ask_one_routing_question"})
        return result
    if photo.get("handoff_required"):
        result = _envelope(status="awaiting_m08_photo_handoff", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, branch=consultation_branch, trace=trace + [{"event": "M08_HANDOFF_REQUIRED"}])
        result.update({"m11_route": route, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": build_department_handoff(route, consultation_branch), "next_action": "send_photo_task_to_m08_then_return_through_m00_and_m11"})
        return result

    approved, blocked = gate_knowledge_context(knowledge_context, task=task, branch=consultation_branch)
    result = _envelope(status="ready_for_base_model", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, branch=consultation_branch, trace=trace + [{"event": "M07_BRANCH_CONFIRMED", "branch": consultation_branch}, {"event": "KNOWLEDGE_GATE_APPLIED", "approved_count": len(approved), "blocked_count": len(blocked)}])
    result.update({"m11_route": route, "approved_knowledge_context": approved, "blocked_knowledge_context": blocked, "department_handoff": build_department_handoff(route, consultation_branch), "offline_required": bool(route.get("offline_required")) or consultation_branch in {"mass", "trauma", "neuro"}, "next_action": "base_model_generate_then_m11_review_then_m00_final_guard"})
    return result


def guard_user_output(text: str, *, safety_level: str) -> dict[str, Any]:
    violations = [{"reason": reason, "matched": match.group(0)} for pattern, reason in FORBIDDEN_OUTPUT_PATTERNS if (match := re.search(pattern, text, flags=re.IGNORECASE))]
    if safety_level in HALT_LEVELS and not re.search(r"立即|马上|综合医院急诊|急诊科|呼叫急救", text):
        violations.append({"reason": "M00紧急行动未保留", "matched": ""})
    return {"passed": not violations, "violations": violations, "reviewed_by": ["M11_BOUNDARY_GUARD", "M00_FINAL_GUARD"], "safety_level": safety_level}
