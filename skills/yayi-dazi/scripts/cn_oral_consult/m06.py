from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


M06_FIELD_IDS = {f"M06-FLD-{index:03d}" for index in range(1, 23)}
SHARED_FIELD_IDS = {f"M01-FLD-{index:03d}" for index in range(1, 16)}
ALLOWED_FACT_STATUSES = {
    "affirmed", "denied", "uncertain", "unknown", "not_applicable",
    "conflicted", "historical", "documented",
}
ALLOWED_SOURCE_TYPES = {
    "user_current", "user_history", "clinician_record", "device_document",
    "third_party", "linked_module_fact", "system_state",
}
ALLOWED_TASKS = {
    "intake_support", "goal_clarification", "problem_education",
    "assessment_explanation", "category_comparison", "maintenance",
    "retention_education", "record_explanation", "photo_observation",
}
ALLOWED_MODULES = {f"M{index:02d}" for index in range(2, 9)}
ALLOWED_ROUTE_STATUSES = {"confirmed", "provisional", "needs_clarification", "route_unresolved"}
ALL_M00_LEVELS = {"E0", "E1", "U1", "N1", "S0", "NEEDS_CLARIFICATION"}
HALT_LEVELS = {"E0", "E1"}
PHOTO_METADATA_KEYS = {
    "provided", "media_ids", "source_type", "user_request",
    "requested_views", "requested_capture_views", "requested_observation_profiles", "m08_linked_fact_ids",
}
PHOTO_OBSERVATION_KEYS = {
    "technical_quality", "visible_observations", "diagnosis", "assessment",
    "findings", "skeletal_class", "dental_or_skeletal_origin",
}
ALLOWED_PHOTO_TASKS = {
    "intraoral_frontal", "intraoral_right", "intraoral_left",
    "upper_arch", "lower_arch", "face_frontal_rest", "face_frontal_smile",
    "face_profile", "prosthesis_or_appliance_area", "wound_or_device_area",
    "gingiva_region", "mucosal_region", "single_tooth_or_area",
}
ALLOWED_CAPTURE_VIEWS = {
    "frontal_rest", "profile_rest", "oblique_45_rest", "frontal_smile",
    "profile_smile", "oblique_45_smile", "intraoral_right",
    "intraoral_frontal", "intraoral_left", "anterior_overbite_overjet",
    "upper_arch", "lower_arch",
}
ALLOWED_ORTHODONTIC_OBSERVATION_PROFILES = {
    *(f"M08-ORTHO-PAT-{index:03d}" for index in range(1, 10)),
    *(f"M08-ORTHO-DEV-{index:03d}" for index in range(1, 8)),
}
KNOWLEDGE_ID_PATTERN = re.compile(r"^(?:M06-(?:DXM|PRB|MNT)-\d{3}|M09-TRT-0(?:2[8-9]|3[0-8]))$")
INTERNAL_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:M06-(?:FLD|DLG|FLO|RUL|OUT|DXM|PRB|MNT)|M09-TRT|M08-ORTHO-(?:PAT|DEV))-[A-Z0-9-]*\d{3}(?![A-Za-z0-9])"
)

DEPARTMENTS = {
    "M02": ("牙体牙髓科", "医院口腔科或口腔综合科"),
    "M03": ("牙周科", "医院口腔科或口腔综合科"),
    "M04": ("口腔黏膜科或口腔内科", "医院口腔科或口腔综合科"),
    "M05": ("口腔修复科", "医院口腔科或口腔综合科"),
    "M06": ("口腔正畸科", "医院口腔科或口腔综合科"),
    "M07": ("口腔颌面外科或医院相应专科门诊", "医院口腔科现场分诊"),
}

AESTHETIC_SCREEN_KEYS = {
    "adult_confirmed", "explicit_aesthetic_goal", "no_health_features",
    "no_functional_features", "asymmetry_long_term_stable_or_absent",
    "m00_allows_ordinary",
}

