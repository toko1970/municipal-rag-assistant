"""Shared serialization helpers for query audit and response payloads."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def serialize_claims(
    claims: Iterable[Any], *, include_facet_details: bool = False
) -> list[dict[str, Any]]:
    rows = []
    for claim in claims:
        row = {
            "claim_id": claim.claim_id,
            "ordinal": claim.ordinal,
            "text": claim.text,
            "evidence_element_ids": list(claim.evidence_element_ids),
        }
        if include_facet_details:
            row["claim_type"] = claim.claim_type
            row["depends_on_condition_ids"] = list(claim.depends_on_condition_ids)
        rows.append(row)
    return rows


def classification_answer_payload(answer, raw_data: dict) -> dict:
    schema_version = raw_data.get("schema_version")
    if schema_version == "1.0":
        return raw_data
    payload = {
        "schema_version": schema_version,
        "claims": [
            {
                "claim_id": claim.claim_id,
                "ordinal": claim.ordinal,
                "text": claim.text,
                "evidence_element_ids": [
                    str(value) for value in claim.evidence_element_ids
                ],
                "evidence_kind": claim.evidence_kind,
            }
            for claim in answer.claims
        ],
        "date_calculations": [
            {
                "calculation_id": calculation.calculation_id,
                "result_label": calculation.result_label,
                "anchor_date": calculation.anchor_date.isoformat(),
                "offset_value": calculation.offset_value,
                "offset_unit": calculation.offset_unit,
                "counting_rule": calculation.counting_rule,
                "cutoff_time": (
                    calculation.cutoff_time.isoformat()
                    if calculation.cutoff_time is not None
                    else None
                ),
                "evidence_element_ids": [
                    str(value) for value in calculation.evidence_element_ids
                ],
            }
            for calculation in answer.date_calculations
        ],
    }
    if schema_version == "1.1":
        payload["missing_conditions"] = [
            condition.description for condition in answer.missing_conditions
        ]
    else:
        payload["missing_conditions"] = [
            {
                "type": condition.condition_type,
                "description": condition.description,
                "evidence_element_ids": [
                    str(value) for value in condition.evidence_element_ids
                ],
            }
            for condition in answer.missing_conditions
        ]
    return payload
