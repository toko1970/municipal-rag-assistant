"""Feature-flagged Question Contract and facet classification query flow."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Callable
from uuid import UUID

from src.asset_store import AssetReader, LocalAssetReader, VisualEvidenceAsset
from src.classification_contract_v2 import (
    ClassificationResultV2,
    DisplayAnswerV2,
    decide_classification_v2,
    parse_answer_output_v3,
    parse_classification_output_v2,
    parse_question_contract_v2,
    render_display_answer_v2,
)
from src.contracts import SearchHit, VectorIndex
from src.llm_provider import StructuredLLMProvider
from src.query_service import (
    QueryEventLogger,
    _evidence_payload,
)
from src.version_resolution import (
    build_version_resolution_prompt,
    parse_version_resolution,
)


QUESTION_CONTRACT_PROMPT_VERSION = "question-contract-v1"
GENERATION_PROMPT_V3_VERSION = "answer-facet-claims-v3-candidate"
CLASSIFICATION_PROMPT_V2_VERSION = "classification-facet-v2-candidate"
CLASSIFICATION_DECISION_V2_VERSION = "classification-rubric-v2.0"
VERSION_RESOLUTION_PROMPT_VERSION = "version-resolution-v2"
VERSION_RESOLUTION_CONFIDENCE_THRESHOLD = 0.80


def build_question_contract_prompt(question: str) -> str:
    return (
        "質問だけを読み、question-contract-v1のJSONを返してください。"
        "requested_facetsは質問が直接求める回答項目へ分け、input_factsには質問に明記された"
        "日付・金額・数量・条件・対象・出来事だけを記録してください。input_factsから回答分類を決めず、"
        "epistemic_status等の確実性ラベルを追加しないでください。\n"
        f"質問: {question}"
    )


def build_generation_prompt_v3(
    question: str,
    question_contract: dict,
    hits: list[SearchHit],
    visual_assets: dict[UUID, VisualEvidenceAsset] | None = None,
) -> str:
    payload = {
        "question": question,
        "question_contract": question_contract,
        "retrieved_evidence": _evidence_payload(hits, visual_assets),
    }
    return (
        "answer-output-v3-candidateに従い、取得根拠だけを使ったfacet付きclaimを返してください。"
        "各claimは答えるfacet、使用するquestion input、検証済み計算、文書根拠をIDで参照します。"
        "質問外の注意事項をmissing_conditionsへ追加しないでください。"
        "自由文の最終表示や回答分類は返さないでください。\n"
        f"生成対象: {json.dumps(payload, ensure_ascii=False)}"
    )


def build_classification_prompt_v2(
    question: str,
    question_contract: dict,
    hits: list[SearchHit],
    answer_data: dict,
) -> str:
    payload = {
        "question": question,
        "question_contract": question_contract,
        "retrieved_evidence": _evidence_payload(hits),
        "generated_answer": answer_data,
    }
    return (
        "classification-output-v2-candidateに従い、最終ラベルではなく各requested facetの"
        "evidence_coverage、claim_support、human_review_requirementsを返してください。"
        "質問内の事実は文書根拠ではなく入力値です。文書に判断基準があり、その事実が結論を"
        "変える場合だけcase_factにします。文書に判断基準がない場合はevidence_coverageを"
        "insufficientとし、人による確認要件を作らないでください。\n"
        f"判定対象: {json.dumps(payload, ensure_ascii=False)}"
    )


def _claim_log_rows(display: DisplayAnswerV2) -> list[dict]:
    return [
        {
            "claim_id": claim.claim_id,
            "ordinal": claim.ordinal,
            "text": claim.text,
            "evidence_element_ids": list(claim.evidence_element_ids),
        }
        for claim in display.visible_claims
    ]


def _classification_factors(
    question_contract: dict,
    classification: ClassificationResultV2,
) -> dict:
    return {
        "schema_version": "2.0-candidate",
        "decision_version": CLASSIFICATION_DECISION_V2_VERSION,
        "question_contract": question_contract,
        "facet_assessments": [
            {
                "facet_id": assessment.facet_id,
                "claim_ids": list(assessment.claim_ids),
                "claim_support": assessment.claim_support,
                "evidence_coverage": assessment.evidence_coverage,
                "human_review_requirements": [
                    {
                        "review_id": review.review_id,
                        "type": review.requirement_type,
                        "description": review.description,
                        "condition_ids": list(review.condition_ids),
                        "evidence_element_ids": [
                            str(value) for value in review.evidence_element_ids
                        ],
                    }
                    for review in assessment.human_review_requirements
                ],
                "evidence_element_ids": [
                    str(value) for value in assessment.evidence_element_ids
                ],
                "confidence": assessment.confidence,
            }
            for assessment in classification.facet_assessments
        ],
    }


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


def answer_question_v2(
    question: str,
    *,
    embed_query: Callable[[str], list[float]],
    vector_index: VectorIndex,
    question_contract_provider: StructuredLLMProvider,
    generator: StructuredLLMProvider,
    classifier: StructuredLLMProvider,
    event_logger: QueryEventLogger,
    question_contract_schema: dict,
    answer_schema: dict,
    classification_schema: dict,
    top_k: int = 5,
    visual_asset_loader: Callable[[list[UUID]], list[VisualEvidenceAsset]]
    | None = None,
    asset_reader: AssetReader | None = None,
    max_visual_assets: int = 3,
    version_resolver: StructuredLLMProvider | None = None,
    version_resolution_schema: dict | None = None,
    version_resolution_confidence_threshold: float = (
        VERSION_RESOLUTION_CONFIDENCE_THRESHOLD
    ),
) -> dict:
    if max_visual_assets < 0:
        raise ValueError("max_visual_assetsは0以上である必要があります")
    if not 0 <= version_resolution_confidence_threshold <= 1:
        raise ValueError("version resolution confidence thresholdは0以上1以下です")
    if (version_resolver is None) != (version_resolution_schema is None):
        raise ValueError("version resolverとschemaは両方指定する必要があります")
    request_id = event_logger.start_request(question)
    contract_result = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        retrieval_future = executor.submit(
            lambda: vector_index.search(embed_query(question), limit=top_k)
        )
        contract_future = executor.submit(
            question_contract_provider.generate_structured,
            build_question_contract_prompt(question),
            question_contract_schema,
        )
        try:
            contract_result = contract_future.result()
            contract_data = contract_result.data
            contract = parse_question_contract_v2(contract_data)
        except Exception as exc:
            event_logger.record_classification_attempt(
                request_id,
                provider=(
                    contract_result.provider
                    if contract_result
                    else question_contract_provider.provider_name
                ),
                model=(
                    contract_result.model
                    if contract_result
                    else question_contract_provider.model
                ),
                prompt_version=QUESTION_CONTRACT_PROMPT_VERSION,
                factors=(
                    {"question_contract": contract_result.data}
                    if contract_result
                    else None
                ),
                derived_label=None,
                confidence=None,
                status="CONTRACT_FAILED",
                error_summary=str(exc)[:1000],
            )
            raise
        event_logger.record_classification_attempt(
            request_id,
            provider=contract_result.provider,
            model=contract_result.model,
            prompt_version=QUESTION_CONTRACT_PROMPT_VERSION,
            factors={"question_contract": contract_data},
            derived_label=None,
            confidence=None,
            status="SUCCESS",
            error_summary=None,
        )
        hits = retrieval_future.result()

    event_logger.record_retrieval(request_id, hits)

    visual_assets: dict[UUID, VisualEvidenceAsset] = {}
    visual_content: dict[UUID, bytes] = {}
    generation_result = None
    try:
        if visual_asset_loader is not None:
            loaded_assets = visual_asset_loader([hit.element.id for hit in hits])
            loaded_by_id = {asset.element_id: asset for asset in loaded_assets}
            visual_assets = {
                hit.element.id: loaded_by_id[hit.element.id]
                for hit in hits
                if hit.element.id in loaded_by_id
            }
            visual_assets = dict(list(visual_assets.items())[:max_visual_assets])
        prompt = build_generation_prompt_v3(
            question, contract_data, hits, visual_assets
        )
        if visual_assets:
            if not hasattr(generator, "generate_structured_with_media"):
                raise TypeError("図表根拠にはmultimodal対応generatorが必要です")
            reader = asset_reader or LocalAssetReader()
            visual_content = {
                element_id: reader.read(asset)
                for element_id, asset in visual_assets.items()
            }
            generation_result = generator.generate_structured_with_media(
                prompt,
                answer_schema,
                media=[
                    (visual_content[element_id], asset.mime_type)
                    for element_id, asset in visual_assets.items()
                ],
            )
        else:
            generation_result = generator.generate_structured(prompt, answer_schema)
        answer_data = generation_result.data
        answer = parse_answer_output_v3(answer_data)
    except Exception as exc:
        event_logger.record_generation_attempt(
            request_id,
            provider=(
                generation_result.provider
                if generation_result
                else generator.provider_name
            ),
            model=generation_result.model if generation_result else generator.model,
            prompt_version=GENERATION_PROMPT_V3_VERSION,
            response_data=generation_result.data if generation_result else None,
            input_tokens=generation_result.input_tokens if generation_result else 0,
            output_tokens=generation_result.output_tokens if generation_result else 0,
            status="GENERATION_FAILED",
            error_summary=str(exc)[:1000],
        )
        raise
    event_logger.record_generation_attempt(
        request_id,
        provider=generation_result.provider,
        model=generation_result.model,
        prompt_version=GENERATION_PROMPT_V3_VERSION,
        response_data=answer_data,
        input_tokens=generation_result.input_tokens,
        output_tokens=generation_result.output_tokens,
        status="SUCCESS",
        error_summary=None,
    )

    classification_result = None
    try:
        classification_result = classifier.generate_structured(
            build_classification_prompt_v2(question, contract_data, hits, answer_data),
            classification_schema,
        )
        classification = parse_classification_output_v2(classification_result.data)
    except Exception as exc:
        event_logger.record_classification_attempt(
            request_id,
            provider=(
                classification_result.provider
                if classification_result
                else classifier.provider_name
            ),
            model=(
                classification_result.model
                if classification_result
                else classifier.model
            ),
            prompt_version=CLASSIFICATION_PROMPT_V2_VERSION,
            factors=None,
            derived_label=None,
            confidence=None,
            status="CLASSIFICATION_FAILED",
            error_summary=str(exc)[:1000],
        )
        raise

    base_decision = decide_classification_v2(
        contract,
        answer,
        classification,
        {hit.element.id for hit in hits},
    )
    if base_decision.status != "SUCCESS":
        version_metadata = {
            "status": "NOT_REQUIRED",
            "applied": False,
            "fallback_used": False,
            "prompt_version": VERSION_RESOLUTION_PROMPT_VERSION,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        resolver_factors = None
    else:
        classification, version_metadata, resolver_factors = (
            _resolve_version_requirements(
                question=question,
                hits=hits,
                answer_data=answer_data,
                classification=classification,
                version_resolver=version_resolver,
                version_resolution_schema=version_resolution_schema,
                confidence_threshold=version_resolution_confidence_threshold,
            )
        )
    if resolver_factors is not None:
        event_logger.record_classification_attempt(
            request_id,
            provider=version_metadata["provider"],
            model=version_metadata["model"],
            prompt_version=VERSION_RESOLUTION_PROMPT_VERSION,
            factors=resolver_factors,
            derived_label=None,
            confidence=version_metadata.get("confidence"),
            status=version_metadata["status"],
            fallback_used=version_metadata["fallback_used"],
            error_summary=version_metadata.get("error_summary"),
        )

    decision = decide_classification_v2(
        contract,
        answer,
        classification,
        {hit.element.id for hit in hits},
    )
    display = render_display_answer_v2(answer, classification, decision)
    event_logger.record_classification_attempt(
        request_id,
        provider=classification_result.provider,
        model=classification_result.model,
        prompt_version=CLASSIFICATION_PROMPT_V2_VERSION,
        factors=_classification_factors(contract_data, classification),
        derived_label=decision.label,
        confidence=classification.confidence,
        status=decision.status,
        fallback_used=version_metadata["fallback_used"],
        error_summary=(
            decision.invariant_code if decision.status != "SUCCESS" else None
        ),
    )
    event_logger.record_answer_result(
        request_id,
        label=display.label,
        display_text=display.text,
        claims=_claim_log_rows(display),
        status=display.status,
    )
    return {
        "request_id": str(request_id),
        "question": question,
        "question_contract": contract_data,
        "answer": display.text,
        "answer_label": display.label,
        "answer_status": display.status,
        "degraded": display.status != "SUCCESS",
        "invariant_code": display.invariant_code,
        "claims": _claim_log_rows(display),
        "references": _evidence_payload(
            hits, visual_assets, display_content=visual_content
        ),
        "question_contract_generation": contract_result.metadata(),
        "generation": generation_result.metadata(),
        "classification": classification_result.metadata(),
        "classification_decision_version": CLASSIFICATION_DECISION_V2_VERSION,
        "version_resolution": version_metadata,
        "visual_evidence_count": len(visual_assets),
    }
