# This deliverable is considered developed content as defined in contract between BDF parties.


"""Validation functions for synthetic error generation."""

from typing import Optional


def validate_response(response: str, original: str, field: Optional[str] = None) -> str:
    """Validate and clean up LLM responses.

    Args:
        response: Raw response from LLM
        original: Original value being modified
        field: Optional field name for field-specific validation

    Returns:
        Cleaned and validated response

    Raises:
        ValueError: If response fails validation
    """
    # Remove any explanatory text and clean up
    lines = [
        line
        for line in response.strip().split("\n")
        if not any(
            x in line.lower()
            for x in [
                "sorry",
                "apolog",
                "concern",
                "suggest",
                "privacy",
                "dignity",
                "harm",
            ]
        )
    ]
    if not lines:
        raise ValueError("Response contains only apologetic text")

    value = lines[0].strip().strip("\"'->[] ")

    # Ensure we got a modification
    if value.lower() == original.lower():
        raise ValueError("Response matches original value")

    # Field-specific validation
    if field:
        if field in ["sex", "isCellLine", "isPrimaryCell", "isXenograft"]:
            # Boolean/enumeration fields should be short
            if len(value) > 20:
                raise ValueError("Value too long for enumeration field")
        elif field in ["diagnosis", "tumorType", "platform"]:
            # Technical fields can have more variation
            if len(value) > len(original) * 2:
                raise ValueError("Value too long for technical field")
        else:
            # Default length validation
            if len(value) < len(original) * 0.5 or len(value) > len(original) * 1.5:
                raise ValueError("Response length too different from original")

    # Check for common error patterns
    if any(x in value.lower() for x in ["wholesale", "retail", "commercial"]):
        raise ValueError("Invalid business terminology in response")

    if "sorry" in value.lower() or "apolog" in value.lower():
        raise ValueError("Apologetic text in response")

    return value
