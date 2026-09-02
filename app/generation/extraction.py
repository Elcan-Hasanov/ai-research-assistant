from enum import Enum
from pydantic import BaseModel, ValidationError


class ExtractionErrorCause(str, Enum):
    """Specific cause categories for LLM extraction failure."""

    UNPARSEABLE = "unparseable"
    SCHEMA_VIOLATION = "schema_violation"


class ExtractionValidationError(Exception):
    """Raised when LLM text extraction or JSON validation fails."""

    def __init__(self, message: str, cause: ExtractionErrorCause, details: list[dict]):
        super().__init__(message)
        self.cause = cause
        self.details = details


class PaperFacts(BaseModel):
    """Extracted core research paper facts."""

    problem: str
    contributions: list[str]
    evaluated: bool


def parse_paper_facts(raw_text: str) -> PaperFacts:
    """Parse raw LLM JSON response and validate against PaperFacts schema.

    Raises:
        ExtractionValidationError: If raw_text is invalid JSON or does not match schema.
    """
    try:
        return PaperFacts.model_validate_json(raw_text)
    except ValidationError as exc:

        safe_details = [
            {
                "type": err["type"],
                "loc": err["loc"],
                "msg": err["msg"],
            }
            for err in exc.errors()
        ]

        first_type = safe_details[0]["type"]
        
        cause = (
            ExtractionErrorCause.UNPARSEABLE
            if first_type == "json_invalid"
            else ExtractionErrorCause.SCHEMA_VIOLATION
        )

        raise ExtractionValidationError(
            message="LLM output validation failed.",
            cause=cause,
            details=safe_details,
        ) from exc