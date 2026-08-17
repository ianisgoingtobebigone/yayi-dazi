from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


M05_FIELD_IDS = {f"M05-FLD-{index:03d}" for index in range(1, 19)}
SHARED_FIELD_IDS = {f"M01-FLD-{index:03d}" for index in range(1, 16)}

ALLOWED_FACT_STATUSES = {
    "affirmed",
    "denied",
    "uncertain",
    "unknown",
    "not_applicable",
    "conflicted",
    "historical",
    "documented",
}
ALLOWED_SOURCE_TYPES = {
    "user_current",
    "user_history",
    "clinician_record",
    "device_document",
    "third_party",
    "linked_module_fact",
    "system_state",
}
ALLOWED_TASKS = {
    "intake_support",
    "problem_education",
    "assessment_explanation",
    "category_comparison",
    "maintenance",
    "record_explanation",
    "photo_observation",
}
ALLOWED_MODULES = {f"M{index:02d}" for index in range(2, 9)}
ALLOWED_ROUTE_STATUSES = {
    "confirmed",
    "provisional",
    "needs_clarification",
    "route_unresolved",
}

CONTINUABLE_LEVELS = {"N1", "S0"}
LIMITED_LEVELS = {"U1"}
HALT_LEVELS = {"E0", "E1"}
ALL_M00_LEVELS = HALT_LEVELS | LIMITED_LEVELS | CONTINUABLE_LEVELS | {
    "NEEDS_CLARIFICATION"
}

PHOTO_METADATA_KEYS = {
    "provided",
    "media_ids",
    "source_type",
    "user_request",
    "m08_linked_fact_ids",
}
PHOTO_OBSERVATION_KEYS = {
    "technical_quality",
    "visible_observations",
    "visible_observations_only",
    "diagnosis",
    "assessment",
    "findings",
}

KNOWLEDGE_ID_PATTERN = re.compile(
    r"^(?:M05-(?:DXM|PRB|MNT)|M09-TRT)-\d{3}$"
)
INTERNAL_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:M05-(?:FLD|DLG|FLO|RUL|OUT|DXM|PRB|MNT)|M09-TRT)-[A-Z0-9-]*\d{3}(?![A-Za-z0-9])"
)

DEPARTMENT_DIRECTIONS: dict[str, tuple[str, str]] = {
    "M02": ("牙体牙髓科", "医院口腔科或口腔综合科"),
    "M03": ("牙周科", "医院口腔科或口腔综合科"),
    "M04": ("口腔黏膜科或口腔内科", "医院口腔科或口腔综合科"),
    "M05": ("口腔修复科", "医院口腔科或口腔综合科"),
    "M06": ("口腔正畸科", "医院口腔科或口腔综合科"),
    "M07": ("口腔颌面外科或医院相应专科门诊", "医院口腔科现场分诊"),
}

