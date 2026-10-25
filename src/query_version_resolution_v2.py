"""Version conflict resolution for the facet based query flow."""

from __future__ import annotations

from dataclasses import replace

from src.classification_contract_v2 import ClassificationResultV2
from src.contracts import SearchHit
from src.llm_provider import StructuredLLMProvider
from src.query_prompts import _evidence_payload
from src.version_resolution import (
    build_version_resolution_prompt,
    parse_version_resolution,
)


VERSION_RESOLUTION_PROMPT_VERSION = "version-resolution-v2"
VERSION_RESOLUTION_CONFIDENCE_THRESHOLD = 0.80


def _resolve_version_requirements(
    *,
    question: str,
    hits: list[SearchHit],
    answer_data: dict,
    classification: ClassificationResultV2,
    version_resolver: StructuredLLMProvider | None,
    version_resolution_schema: dict | None,
    confidence_threshold: float,
) -> tuple[ClassificationResultV2, dict, dict | None]:
    has_version_requirement = any(
        review.requirement_type == "version_conflict"
        for assessment in classification.facet_assessments
        for review in assessment.human_review_requirements
    )
    metadata = {
        "status": "NOT_CONFIGURED" if version_resolver is None else "NOT_REQUIRED",
        "applied": False,
        "fallback_used": False,
        "prompt_version": VERSION_RESOLUTION_PROMPT_VERSION,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    if not has_version_requirement or version_resolver is None:
        return classification, metadata, None
    if version_resolution_schema is None:
        raise ValueError("version resolverとschemaは両方指定する必要があります")

    result = None
    try:
        result = version_resolver.generate_structured(
            build_version_resolution_prompt(
                question, _evidence_payload(hits), answer_data
            ),
            version_resolution_schema,
        )
        resolution = parse_version_resolution(result.data)
        if not set(resolution.evidence_element_ids) <= {hit.element.id for hit in hits}:
            raise ValueError("resolverが取得外の根拠IDを返しました")
        if resolution.confidence < confidence_threshold:
            metadata = {
                **result.metadata(),
                "status": "LOW_CONFIDENCE_FALLBACK",
                "applied": False,
                "fallback_used": True,
                "prompt_version": VERSION_RESOLUTION_PROMPT_VERSION,
            }
            return (
                classification,
                metadata,
                {
                    "baseline_version_conflict": True,
                    "applied": False,
                },
            )
        assessments = tuple(
            replace(
                assessment,
                human_review_requirements=tuple(
                    review
                    for review in assessment.human_review_requirements
                    if review.requirement_type != "version_conflict"
                    or resolution.version_conflict
                ),
            )
            for assessment in classification.facet_assessments
        )
        metadata = {
            **result.metadata(),
            "status": "SUCCESS",
            "applied": True,
            "fallback_used": False,
            "prompt_version": VERSION_RESOLUTION_PROMPT_VERSION,
            "version_conflict": resolution.version_conflict,
            "resolution_basis": resolution.resolution_basis,
            "evidence_element_ids": [
                str(value) for value in resolution.evidence_element_ids
            ],
            "confidence": resolution.confidence,
        }
        return (
            replace(classification, facet_assessments=assessments),
            metadata,
            {
                "baseline_version_conflict": True,
                "resolved_version_conflict": resolution.version_conflict,
                "applied": True,
            },
        )
    except Exception as exc:
        metadata = {
            "provider": result.provider if result else version_resolver.provider_name,
            "model": result.model if result else version_resolver.model,
            "status": "RESOLUTION_FAILED",
            "applied": False,
            "fallback_used": True,
            "prompt_version": VERSION_RESOLUTION_PROMPT_VERSION,
            "input_tokens": result.input_tokens if result else 0,
            "output_tokens": result.output_tokens if result else 0,
            "error_summary": str(exc)[:1000],
        }
        return (
            classification,
            metadata,
            {
                "baseline_version_conflict": True,
                "applied": False,
            },
        )


def _apply_resolved_version_conditions(answer, classification, version_metadata: dict):
    if not version_metadata.get("applied") or version_metadata.get("version_conflict"):
        return answer, classification
    resolved_ids = {
        condition.condition_id
        for condition in answer.missing_conditions
        if condition.condition_type == "version_conflict"
    }
    if not resolved_ids:
        return answer, classification
    remaining = [
        condition for condition in answer.missing_conditions
        if condition.condition_id not in resolved_ids
    ]
    id_map = {
        condition.condition_id: f"condition-{index}"
        for index, condition in enumerate(remaining, start=1)
    }
    answer = replace(
        answer,
        missing_conditions=tuple(
            replace(condition, condition_id=id_map[condition.condition_id])
            for condition in remaining
        ),
        claims=tuple(
            replace(
                claim,
                depends_on_condition_ids=tuple(
                    id_map[condition_id]
                    for condition_id in claim.depends_on_condition_ids
                    if condition_id in id_map
                ),
            )
            for claim in answer.claims
        ),
    )
    assessments = tuple(
        replace(
            assessment,
            human_review_requirements=tuple(
                replace(
                    review,
                    condition_ids=tuple(
                        id_map[condition_id]
                        for condition_id in review.condition_ids
                        if condition_id in id_map
                    ),
                )
                for review in assessment.human_review_requirements
            ),
        )
        for assessment in classification.facet_assessments
    )
    return answer, replace(classification, facet_assessments=assessments)