FORBIDDEN_OUTPUT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?:你|您)(?:就是|得了|患有)", "把远程信息写成确诊"),
    (r"(?:已经|可以)?确诊|(?:可以|能够|基本)排除", "作出确诊或排除性结论"),
    (r"(?:最像|大概率|基本确定|肯定是)|\b\d+(?:\.\d+)?\s*%", "输出未经验证的个体概率"),
    (r"(?:你|您)(?:是|属于).{0,8}(?:骨性|牙性|牙槽性)", "远程确定牙颌面来源"),
    (r"(?:脸歪|面部不对称|下巴偏).{0,8}(?:就是|肯定|一定|主要).{0,8}(?:牙齿|颌骨).{0,4}(?:导致|造成)", "建立未经线下评估的因果关系"),
    (r"(?:牙齿|颌骨).{0,8}(?:就是|肯定|一定|主要).{0,8}(?:导致|造成).{0,8}(?:脸歪|面部不对称|下巴偏)", "建立未经线下评估的因果关系"),
    (r"(?:你|您).{0,28}(?:适合|最适合|应该|必须|一定要|首选|建议).{0,16}(?:隐形矫治|隐形牙套|固定矫治|金属牙套|陶瓷牙套|拔牙|正颌手术|种植钉|骨钉)", "替当前用户选择个人正畸或正颌方案"),
    (r"建议(?:你|您).{0,12}(?:戴牙套|矫牙|拔牙|做正颌|打骨钉|用橡皮筋)", "替当前用户选择个人方案"),
    (r"(?:矫正后|治疗后).{0,8}(?:一定|肯定|保证).{0,12}(?:脸|侧貌|下巴|对称|好看)", "承诺个体外观结果"),
    (r"(?:自行|自己).{0,12}(?:加力|弯|剪|磨|粘|调整|换下一副|延长佩戴|缩短佩戴|戴橡皮筋)", "提供自行调整矫治装置或方案的指令"),
    (r"(?<!\d)(?:911|999|111)(?!\d)|(?:NHS|urgent care|海外急诊)", "包含境外医疗服务入口"),
    (INTERNAL_ID_PATTERN.pattern, "向用户暴露内部编号"),
)


class M06ContractError(ValueError):
    """Raised when M06 is used outside its approved contract."""