FORBIDDEN_USER_OUTPUT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?:你|您)(?:就是|得了|患有)", "把远程信息写成确诊"),
    (r"(?:已经|可以)?确诊", "把远程信息写成确诊"),
    (r"(?:可以|能够|基本)排除", "作出排除性结论"),
    (r"(?:最像|大概率|基本确定|肯定是)", "输出未经验证的个体概率或确定性"),
    (r"\b\d+(?:\.\d+)?\s*%", "输出未经验证的个体概率"),
    (r"(?:医生.{0,6}做坏|设计错误|材料不合格|粘接失败|维护不到位)", "对修复质量或责任作出归责"),
    (
        r"(?:你|您).{0,4}适合.{0,5}(?:种植|固定桥|活动义齿|可摘义齿|重做|重衬|重基托|调磨|重新粘接|拔牙)",
        "替当前用户选择个人修复或处理方案",
    ),
    (
        r"(?:你|您).{0,24}(?:最适合|很适合|更适合|应该|必须|一定要|首选|建议).{0,12}(?:种植|固定桥|活动义齿|可摘义齿|重做|重衬|重基托|调磨|重新粘接|拔牙)",
        "替当前用户选择个人修复或处理方案",
    ),
    (
        r"(?:根据|结合|按)(?:你|您)(?:的)?.{0,24}(?:种植|固定桥|活动义齿|可摘义齿|重做|重衬|重基托|调磨|重新粘接|拔牙).{0,8}(?:最好|首选|最合适)",
        "替当前用户选择个人修复或处理方案",
    ),
    (
        r"建议(?:你|您).{0,8}(?:种植|做固定桥|戴活动义齿|重做|重衬|重基托|调磨|重新粘接|拔牙)",
        "替当前用户选择个人修复或处理方案",
    ),
    (
        r"(?:你|您)(?:必须|一定要)(?:拍|做|查|接受)",
        "把专业评估背景写成个人必做检查",
    ),
    (
        r"(?:自行|自己).{0,10}(?:拆|撬|打磨|弯折|掰|垫衬|粘接|修理|强行摘戴|强行取戴|调整)",
        "提供自行调整或修理指令",
    ),
    (
        r"(?:用|拿)(?:钳子|镊子|砂纸|锉刀|刀片|螺丝刀).{0,10}(?:拆|撬|磨|弯|修|取)",
        "提供器械操作指令",
    ),
    (r"(?<!\d)(?:911|999|111)(?!\d)", "包含非中国本土紧急服务号码"),
    (r"(?:NHS|urgent care|海外急诊)", "包含境外医疗服务入口"),
    (INTERNAL_ID_PATTERN.pattern, "向用户暴露内部字段、规则或知识编号"),
)


class M05ContractError(ValueError):
    """Raised when M05 is called outside its approved safety or evidence contract."""


def _validate_safety_result(safety_result: Mapping[str, Any] | None) -> dict[str, Any]:
    if not safety_result:
        raise M05ContractError("M05_REQUIRES_M00_RESULT")
    level = str(safety_result.get("effective_level", ""))
    if level not in ALL_M00_LEVELS:
        raise M05ContractError(f"unsupported M00 effective_level: {level}")
    basis = safety_result.get("basis_from_user", [])
    if not isinstance(basis, list):
        raise M05ContractError("M00 basis_from_user must be a list")
    return {
        "effective_level": level,
        "risk_floor_level": safety_result.get("risk_floor_level"),
        "next_state": safety_result.get("next_state"),
        "basis_from_user": list(basis),
        "uncertainties": list(safety_result.get("uncertainties", [])),
        "user_message_zh": safety_result.get("user_message_zh"),
        "time_to_care": safety_result.get("time_to_care"),
        "destination": safety_result.get("destination"),
        "urgency_owned_by": "M00",
    }


