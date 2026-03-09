# This deliverable is considered developed content as defined in contract between BDF parties.


"""Error type definitions for synthetic error generation."""


class ErrorType:
    """Types of errors that can be generated."""

    FUZZY = "fuzzy"
    SEMANTIC = "semantic"
    CONTEXTUAL = "contextual"
    FORMAT = "format"
    CASE_SPACING = "case_spacing"
    ABBREVIATION = "abbreviation"


class FieldErrorGenerator:
    """Generates field-specific errors based on field characteristics."""

    def __init__(self, field_name: str, valid_options: list[str]):
        self.field_name = field_name
        self.valid_options = valid_options
        self.error_patterns = self._get_field_patterns()

    def _get_field_patterns(self) -> dict[str, float]:
        """Return error pattern weights based on field type."""
        # Basic fields with simple values
        if self.field_name in [
            "sex",
            "species",
            "isCellLine",
            "isPrimaryCell",
            "isXenograft",
        ]:
            return {
                ErrorType.FUZZY: 0.3,
                ErrorType.SEMANTIC: 0.4,
                ErrorType.CASE_SPACING: 0.3,
            }
        # Complex fields with technical terms
        elif self.field_name in ["diagnosis", "tumorType", "assay", "platform"]:
            return {
                ErrorType.ABBREVIATION: 0.4,
                ErrorType.SEMANTIC: 0.3,
                ErrorType.FORMAT: 0.3,
            }
        # Numeric or identifier fields
        elif self.field_name in [
            "age",
            "progressReportNumber",
            "id",
            "entityId",
            "studyId",
        ]:
            return {ErrorType.FORMAT: 0.5, ErrorType.FUZZY: 0.5}
        # Default pattern for other fields
        return {
            ErrorType.FUZZY: 0.25,
            ErrorType.SEMANTIC: 0.25,
            ErrorType.FORMAT: 0.25,
            ErrorType.CASE_SPACING: 0.25,
        }