def _validate_safety_result(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        raise M06ContractError("M06_REQUIRES_M00_RESULT")
    level = str(value.get("effective_level", ""))
    if level not in ALL_M00_LEVELS:
        raise M06ContractError(f"unsupported M00 effective_level: {level}")
    basis = value.get("basis_from_user", [])
    if not isinstance(basis, list):
        raise M06ContractError("M00 basis_from_user must be a list")
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


def evaluate_aesthetic_entry(screen: Mapping[str, Any] | None) -> dict[str, Any]:
    if screen is None:
        return {"screen_status": "not_run", "pure_aesthetic_allowed": False, "health_first_required": False, "failed_conditions": []}
    unknown = set(screen) - AESTHETIC_SCREEN_KEYS
    missing = AESTHETIC_SCREEN_KEYS - set(screen)
    if unknown or missing:
        raise M06ContractError(f"invalid aesthetic screen keys; missing={sorted(missing)}, unknown={sorted(unknown)}")
    values = {key: bool(screen[key]) for key in AESTHETIC_SCREEN_KEYS}
    failed = sorted(key for key, passed in values.items() if not passed)
    pure = not failed
    health_first = bool(values["explicit_aesthetic_goal"] and (
        not values["no_health_features"]
        or not values["no_functional_features"]
        or not values["asymmetry_long_term_stable_or_absent"]
    ))
    return {
        "screen_status": "complete",
        "pure_aesthetic_allowed": pure,
        "health_first_required": health_first,
        "failed_conditions": failed,
    }


def validate_facts(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for index, fact in enumerate(facts):
        field_id = str(fact.get("field_id", ""))
        if field_id not in M06_FIELD_IDS | SHARED_FIELD_IDS:
            raise M06ContractError(f"fact {index} uses an unapproved field ID: {field_id}")
        status = str(fact.get("value_status", fact.get("status", "")))
        if status not in ALLOWED_FACT_STATUSES:
            raise M06ContractError(f"fact {index} has unsupported status: {status}")
        source_type = str(fact.get("source_type", ""))
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise M06ContractError(f"fact {index} has unsupported source_type: {source_type}")
        spans = fact.get("basis_spans", [])
        if isinstance(spans, str):
            spans = [spans]
        if not isinstance(spans, Sequence):
            raise M06ContractError(f"fact {index} basis_spans must be a list")
        spans = [str(item).strip() for item in spans if str(item).strip()]
        if status not in {"unknown", "not_applicable"} and not spans:
            raise M06ContractError(f"fact {index} is missing basis_spans")
        if "value" not in fact:
            raise M06ContractError(f"fact {index} is missing value")
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
        target = (
            "affirmed" if status == "affirmed" else
            "denied" if status == "denied" else
            "uncertain_or_conflicted" if status in {"uncertain", "conflicted"} else
            "historical_or_documented" if status in {"historical", "documented"} else
            "not_for_user_display"
        )
        groups[target].append(dict(fact))
    return groups


def register_photo_context(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value or not value.get("provided"):
        return {"provided": False, "handoff_required": False, "handoff_target": None, "m06_observations": [], "m08_linked_fact_ids": []}
    prohibited = set(value) & PHOTO_OBSERVATION_KEYS
    if prohibited:
        raise M06ContractError(f"M06_CANNOT_ACCEPT_PHOTO_OBSERVATIONS: {sorted(prohibited)}")
    unknown = set(value) - PHOTO_METADATA_KEYS
    if unknown:
        raise M06ContractError(f"unsupported M06 photo metadata: {sorted(unknown)}")
    media_ids = value.get("media_ids", [])
    if not isinstance(media_ids, list) or not media_ids or not all(str(item).strip() for item in media_ids):
        raise M06ContractError("photo media_ids must be a non-empty list")
    views = value.get("requested_views", [])
    if not isinstance(views, list) or any(str(item) not in ALLOWED_PHOTO_TASKS for item in views):
        raise M06ContractError("photo requested_views contains an unsupported M08 task")
    capture_views = value.get("requested_capture_views", [])
    if not isinstance(capture_views, list) or any(str(item) not in ALLOWED_CAPTURE_VIEWS for item in capture_views):
        raise M06ContractError("photo requested_capture_views contains an unsupported standard view")
    profiles = value.get("requested_observation_profiles", [])
    if not isinstance(profiles, list) or any(str(item) not in ALLOWED_ORTHODONTIC_OBSERVATION_PROFILES for item in profiles):
        raise M06ContractError("photo requested_observation_profiles contains an unsupported orthodontic profile")
    linked = value.get("m08_linked_fact_ids", [])
    if not isinstance(linked, list) or any(not re.fullmatch(r"FACT-[A-Za-z0-9_-]+", str(item)) for item in linked):
        raise M06ContractError("invalid M08 linked fact IDs")
    return {
        "provided": True,
        "media_ids": [str(item) for item in media_ids],
        "source_type": str(value.get("source_type", "user_upload")),
        "user_request": str(value.get("user_request", "")),
        "requested_views": [str(item) for item in views],
        "requested_capture_views": [str(item) for item in capture_views],
        "requested_observation_profiles": [str(item) for item in profiles],
        "handoff_required": not bool(linked),
        "handoff_target": "M08",
        "m06_observations": [],
        "m08_linked_fact_ids": [str(item) for item in linked],
        "limitations": [
            "M06只定义图像任务并登记M08关联事实，不生成图像观察",
            "普通照片不能确定错𬌗分类、牙性或骨性来源、真实咬合、牙周支持或个人方案",
            "照片不得降低M00紧迫度或否定用户感受",
        ],
    }


def validate_m11_route(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if value.get("assembled_by") != "M11":
        raise M06ContractError("M06_REQUIRES_M11_BUSINESS_ROUTE")
    forbidden = {"effective_level", "risk_floor_level", "time_to_care", "destination", "urgency"}
    overlap = set(value) & forbidden
    if overlap:
        raise M06ContractError(f"M11 route must not alter M00 safety fields: {sorted(overlap)}")
    status = str(value.get("route_status", ""))
    if status not in ALLOWED_ROUTE_STATUSES:
        raise M06ContractError(f"unsupported M11 route_status: {status}")
    primary = value.get("primary_module")
    secondary = value.get("secondary_module")
    if primary is not None and str(primary) not in ALLOWED_MODULES:
        raise M06ContractError(f"unsupported primary_module: {primary}")
    if isinstance(secondary, list):
        raise M06ContractError("M11 may return at most one secondary_module")
    if secondary is not None and str(secondary) not in ALLOWED_MODULES:
        raise M06ContractError(f"unsupported secondary_module: {secondary}")
    if primary == secondary and primary is not None:
        raise M06ContractError("primary_module and secondary_module must differ")
    if primary is None and status not in {"needs_clarification", "route_unresolved"}:
        raise M06ContractError("primary_module may be null only when routing remains unresolved")
    history = value.get("route_history", [])
    if not isinstance(history, list):
        raise M06ContractError("route_history must be a list")
    return {
        "primary_module": str(primary) if primary is not None else None,
        "secondary_module": str(secondary) if secondary is not None else None,
        "route_status": status,
        "health_first": bool(value.get("health_first", False)),
        "offline_required": bool(value.get("offline_required", False)),
        "route_history": list(history),
        "assembled_by": "M11",
    }


def build_department_handoff(route: Mapping[str, Any]) -> dict[str, Any]:
    primary = route.get("primary_module")
    if primary is None or route.get("route_status") in {"needs_clarification", "route_unresolved"}:
        return {"ordinary_candidates_only": True, "primary": "医院口腔科或口腔综合科", "fallback": "由现场检查后分诊", "secondary": None, "route_unresolved": True, "urgency_owned_by": "M00", "assembled_by": "M11"}
    primary_name, fallback = DEPARTMENTS.get(str(primary), ("医院口腔科或口腔综合科", "由现场检查后分诊"))
    secondary = route.get("secondary_module")
    secondary_name = DEPARTMENTS[str(secondary)][0] if secondary in DEPARTMENTS and secondary != "M08" else None
    return {"ordinary_candidates_only": True, "primary": primary_name, "fallback": fallback, "secondary": secondary_name, "route_unresolved": False, "health_first": bool(route.get("health_first")), "urgency_owned_by": "M00", "assembled_by": "M11"}


def gate_knowledge_context(items: Sequence[Mapping[str, Any]] | None, *, task: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    approved, blocked = [], []
    for index, item in enumerate(items or []):
        knowledge_id = str(item.get("knowledge_id", ""))
        if not KNOWLEDGE_ID_PATTERN.fullmatch(knowledge_id):
            raise M06ContractError(f"knowledge item {index} uses unsupported knowledge ID: {knowledge_id}")
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
        if item.get("runtime_scope") == "out_of_adult_runtime":
            blocked.append({"knowledge_id": knowledge_id, "reason": "outside_adult_runtime_scope"})
            continue
        approved.append({
            "knowledge_id": knowledge_id,
            "name_zh": str(item.get("name_zh", "")),
            "summary": item.get("summary"),
            "runtime_scope": item.get("runtime_scope", "adult_runtime"),
            "source_refs": list(refs),
            "must_not_infer": list(item.get("must_not_infer", [])),
            "retrieval_relation": "context_only",
            "review_status": "approved",
        })
    return approved, blocked


def _envelope(*, status: str, task: str, user_task: str, safety: Mapping[str, Any], facts: Sequence[Mapping[str, Any]], photo: Mapping[str, Any], entry: Mapping[str, Any], trace: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "cn-dental-m06.output.v1",
        "module": "M06",
        "status": status,
        "task": task,
        "user_task": user_task,
        "output_rule_ids": ["M06-OUT-001", "M06-OUT-028"],
        "safety": dict(safety),
        "entry_assessment": dict(entry),
        "fact_groups": group_facts(facts),
        "photo_registration": dict(photo),
        "capability_boundary_zh": "本输出不是诊断、个人正畸或正颌方案，也不预测治疗效果",
        "trace": [dict(item) for item in trace],
    }


def run_m06(
    *, task: str, user_task: str, facts: Sequence[Mapping[str, Any]],
    safety_result: Mapping[str, Any] | None, route_result: Mapping[str, Any] | None = None,
    age_group: str = "adult", aesthetic_screen: Mapping[str, Any] | None = None,
    photo_context: Mapping[str, Any] | None = None,
    knowledge_context: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a constrained M06 evidence package without diagnosing or selecting a plan."""
    if task not in ALLOWED_TASKS:
        raise M06ContractError(f"unsupported M06 task: {task}")
    safety = _validate_safety_result(safety_result)
    validated_facts = validate_facts(facts)
    photo = register_photo_context(photo_context)
    entry = evaluate_aesthetic_entry(aesthetic_screen)
    trace = [
        {"event": "M00_RESULT_VERIFIED", "effective_level": safety["effective_level"]},
        {"event": "M01_M06_FACTS_VALIDATED", "fact_count": len(validated_facts)},
        {"event": "M06_ENTRY_SCREEN_RECORDED", "screen_status": entry["screen_status"]},
    ]

    if age_group != "adult":
        result = _envelope(status="out_of_adult_scope", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, entry=entry, trace=trace + [{"event": "ADULT_SCOPE_NOT_CONFIRMED"}])
        result.update({"m11_route": None, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": {"primary": "医院口腔科或具备资质的口腔专业人员", "note": "成人首版规则不用于未成年人个体正畸判断"}, "next_action": "adult_scope_handoff_without_applying_m06_rules"})
        return result

    if safety["effective_level"] in HALT_LEVELS:
        result = _envelope(status="halted_by_m00", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, entry=entry, trace=trace + [{"event": "M06_HALTED"}])
        result.update({"m11_route": None, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": None, "next_action": "execute_m00_route_without_continuing_m06"})
        return result
    if safety["effective_level"] == "NEEDS_CLARIFICATION":
        result = _envelope(status="waiting_for_m00_clarification", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, entry=entry, trace=trace + [{"event": "M06_PAUSED_FOR_M00_CLARIFICATION"}])
        result.update({"m11_route": None, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": None, "next_action": "ask_only_m00_clarification"})
        return result
    if safety["effective_level"] == "U1":
        result = _envelope(status="limited_by_m00", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, entry=entry, trace=trace + [{"event": "M06_LIMITED_BEFORE_KNOWLEDGE"}])
        result.update({"m11_route": None, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": {"ordinary_candidates_only": False, "primary": safety.get("destination"), "urgency_owned_by": "M00"}, "next_action": "limited_handoff_to_m11_then_m00_final_guard"})
        return result

    route = validate_m11_route(route_result)
    if route is None:
        result = _envelope(status="awaiting_m11_business_route", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, entry=entry, trace=trace + [{"event": "M11_ROUTE_REQUIRED"}])
        result.update({"m11_route": None, "route_submission": {"candidate_modules": ["M06"], "safety_owned_by": "M00", "facts_only": True}, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": None, "next_action": "request_m11_business_route_without_recalculating_safety"})
        return result

    if entry["health_first_required"] and route["primary_module"] == "M06" and not route["health_first"]:
        raise M06ContractError("health_or_function_features_require_health_first_route")
    if photo["provided"] and photo["handoff_required"]:
        result = _envelope(status="awaiting_m08_photo_handoff", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, entry=entry, trace=trace + [{"event": "M08_HANDOFF_REQUIRED"}])
        result.update({"m11_route": route, "approved_knowledge_context": [], "blocked_knowledge_context": [], "department_handoff": build_department_handoff(route), "next_action": "dispatch_photo_to_m08_then_return_via_m00_and_m11"})
        return result

    approved, blocked = gate_knowledge_context(knowledge_context, task=task)
    result = _envelope(status="ready_for_base_model", task=task, user_task=user_task, safety=safety, facts=validated_facts, photo=photo, entry=entry, trace=trace + [{"event": "M11_BUSINESS_ROUTE_VERIFIED"}, {"event": "M10_KNOWLEDGE_GATE_COMPLETED", "approved_count": len(approved), "blocked_count": len(blocked)}])
    result.update({
        "m11_route": route,
        "approved_knowledge_context": approved,
        "blocked_knowledge_context": blocked,
        "retrieval_gap": not bool(approved),
        "department_handoff": build_department_handoff(route),
        "model_handoff": {
            "base_model_required": True,
            "required_output_sections": ["M00安全行动（如需）", "用户目标与健康/美观先后", "有来源事实、否认、历史与不确定性", "当前咨询维度", "已批准的一般知识（如有）", "线上不能确认和线下决定点", "M11中国化科室方向", "能力边界"],
            "prohibitions": ["不得确诊错𬌗、判断牙性或骨性来源及病因", "不得选择矫治器、拔牙、支抗或正颌方案", "不得预测脸型改变或治疗效果", "不得把普通照片写成正畸专业检查结论", "不得提供自行调整装置或佩戴方案步骤", "不得显示内部ID或未批准知识"],
        },
        "next_action": "base_model_synthesis_then_m11_review_and_m00_final_guard",
    })
    return result


def guard_user_output(text: str, *, safety_level: str) -> dict[str, Any]:
    if safety_level not in ALL_M00_LEVELS:
        raise M06ContractError(f"unsupported M00 effective_level: {safety_level}")
    violations = [
        {"pattern": pattern, "reason": reason}
        for pattern, reason in FORBIDDEN_OUTPUT_PATTERNS
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]
    if safety_level in HALT_LEVELS and not any(token in text for token in ("急诊", "立即", "尽快前往", "马上前往")):
        violations.append({"pattern": "m00_action_missing", "reason": "E0/E1输出未保留M00紧急行动"})
    if safety_level == "U1" and not any(token in text for token in ("24小时", "当天", "尽快")):
        violations.append({"pattern": "u1_time_missing", "reason": "U1输出未保留M00及时行动"})
    return {"passed": not violations, "violations": violations, "next_action": "send_to_m00_final_guard" if not violations else "regenerate_without_expanding_m06_authority"}