def validate_facts(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for index, fact in enumerate(facts):
        field_id = str(fact.get("field_id", ""))
        if field_id not in M05_FIELD_IDS | SHARED_FIELD_IDS:
            raise M05ContractError(f"fact {index} uses an unapproved field ID: {field_id}")

        status = str(fact.get("value_status", fact.get("status", "")))
        if status not in ALLOWED_FACT_STATUSES:
            raise M05ContractError(f"fact {index} has unsupported status: {status}")

        source_type = str(fact.get("source_type", ""))
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise M05ContractError(f"fact {index} has unsupported source_type: {source_type}")

        raw_spans = fact.get("basis_spans", [])
        if isinstance(raw_spans, str):
            raw_spans = [raw_spans]
        if not isinstance(raw_spans, Sequence):
            raise M05ContractError(f"fact {index} basis_spans must be a list")
        basis_spans = [str(item).strip() for item in raw_spans if str(item).strip()]
        if status not in {"unknown", "not_applicable"} and not basis_spans:
            raise M05ContractError(f"fact {index} is missing basis_spans")

        if "value" not in fact:
            raise M05ContractError(f"fact {index} is missing value")

        validated.append(
            {
                "field_id": field_id,
                "value_status": status,
                "value": fact["value"],
                "source_type": source_type,
                "basis_spans": basis_spans,
                "source_date": fact.get("source_date"),
                "linked_fact_id": fact.get("linked_fact_id"),
            }
        )
    return validated


def group_facts(facts: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {
        "affirmed": [],
        "denied": [],
        "uncertain_or_conflicted": [],
        "historical_or_documented": [],
        "not_for_user_display": [],
    }
    for fact in facts:
        status = str(fact["value_status"])
        projected = dict(fact)
        if status == "affirmed":
            groups["affirmed"].append(projected)
        elif status == "denied":
            groups["denied"].append(projected)
        elif status in {"uncertain", "conflicted"}:
            groups["uncertain_or_conflicted"].append(projected)
        elif status in {"historical", "documented"}:
            groups["historical_or_documented"].append(projected)
        else:
            groups["not_for_user_display"].append(projected)
    return groups


def register_photo_context(photo_context: Mapping[str, Any] | None) -> dict[str, Any]:
    if not photo_context or not photo_context.get("provided"):
        return {
            "provided": False,
            "handoff_required": False,
            "handoff_target": None,
            "m05_observations": [],
            "m08_linked_fact_ids": [],
        }

    prohibited = set(photo_context) & PHOTO_OBSERVATION_KEYS
    if prohibited:
        raise M05ContractError(
            f"M05_CANNOT_ACCEPT_PHOTO_OBSERVATIONS: {sorted(prohibited)}"
        )
    unknown = set(photo_context) - PHOTO_METADATA_KEYS
    if unknown:
        raise M05ContractError(f"unsupported M05 photo metadata: {sorted(unknown)}")

    media_ids = photo_context.get("media_ids", [])
    if not isinstance(media_ids, list) or not all(str(item).strip() for item in media_ids):
        raise M05ContractError("photo media_ids must be a non-empty list")

    linked_fact_ids = photo_context.get("m08_linked_fact_ids", [])
    if not isinstance(linked_fact_ids, list):
        raise M05ContractError("m08_linked_fact_ids must be a list")
    for fact_id in linked_fact_ids:
        if not re.fullmatch(r"FACT-[A-Za-z0-9_-]+", str(fact_id)):
            raise M05ContractError(f"invalid M08 linked fact ID: {fact_id}")

    return {
        "provided": True,
        "media_ids": [str(item) for item in media_ids],
        "source_type": str(photo_context.get("source_type", "user_upload")),
        "user_request": str(photo_context.get("user_request", "")),
        "handoff_required": not bool(linked_fact_ids),
        "handoff_target": "M08",
        "m05_observations": [],
        "m08_linked_fact_ids": [str(item) for item in linked_fact_ids],
        "limitations": [
            "M05只登记照片和M08关联事实ID，不生成图像观察",
            "照片不能确认边缘密合、咬合、深部支持、材料、种植部件或修复质量",
            "照片不得降低M00已确定的紧迫度",
        ],
    }


def validate_m11_route(route_result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if route_result is None:
        return None
    if route_result.get("assembled_by") != "M11":
        raise M05ContractError("M05_REQUIRES_M11_BUSINESS_ROUTE")
    forbidden_safety_keys = {
        "effective_level",
        "risk_floor_level",
        "time_to_care",
        "destination",
        "urgency",
    }
    overlap = set(route_result) & forbidden_safety_keys
    if overlap:
        raise M05ContractError(
            f"M11 route must not alter M00 safety fields: {sorted(overlap)}"
        )

    route_status = str(route_result.get("route_status", ""))
    if route_status not in ALLOWED_ROUTE_STATUSES:
        raise M05ContractError(f"unsupported M11 route_status: {route_status}")

    primary = route_result.get("primary_module")
    if primary is not None and str(primary) not in ALLOWED_MODULES:
        raise M05ContractError(f"unsupported primary_module: {primary}")
    secondary = route_result.get("secondary_module")
    if isinstance(secondary, list):
        raise M05ContractError("M11 may return at most one secondary_module")
    if secondary is not None and str(secondary) not in ALLOWED_MODULES:
        raise M05ContractError(f"unsupported secondary_module: {secondary}")
    if primary is not None and secondary == primary:
        raise M05ContractError("primary_module and secondary_module must differ")
    if primary is None and route_status not in {"needs_clarification", "route_unresolved"}:
        raise M05ContractError("primary_module may be null only when routing remains unresolved")

    route_history = route_result.get("route_history", [])
    if not isinstance(route_history, list):
        raise M05ContractError("route_history must be a list")
    return {
        "primary_module": str(primary) if primary is not None else None,
        "secondary_module": str(secondary) if secondary is not None else None,
        "route_status": route_status,
        "health_first": bool(route_result.get("health_first", False)),
        "offline_required": bool(route_result.get("offline_required", False)),
        "route_history": list(route_history),
        "assembled_by": "M11",
    }


def build_department_handoff(route: Mapping[str, Any]) -> dict[str, Any]:
    primary = route.get("primary_module")
    route_status = route.get("route_status")
    if primary is None or route_status in {"needs_clarification", "route_unresolved"}:
        return {
            "ordinary_candidates_only": True,
            "primary": "医院口腔科或口腔综合科",
            "fallback": "由现场检查后分诊",
            "secondary": None,
            "route_unresolved": True,
            "urgency_owned_by": "M00",
            "assembled_by": "M11",
        }

    primary_direction = DEPARTMENT_DIRECTIONS.get(
        str(primary), ("医院口腔科或口腔综合科", "由现场检查后分诊")
    )
    secondary = route.get("secondary_module")
    secondary_direction = (
        DEPARTMENT_DIRECTIONS[str(secondary)][0]
        if secondary in DEPARTMENT_DIRECTIONS and secondary != "M08"
        else None
    )
    return {
        "ordinary_candidates_only": True,
        "primary": primary_direction[0],
        "fallback": primary_direction[1],
        "secondary": secondary_direction,
        "route_unresolved": False,
        "health_first": bool(route.get("health_first", False)),
        "urgency_owned_by": "M00",
        "assembled_by": "M11",
    }


def gate_knowledge_context(
    knowledge_context: Sequence[Mapping[str, Any]] | None,
    *,
    task: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    approved: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    for index, item in enumerate(knowledge_context or []):
        knowledge_id = str(item.get("knowledge_id", ""))
        if not KNOWLEDGE_ID_PATTERN.fullmatch(knowledge_id):
            raise M05ContractError(
                f"knowledge item {index} uses unsupported knowledge ID: {knowledge_id}"
            )
        if item.get("review_status") != "approved":
            blocked.append({"knowledge_id": knowledge_id, "reason": "not_approved"})
            continue
        source_refs = item.get("source_refs", [])
        if not isinstance(source_refs, list) or not source_refs:
            blocked.append({"knowledge_id": knowledge_id, "reason": "missing_source_refs"})
            continue
        eligible_tasks = item.get("eligible_tasks")
        if eligible_tasks is not None:
            if not isinstance(eligible_tasks, list):
                raise M05ContractError(
                    f"knowledge item {index} eligible_tasks must be a list"
                )
            if task not in eligible_tasks:
                blocked.append({"knowledge_id": knowledge_id, "reason": "task_mismatch"})
                continue
        approved.append(
            {
                "knowledge_id": knowledge_id,
                "name_zh": str(item.get("name_zh", "")),
                "summary": item.get("summary"),
                "source_refs": list(source_refs),
                "user_disclosure_policy": item.get(
                    "user_disclosure_policy", "education"
                ),
                "must_not_infer": list(item.get("must_not_infer", [])),
                "retrieval_relation": "context_only",
                "review_status": "approved",
            }
        )
    return approved, blocked


def _base_envelope(
    *,
    status: str,
    task: str,
    user_task: str,
    safety: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
    photo_registration: Mapping[str, Any],
    trace: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "cn-dental-m05.output.v1",
        "module": "M05",
        "status": status,
        "task": task,
        "user_task": user_task,
        "output_rule_ids": ["M05-OUT-001", "M05-OUT-030"],
        "safety": dict(safety),
        "fact_groups": group_facts(facts),
        "photo_registration": dict(photo_registration),
        "capability_boundary_zh": "本输出不是诊断、责任判断或个人修复方案",
        "trace": [dict(item) for item in trace],
    }


def run_m05(
    *,
    task: str,
    user_task: str,
    facts: Sequence[Mapping[str, Any]],
    safety_result: Mapping[str, Any] | None,
    route_result: Mapping[str, Any] | None = None,
    photo_context: Mapping[str, Any] | None = None,
    knowledge_context: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prepare a constrained M05 evidence package; it never selects a personal plan."""
    if task not in ALLOWED_TASKS:
        raise M05ContractError(f"unsupported M05 task: {task}")
    safety = _validate_safety_result(safety_result)
    validated_facts = validate_facts(facts)
    photo_registration = register_photo_context(photo_context)

    trace: list[dict[str, Any]] = [
        {"event": "M00_RESULT_VERIFIED", "effective_level": safety["effective_level"]},
        {"event": "M01_M05_FACTS_VALIDATED", "fact_count": len(validated_facts)},
    ]
    if photo_registration["provided"]:
        trace.append(
            {
                "event": "PHOTO_REGISTERED_FOR_M08",
                "media_count": len(photo_registration["media_ids"]),
                "handoff_required": photo_registration["handoff_required"],
            }
        )

    if safety["effective_level"] in HALT_LEVELS:
        result = _base_envelope(
            status="halted_by_m00",
            task=task,
            user_task=user_task,
            safety=safety,
            facts=validated_facts,
            photo_registration=photo_registration,
            trace=trace + [{"event": "M05_HALTED", "reason": safety["effective_level"]}],
        )
        result.update(
            {
                "m11_route": None,
                "approved_knowledge_context": [],
                "blocked_knowledge_context": [],
                "department_handoff": None,
                "next_action": "execute_m00_route_without_continuing_m05",
            }
        )
        return result

    if safety["effective_level"] == "NEEDS_CLARIFICATION":
        result = _base_envelope(
            status="waiting_for_m00_clarification",
            task=task,
            user_task=user_task,
            safety=safety,
            facts=validated_facts,
            photo_registration=photo_registration,
            trace=trace + [{"event": "M05_PAUSED_FOR_M00_CLARIFICATION"}],
        )
        result.update(
            {
                "m11_route": None,
                "approved_knowledge_context": [],
                "blocked_knowledge_context": [],
                "department_handoff": None,
                "next_action": "ask_only_m00_clarification",
            }
        )
        return result

    if safety["effective_level"] in LIMITED_LEVELS:
        result = _base_envelope(
            status="limited_by_m00",
            task=task,
            user_task=user_task,
            safety=safety,
            facts=validated_facts,
            photo_registration=photo_registration,
            trace=trace + [{"event": "M05_LIMITED_BEFORE_KNOWLEDGE", "reason": "U1"}],
        )
        result.update(
            {
                "m11_route": None,
                "approved_knowledge_context": [],
                "blocked_knowledge_context": [],
                "department_handoff": {
                    "ordinary_candidates_only": False,
                    "primary": safety.get("destination"),
                    "urgency_owned_by": "M00",
                },
                "model_handoff": {
                    "base_model_required": True,
                    "required_output_sections": [
                        "M00紧迫度与行动",
                        "一至三项关键事实",
                        "一个线下未决问题",
                        "能力边界",
                    ],
                    "prohibitions": [
                        "不得继续普通修复问诊、维护解释或修复类别比较",
                        "不得用普通科室方向覆盖M00安全去向",
                    ],
                },
                "next_action": "limited_handoff_to_m11_then_m00_final_guard",
            }
        )
        return result

    route = validate_m11_route(route_result)
    if route is None:
        result = _base_envelope(
            status="awaiting_m11_business_route",
            task=task,
            user_task=user_task,
            safety=safety,
            facts=validated_facts,
            photo_registration=photo_registration,
            trace=trace + [{"event": "M11_ROUTE_REQUIRED"}],
        )
        result.update(
            {
                "m11_route": None,
                "route_submission": {
                    "candidate_modules": ["M05"],
                    "safety_owned_by": "M00",
                    "facts_only": True,
                },
                "approved_knowledge_context": [],
                "blocked_knowledge_context": [],
                "department_handoff": None,
                "next_action": "request_m11_business_route_without_recalculating_safety",
            }
        )
        return result

    trace.append(
        {
            "event": "M11_BUSINESS_ROUTE_VERIFIED",
            "primary_module": route["primary_module"],
            "secondary_module": route["secondary_module"],
            "route_status": route["route_status"],
        }
    )

    if photo_registration["provided"] and photo_registration["handoff_required"]:
        result = _base_envelope(
            status="awaiting_m08_photo_handoff",
            task=task,
            user_task=user_task,
            safety=safety,
            facts=validated_facts,
            photo_registration=photo_registration,
            trace=trace + [{"event": "M08_HANDOFF_REQUIRED"}],
        )
        result.update(
            {
                "m11_route": route,
                "approved_knowledge_context": [],
                "blocked_knowledge_context": [],
                "department_handoff": build_department_handoff(route),
                "next_action": "dispatch_photo_to_m08_then_return_via_m00_and_m11",
            }
        )
        return result

    approved_knowledge, blocked_knowledge = gate_knowledge_context(
        knowledge_context, task=task
    )
    trace.append(
        {
            "event": "M10_KNOWLEDGE_GATE_COMPLETED",
            "approved_count": len(approved_knowledge),
            "blocked_count": len(blocked_knowledge),
        }
    )
    department_handoff = build_department_handoff(route)

    result = _base_envelope(
        status="ready_for_base_model",
        task=task,
        user_task=user_task,
        safety=safety,
        facts=validated_facts,
        photo_registration=photo_registration,
        trace=trace,
    )
    result.update(
        {
            "m11_route": route,
            "approved_knowledge_context": approved_knowledge,
            "blocked_knowledge_context": blocked_knowledge,
            "retrieval_gap": not bool(approved_knowledge),
            "department_handoff": department_handoff,
            "model_handoff": {
                "base_model_required": True,
                "required_output_sections": [
                    "M00安全行动（如需显示）",
                    "当前目标与有来源事实",
                    "明确否认、不确定或冲突、历史资料",
                    "线上不能确认的具体事项",
                    "已批准的一般知识（如有）",
                    "线下决定点",
                    "M11组装的中国化科室方向",
                    "已保留的美观或其他目标（如有）",
                    "能力边界",
                ],
                "prohibitions": [
                    "不得确诊、排除疾病或输出个体概率",
                    "不得评价修复质量、医生责任、材料或用户维护责任",
                    "不得选择个人修复、调整、修理、重衬、重做或检查方案",
                    "不得提供器械、手术、拆卸、粘接、打磨、弯折、垫衬或自行修理步骤",
                    "不得把照片写成M05专业检查结论",
                    "不得显示未批准知识或内部ID",
                ],
            },
            "next_action": "base_model_synthesis_then_m11_review_and_m00_final_guard",
        }
    )
    return result


def guard_user_output(text: str, *, safety_level: str) -> dict[str, Any]:
    """Conservative M11-style backstop before the final M00 guard."""
    if safety_level not in ALL_M00_LEVELS:
        raise M05ContractError(f"unsupported M00 effective_level: {safety_level}")

    violations: list[dict[str, str]] = []
    for pattern, reason in FORBIDDEN_USER_OUTPUT_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            violations.append({"pattern": pattern, "reason": reason})

    if safety_level in HALT_LEVELS and not any(
        token in text for token in ("急诊", "立即", "尽快前往", "马上前往")
    ):
        violations.append(
            {"pattern": "m00_action_missing", "reason": "E0/E1输出未保留M00紧急行动"}
        )
    if safety_level == "U1" and not any(
        token in text for token in ("24小时", "当天", "尽快")
    ):
        violations.append(
            {"pattern": "u1_time_missing", "reason": "U1输出未保留M00的及时行动"}
        )

    return {
        "passed": not violations,
        "violations": violations,
        "next_action": (
            "send_to_m00_final_guard"
            if not violations
            else "regenerate_without_lowering_m00_or_expanding_m05_authority"
        ),
    }
