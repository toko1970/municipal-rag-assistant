"""Compatibility exports for structured answer and classification handling."""

from src.answer_contract import (
    AnswerClaim as AnswerClaim,
    DateCalculation as DateCalculation,
    MISSING_CONDITION_TYPES as MISSING_CONDITION_TYPES,
    MissingCondition as MissingCondition,
    StructuredAnswer as StructuredAnswer,
    parse_answer_output as parse_answer_output,
    validate_answer_evidence as validate_answer_evidence,
)
from src.answer_classification import (
    ClassificationFactors as ClassificationFactors,
    ClassificationResult as ClassificationResult,
    derive_label as derive_label,
    parse_classification_output as parse_classification_output,
)
from src.answer_display import (
    DisplayAnswer as DisplayAnswer,
    DisplayContractError as DisplayContractError,
    render_display_answer as render_display_answer,
    render_pipeline_inconsistency as render_pipeline_inconsistency,
)
