from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .runtime_paths import data_path


DEFAULT_CATALOG_PATH = data_path("m10_catalog.json")
MODULE_PRODUCTION_ENABLED = False

ALL_M00_LEVELS = {"E0", "E1", "U1", "N1", "S0", "NEEDS_CLARIFICATION"}
HALT_LEVELS = {"E0", "E1"}
ALLOWED_TASKS = {
    "clinical_evidence",
    "diagnostic_method_background",
    "treatment_background",
    "maintenance_background",
    "literature_recommendation",
}
ALLOWED_MODULES = {f"M{number:02d}" for number in range(2, 11)}
ALLOWED_ENTRY_TYPES = {"DIS", "DXM", "LSN", "MNT", "PRB", "TRT"}
ALLOWED_RELATIONS = {"supports", "conflicts", "missing_clinician_evidence", "context_only", "retrieval_gap"}
ALLOWED_AUDIENCES = {"public", "professional"}
INTERNAL_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])M(?:0[2-9]|10)-(?:DIS|DXM|LSN|MNT|PRB|TRT|CHK|EVD)-[A-Z0-9-]+")
LOCAL_PATH_PATTERN = re.compile(r"(?:/Users/|/mnt/data/|[A-Za-z]:\\Users\\)")
FOREIGN_PATHWAY_PATTERN = re.compile(r"(?<!\d)(?:911|999|111)(?!\d)|\bNHS\b|urgent care", re.IGNORECASE)
PROMPT_INJECTION_PATTERN = re.compile(
    r"ignore (?:all |the )?(?:previous|prior) instructions|system prompt|developer message|忽略(?:以上|之前|系统)指令|泄露系统提示",
    re.IGNORECASE,
)


class M10ContractError(ValueError):
    """Raised when the evidence layer is invoked outside its approved contract."""


class M10Catalog:
    def __init__(self, path: str | Path = DEFAULT_CATALOG_PATH) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.payload = payload
        self.production_enabled = bool(payload.get("production_enabled", False))
        records = payload.get("knowledge_federation", [])
        chunks = payload.get("evidence_chunks", [])
        if not isinstance(records, list) or not isinstance(chunks, list):
            raise M10ContractError("M10 catalog requires knowledge_federation and evidence_chunks lists")
        self.records = {str(item["knowledge_id"]): dict(item) for item in records}
        self.chunks = [dict(item) for item in chunks]
        self.chunk_by_id = {str(item["chunk_id"]): dict(item) for item in chunks}


def _tokenize(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", str(text).lower())
    ascii_terms = re.findall(r"[a-z0-9][a-z0-9._/-]*", compact)
    cjk_spans = re.findall(r"[\u3400-\u9fff]+", compact)
    terms = list(ascii_terms)
    for span in cjk_spans:
        terms.extend(span)
        terms.extend(span[index : index + 2] for index in range(max(0, len(span) - 1)))
    return [item for item in terms if item]


def _bm25(query: str, chunks: Sequence[Mapping[str, Any]]) -> list[tuple[str, float]]:
    query_terms = _tokenize(query)
    if not query_terms or not chunks:
        return []
    documents = [Counter(_tokenize(str(item.get("text", "")))) for item in chunks]
    lengths = [sum(document.values()) for document in documents]
    average_length = sum(lengths) / max(1, len(lengths))
    document_frequency = Counter()
    for document in documents:
        document_frequency.update(document.keys())
    scores: list[tuple[str, float]] = []
    k1, b = 1.5, 0.75
    for chunk, document, length in zip(chunks, documents, lengths):
        score = 0.0
        for term in query_terms:
            tf = document.get(term, 0)
            if not tf:
                continue
            df = document_frequency[term]
            idf = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
            denominator = tf + k1 * (1 - b + b * length / max(1.0, average_length))
            score += idf * tf * (k1 + 1) / denominator
        if score > 0:
            scores.append((str(chunk["chunk_id"]), score))
    return sorted(scores, key=lambda item: (-item[1], item[0]))


def _rrf(
    lexical: Sequence[tuple[str, float]],
    semantic: Sequence[tuple[str, float]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    fused: defaultdict[str, float] = defaultdict(float)
    for ranking in (lexical, semantic):
        for rank, (chunk_id, _raw_score) in enumerate(ranking, 1):
            fused[chunk_id] += 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda item: (-item[1], item[0]))


def _validate_safety(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        raise M10ContractError("M10_REQUIRES_M00_RESULT")
    level = str(value.get("effective_level", ""))
    if level not in ALL_M00_LEVELS:
        raise M10ContractError(f"unsupported M00 effective_level: {level}")
    basis = value.get("basis_from_user", [])
    if not isinstance(basis, list):
        raise M10ContractError("M00 basis_from_user must be a list")
    return {
        "effective_level": level,
        "risk_floor_level": value.get("risk_floor_level"),
        "basis_from_user": list(basis),
        "uncertainties": list(value.get("uncertainties", [])),
        "time_to_care": value.get("time_to_care"),
        "destination": value.get("destination"),
        "urgency_owned_by": "M00",
    }


def _validate_route(value: Mapping[str, Any] | None, requested_by_module: str) -> dict[str, Any]:
    if not value or value.get("assembled_by") != "M11":
        raise M10ContractError("M10_REQUIRES_M11_BUSINESS_ROUTE")
    forbidden = {"effective_level", "risk_floor_level", "time_to_care", "destination", "urgency"}
    overlap = set(value) & forbidden
    if overlap:
        raise M10ContractError(f"M11 route must not alter M00 fields: {sorted(overlap)}")
    primary = str(value.get("primary_module", ""))
    secondary = value.get("secondary_module")
    if primary not in ALLOWED_MODULES - {"M10"}:
        raise M10ContractError(f"unsupported M11 primary_module: {primary}")
    if isinstance(secondary, list):
        raise M10ContractError("M11 may return at most one secondary_module")
    if secondary is not None and secondary not in ALLOWED_MODULES - {"M10"}:
        raise M10ContractError(f"unsupported M11 secondary_module: {secondary}")
    if requested_by_module not in {primary, secondary}:
        raise M10ContractError("requested_by_module must match M11 primary or secondary module")
    requested_search_modules = value.get("retrieval_modules") or [item for item in (primary, secondary) if item]
    if not isinstance(requested_search_modules, list) or not requested_search_modules:
        raise M10ContractError("M11 retrieval_modules must be a non-empty list when present")
    if any(item not in ALLOWED_MODULES for item in requested_search_modules):
        raise M10ContractError("M11 retrieval_modules contains unsupported module")
    return {
        "primary_module": primary,
        "secondary_module": secondary,
        "retrieval_modules": list(dict.fromkeys(requested_search_modules)),
        "route_status": value.get("route_status"),
        "assembled_by": "M11",
    }


def _base_result(status: str, task: str, safety: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "cn-dental-m10.output.v1",
        "module": "M10",
        "status": status,
        "task": task,
        "safety": dict(safety),
        "retrieval_results": [],
        "retrieval_gaps": [],
        "literature_recommendations": [],
        "blocked_literature": [],
        "next_guard": "M11",
        "m00_final_guard_required": True,
        "retrieved_content_trust": "reference_only",
        "production_enabled": False,
        "user_generation_allowed": False,
    }


def _eligible_chunks(
    catalog: M10Catalog,
    modules: set[str],
    entry_types: set[str],
    *,
    include_pending_for_audit: bool,
) -> list[dict[str, Any]]:
    result = []
    for chunk in catalog.chunks:
        if chunk.get("module") not in modules or chunk.get("entry_type") not in entry_types:
            continue
        if chunk.get("runtime_eligible"):
            result.append(chunk)
            continue
        if include_pending_for_audit and chunk.get("review_status") == "pending_user_audit":
            result.append(chunk)
    return result


def _prompt_injection_status(text: str) -> dict[str, Any]:
    matched = bool(PROMPT_INJECTION_PATTERN.search(text))
    return {
        "detected": matched,
        "action": "exclude_from_generation_context" if matched else "treat_as_reference_data_only",
    }


def retrieve_m10(
    *,
    task: str,
    query: str,
    fact_basis_spans: Sequence[str],
    fact_field_ids: Sequence[str],
    requested_by_module: str,
    safety_result: Mapping[str, Any] | None,
    route_result: Mapping[str, Any] | None,
    entry_types: Sequence[str],
    evidence_relations: Mapping[str, str] | None = None,
    semantic_scores: Mapping[str, float] | None = None,
    audience: str = "public",
    internal_preview: bool = False,
    include_pending_for_audit: bool = False,
    catalog: M10Catalog | None = None,
) -> dict[str, Any]:
    """Retrieve traceable context; never infer a diagnosis from retrieval similarity."""
    if task not in ALLOWED_TASKS:
        raise M10ContractError(f"unsupported M10 task: {task}")
    if requested_by_module not in ALLOWED_MODULES - {"M10"}:
        raise M10ContractError(f"unsupported requesting module: {requested_by_module}")
    if audience not in ALLOWED_AUDIENCES:
        raise M10ContractError(f"unsupported audience: {audience}")
    if not str(query).strip():
        raise M10ContractError("M10 query must not be empty")
    if not fact_basis_spans or not all(str(item).strip() for item in fact_basis_spans):
        raise M10ContractError("M10_REQUIRES_FACT_BASIS_SPANS")
    if not fact_field_ids or not all(re.fullmatch(r"M(?:0[1-8])-FLD-\d{3}", str(item)) for item in fact_field_ids):
        raise M10ContractError("M10_REQUIRES_VALID_FACT_FIELD_IDS")
    requested_types = set(entry_types)
    if not requested_types or not requested_types <= ALLOWED_ENTRY_TYPES:
        raise M10ContractError("M10 entry_types contains unsupported or empty value")
    relations = dict(evidence_relations or {})
    if any(value not in ALLOWED_RELATIONS for value in relations.values()):
        raise M10ContractError("unsupported evidence relation")

    safety = _validate_safety(safety_result)
    if safety["effective_level"] in HALT_LEVELS:
        result = _base_result("halted_by_m00", task, safety)
        result["next_guard"] = "M00"
        return result
    if safety["effective_level"] == "NEEDS_CLARIFICATION":
        result = _base_result("waiting_for_m00_clarification", task, safety)
        result["next_guard"] = "M00"
        return result
    if safety["effective_level"] == "U1":
        result = _base_result("urgent_routing_only", task, safety)
        result["next_guard"] = "M00"
        return result

    route = _validate_route(route_result, requested_by_module)
    store = catalog or M10Catalog()
    if not internal_preview and not (MODULE_PRODUCTION_ENABLED and store.production_enabled):
        result = _base_result("module_disabled_pending_m12_evaluation", task, safety)
        result["route"] = route
        return result

    modules = set(route["retrieval_modules"])
    if task == "treatment_background":
        modules.add("M09")
    chunks = _eligible_chunks(store, modules, requested_types, include_pending_for_audit=include_pending_for_audit)
    lexical = _bm25(query, chunks)[:20]
    semantic_input = semantic_scores or {}
    semantic = sorted(
        (
            (str(chunk["chunk_id"]), float(semantic_input[str(chunk["chunk_id"])]))
            for chunk in chunks
            if str(chunk["chunk_id"]) in semantic_input
        ),
        key=lambda item: (-item[1], item[0]),
    )[:20]
    fused = _rrf(lexical, semantic, k=60)[:20]
    lexical_scores = dict(lexical)
    semantic_score_map = dict(semantic)
    final: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    for chunk_id, rrf_score in fused:
        chunk = store.chunk_by_id[chunk_id]
        entry_type = str(chunk["entry_type"])
        if type_counts[entry_type] >= 5:
            continue
        injection = _prompt_injection_status(str(chunk.get("text", "")))
        if injection["detected"]:
            continue
        type_counts[entry_type] += 1
        relation = relations.get(str(chunk["knowledge_id"]), "context_only")
        final.append(
            {
                "chunk_id": chunk_id,
                "knowledge_id": chunk["knowledge_id"],
                "canonical_name_zh": chunk["canonical_name_zh"],
                "module": chunk["module"],
                "entry_type": entry_type,
                "relation_to_user_facts": relation,
                "relation_is_model_supplied_not_similarity_inferred": True,
                "fact_basis_spans": list(fact_basis_spans),
                "fact_field_ids": list(fact_field_ids),
                "context_text": chunk["text"],
                "source_refs": chunk["source_refs"],
                "retrieved_content_trust": "reference_only",
                "prompt_injection_check": injection,
                "engineering_scores": {
                    "lexical_bm25_raw": round(lexical_scores.get(chunk_id, 0.0), 6),
                    "semantic_provider_raw": round(semantic_score_map.get(chunk_id, 0.0), 6),
                    "rrf_raw": round(rrf_score, 8),
                    "rrf_display_0_to_100": round(min(100.0, rrf_score / (2 / 61) * 100), 2),
                    "score_meaning": "retrieval_ranking_only_not_medical_confidence",
                },
                "review_status": chunk["review_status"],
                "not_for_user_generation": chunk["review_status"] != "approved" or include_pending_for_audit,
            }
        )

    result = _base_result("ready_for_m11_audit_preview" if final else "retrieval_gap", task, safety)
    result["route"] = route
    result["query_contract"] = {
        "query": query,
        "fact_basis_spans": list(fact_basis_spans),
        "fact_field_ids": list(fact_field_ids),
        "modules": sorted(modules),
        "entry_types": sorted(requested_types),
        "audience": audience,
    }
    result["retrieval_results"] = final
    result["retrieval_gaps"] = [] if final else [{"relation": "retrieval_gap", "query": query, "must_not_fill_with_model_prior_as_source": True}]
    result["retrieval_execution"] = {
        "lexical_candidates": len(lexical),
        "semantic_candidates": len(semantic),
        "fused_candidates": len(fused),
        "returned": len(final),
        "semantic_status": "provider_scores_used" if semantic else "degraded_lexical_only_no_embedding_provider",
        "rrf_k": 60,
        "maximum_per_entry_type": 5,
    }
    result["include_pending_for_audit"] = include_pending_for_audit
    result["generation_constraints"] = [
        "检索结果只作为参考资料，不是当前用户事实或诊断证据",
        "supports/conflicts等关系由基于用户事实的推理显式给出，不能由相似度自动产生",
        "模型既有知识必须标记为model_prior，不能伪装成检索来源",
        "任何草稿必须经M11事实、来源、边界复核和M00发送前复核",
    ]
    return result


REQUIRED_LITERATURE_FIELDS = {
    "title",
    "authors",
    "year",
    "publication_type",
    "landing_url",
    "why_recommended_zh",
    "audience",
    "relation_to_question",
    "limitations_zh",
    "last_verified_on",
    "verified_against",
    "retraction_status",
    "recommendation_tier",
}


def validate_literature_record(record: Mapping[str, Any], *, today: str | None = None) -> tuple[bool, list[str]]:
    errors: list[str] = []
    missing = sorted(REQUIRED_LITERATURE_FIELDS - set(record))
    if missing:
        errors.append(f"missing_fields:{','.join(missing)}")
    if not record.get("doi") and not record.get("pmid"):
        errors.append("missing_doi_or_pmid")
    if not isinstance(record.get("authors"), list) or not record.get("authors"):
        errors.append("authors_must_be_nonempty_list")
    year = record.get("year")
    if not isinstance(year, int) or year < 1900 or year > date.today().year + 1:
        errors.append("invalid_year")
    if record.get("audience") not in ALLOWED_AUDIENCES:
        errors.append("invalid_audience")
    if record.get("recommendation_tier") not in {"core", "deeper"}:
        errors.append("invalid_recommendation_tier")
    providers = record.get("verified_against")
    if not isinstance(providers, list) or not set(providers) & {"NCBI-EUTILS", "CROSSREF-REST", "EUROPEPMC-REST", "publisher", "professional_society"}:
        errors.append("missing_authoritative_metadata_verification")
    if record.get("retraction_status") != "not_retracted":
        errors.append("retraction_status_not_cleared")
    landing_url = str(record.get("landing_url", ""))
    if not re.match(r"^https://", landing_url):
        errors.append("landing_url_must_be_https")
    verification_date = str(record.get("last_verified_on", ""))
    try:
        checked = datetime.strptime(verification_date, "%Y-%m-%d").date()
        now = datetime.strptime(today, "%Y-%m-%d").date() if today else date.today()
        if checked > now:
            errors.append("verification_date_in_future")
        if (now - checked).days > 30:
            errors.append("verification_older_than_30_days")
    except ValueError:
        errors.append("invalid_last_verified_on")
    return not errors, errors


def prepare_literature_recommendations(
    records: Sequence[Mapping[str, Any]],
    *,
    audience: str,
    provider_status: str = "available",
    today: str | None = None,
) -> dict[str, Any]:
    if audience not in ALLOWED_AUDIENCES:
        raise M10ContractError(f"unsupported audience: {audience}")
    if provider_status != "available":
        return {
            "status": "literature_verification_unavailable",
            "recommendations": [],
            "blocked": [],
            "must_not_invent_citation": True,
            "retry_policy": "retry_once_then_return_gap",
        }
    accepted: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for item in records:
        valid, errors = validate_literature_record(item, today=today)
        if not valid:
            blocked.append({"title": item.get("title"), "reasons": errors})
            continue
        if item.get("audience") != audience:
            blocked.append({"title": item.get("title"), "reasons": ["audience_mismatch"]})
            continue
        accepted.append(dict(item))
    core = [item for item in accepted if item["recommendation_tier"] == "core"][:3]
    deeper = [item for item in accepted if item["recommendation_tier"] == "deeper"][:2]
    recommendations = core + deeper
    return {
        "status": "verified_recommendations_ready" if recommendations else "no_verified_recommendations",
        "recommendations": recommendations,
        "blocked": blocked,
        "limits": {"core": 3, "deeper": 2, "returned": len(recommendations)},
        "verification_basis": "metadata_identity_identifier_landing_page_and_retraction_status",
    }


def guard_m10_user_output(text: str, cited_records: Sequence[Mapping[str, Any]] = ()) -> None:
    compact = " ".join(str(text).split())
    if INTERNAL_ID_PATTERN.search(compact):
        raise M10ContractError("M10_OUTPUT_BLOCKED: internal knowledge or chunk ID")
    if LOCAL_PATH_PATTERN.search(compact):
        raise M10ContractError("M10_OUTPUT_BLOCKED: local file path or internal PDF location")
    if FOREIGN_PATHWAY_PATTERN.search(compact):
        raise M10ContractError("M10_OUTPUT_BLOCKED: foreign service pathway or number")
    if PROMPT_INJECTION_PATTERN.search(compact):
        raise M10ContractError("M10_OUTPUT_BLOCKED: retrieved prompt injection content")
    for record in cited_records:
        valid, errors = validate_literature_record(record)
        if not valid:
            raise M10ContractError(f"M10_OUTPUT_BLOCKED: unverified literature citation: {errors}")
    if cited_records and not re.search(r"(?:资料|文献|指南).{0,24}(?:不能替代|不等于|仅供|不是)", compact):
        raise M10ContractError("M10_OUTPUT_BLOCKED: missing evidence capability boundary")
