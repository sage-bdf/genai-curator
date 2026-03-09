# This deliverable is considered developed content as defined in contract between BDF parties.


"""Validation node for metadata correction pipeline."""

from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

# Define common null-like values
NULL_LIKE_VALUES = {"none", "na", "n/a", "null", "nil", "-", "no value"}


def is_null_like(value: str) -> bool:
    """Check if a value should be treated as null.

    Args:
        value: Value to check

    Returns:
        True if value is considered null-like, False otherwise
    """
    return str(value).lower().strip() in NULL_LIKE_VALUES


from fix_values.pipeline.core.models import (
    CellError,
    ErrorType,
    PipelineState,
    Schema,
    SchemaField,
    ValidationResult,
)
from fix_values.pipeline.nodes.base import CorrectionNode, NodeConfig


# Type conversion functions
def try_convert_to_int(value: str) -> Tuple[bool, Optional[int], Optional[str]]:
    """Try to convert string to integer.

    Args:
        value: String value to convert

    Returns:
        Tuple of (success, converted_value, error_message)
    """
    try:
        if value == "No Value":
            return True, None, None
        # Check if string represents a whole number
        float_val = float(value)
        if float_val.is_integer():
            return True, int(float_val), None
        return False, None, f"Value '{value}' is not a whole number"
    except ValueError:
        return False, None, f"Cannot convert '{value}' to integer"


def try_convert_to_float(value: str) -> Tuple[bool, Optional[float], Optional[str]]:
    """Try to convert string to float.

    Args:
        value: String value to convert

    Returns:
        Tuple of (success, converted_value, error_message)
    """
    try:
        if value == "No Value":
            return True, None, None
        return True, float(value), None
    except ValueError:
        return False, None, f"Cannot convert '{value}' to float"


def try_convert_to_bool(value: str) -> Tuple[bool, Optional[bool], Optional[str]]:
    """Try to convert string to boolean.

    Args:
        value: String value to convert

    Returns:
        Tuple of (success, converted_value, error_message)
    """
    if value == "No Value":
        return True, None, None

    true_values = {"true", "yes", "1", "t", "y"}
    false_values = {"false", "no", "0", "f", "n"}

    value_lower = value.lower()
    if value_lower in true_values:
        return True, True, None
    if value_lower in false_values:
        return True, False, None
    return (
        False,
        None,
        f"Cannot convert '{value}' to boolean. Valid values are: {true_values | false_values}",
    )


# Type conversion mapping
TYPE_CONVERTERS: Dict[str, Callable[[str], Tuple[bool, Any, Optional[str]]]] = {
    "integer": try_convert_to_int,
    "float": try_convert_to_float,
    "boolean": try_convert_to_bool,
    "string": lambda x: (True, x, None),
}


class ValidationNode(CorrectionNode[Dict[str, Any], ValidationResult]):
    """Schema validation node."""

    def __init__(
        self,
        schema: Schema,
        config: NodeConfig,
        ignore_fields: Optional[List[str]] = None,
    ) -> None:
        """Initialize validation node.

        Args:
            schema: Metadata schema
            config: Node configuration
            ignore_fields: List of field names to ignore during validation
        """
        super().__init__(config)
        self.schema = schema
        self.ignore_fields = ignore_fields or []

        # Log schema details
        logger.info(
            f"[{self.config.name}] Initializing ValidationNode with schema containing {len(self.schema.fields)} fields"
        )
        if self.ignore_fields:
            logger.info(f"[{self.config.name}] Ignoring fields: {self.ignore_fields}")

    async def _process_impl(
        self,
        state: PipelineState,
    ) -> Dict[str, Any]:
        """Validate metadata against schema.

        Args:
            state: Current pipeline state containing metadata to validate

        Returns:
            Dictionary of state updates
        """
        # Clear previous errors
        state.errors = []

        # Run validation and collect new errors
        errors: List[CellError] = []

        logger.info(
            f"[{self.config.name}] Starting validation on DataFrame with {len(state.metadata)} rows"
        )
        logger.info(
            f"[{self.config.name}] Columns in DataFrame: {list(state.metadata.columns)}"
        )
        logger.info(
            f"[{self.config.name}] Schema Field Count: {len(self.schema.fields)}"
        )

        # Validate each cell in the DataFrame
        for field in self.schema.fields:
            logger.info(f"field name: {field.name}")
            logger.info(f"field type: {field.type}")
            logger.info(f"field required: {field.required}")
            logger.info(f"field description: {field.description}")
            # Skip ignored fields
            if field.name in self.ignore_fields:
                logger.info(
                    f"[{self.config.name}] Skipping ignored field: {field.name}"
                )
                continue

            if field.name not in state.metadata.columns:
                # logger.warning(f"[{self.config.name}] Column '{field.name}' not found in DataFrame")
                if field.required:
                    logger.error(
                        f"[{self.config.name}] Required column '{field.name}' is missing"
                    )
                    # Add error for each row since column is missing
                    for idx in range(len(state.metadata)):
                        errors.append(
                            CellError(
                                row_idx=idx,
                                column=field.name,
                                value=None,
                                error_type=ErrorType.SCHEMA,
                                message=f"Required field {field.name} is missing",
                            )
                        )
                continue

            logger.info(f"[{self.config.name}] Validating column '{field.name}'")

            # Validate each value in the column
            for idx, value in enumerate(state.metadata[field.name]):
                # Skip validation for null-like values in optional fields
                if not field.required and (
                    value is None or (isinstance(value, str) and is_null_like(value))
                ):
                    continue

                # Check valid values
                if (
                    field.valid_values is not None
                ):  # Changed condition to explicitly check if valid_values exists
                    if value not in field.valid_values:
                        logger.warning(
                            f"[{self.config.name}] Invalid value in {field.name}[{idx}]: "
                            f"'{value}' not in valid options: {field.valid_values}"
                        )
                        errors.append(
                            CellError(
                                row_idx=idx,
                                column=field.name,
                                value=value,
                                error_type=ErrorType.VOCABULARY,
                                message=f"Value {value} not in valid options: {field.valid_values}",
                            )
                        )
                    else:
                        logger.debug(
                            f"[{self.config.name}] Valid value in {field.name}[{idx}]: '{value}'"
                        )
                else:
                    logger.warning(
                        f"[{self.config.name}] No valid_values defined for field {field.name}, "
                        f"cannot validate value: '{value}'"
                    )

                # Type validation and conversion
                if field.type in TYPE_CONVERTERS:
                    success, converted_value, error_msg = TYPE_CONVERTERS[field.type](
                        str(value)
                    )
                    if not success:
                        logger.warning(
                            f"[{self.config.name}] Type conversion error in {field.name}[{idx}]: {error_msg}"
                        )
                        errors.append(
                            CellError(
                                row_idx=idx,
                                column=field.name,
                                value=value,
                                error_type=ErrorType.FORMAT,
                                message=error_msg,
                            )
                        )
                        continue  # Skip constraint validation if type conversion failed
                    else:
                        # Update the value in the DataFrame with the converted value
                        state.metadata.at[idx, field.name] = converted_value
                        value = converted_value  # Use converted value for constraint validation
                else:
                    logger.warning(
                        f"[{self.config.name}] Unknown type '{field.type}' for field {field.name}"
                    )
                    continue  # Skip constraint validation if type is unknown

                # Constraint validation (only if type validation succeeded)
                if field.constraints:
                    if field.type == "string":
                        self._validate_string_constraints(field, value, idx, errors)
                    elif field.type in {"integer", "float"}:
                        self._validate_numeric_constraints(field, value, idx, errors)

        # Group errors by type for logging
        error_types: Dict[ErrorType, List[CellError]] = {}
        for error in errors:
            if error.error_type not in error_types:
                error_types[error.error_type] = []
            error_types[error.error_type].append(error)

        # Log error summary
        logger.info(
            f"[{self.config.name}] Validation complete. Found {len(errors)} total errors:"
        )
        for error_type, type_errors in error_types.items():
            logger.info(f"  - {error_type}: {len(type_errors)} errors")
            for error in type_errors:
                logger.info(f"    * {error.column}[{error.row_idx}]: {error.message}")

        result = ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            stats={"total_errors": len(errors)},
        )

        # Update state with new errors
        state.errors.extend(errors)

        # Return state updates for LangGraph
        return {
            "metadata": state.metadata,
            "errors": state.errors,
            "correction_history": state.correction_history,
            "stats": state.stats,
            "iteration": state.iteration,
        }

    def _validate_string_constraints(
        self, field: SchemaField, value: Any, row_idx: int, errors: List[CellError]
    ) -> None:
        """Validate string constraints."""
        # Skip validation for None/"No Value"
        if value is None or value == "No Value":
            return

        # Convert to string if needed
        if not isinstance(value, str):
            value = str(value)

        min_length = field.constraints.get("min_length")
        try:
            min_length_val = int(min_length) if min_length is not None else None
            if min_length_val is not None and len(value) < min_length_val:
                logger.warning(
                    f"[{self.config.name}] String length error in {field.name}[{row_idx}]: "
                    f"Length {len(value)} is less than minimum {min_length} (value: {value})"
                )
                errors.append(
                    CellError(
                        row_idx=row_idx,
                        column=field.name,
                        value=value,
                        error_type=ErrorType.FORMAT,
                        message=f"String length {len(value)} is less than minimum {min_length_val}",
                    )
                )
        except (ValueError, TypeError):
            logger.warning(
                f"[{self.config.name}] Invalid min_length constraint for {field.name}: {min_length}"
            )

        max_length = field.constraints.get("max_length")
        try:
            max_length_val = int(max_length) if max_length is not None else None
            if max_length_val is not None and len(value) > max_length_val:
                logger.warning(
                    f"[{self.config.name}] String length error in {field.name}[{row_idx}]: "
                    f"Length {len(value)} is greater than maximum {max_length} (value: {value})"
                )
                errors.append(
                    CellError(
                        row_idx=row_idx,
                        column=field.name,
                        value=value,
                        error_type=ErrorType.FORMAT,
                        message=f"String length {len(value)} is greater than maximum {max_length_val}",
                    )
                )
        except (ValueError, TypeError):
            logger.warning(
                f"[{self.config.name}] Invalid max_length constraint for {field.name}: {max_length}"
            )

        pattern = field.constraints.get("pattern")
        if pattern is not None:
            try:
                import re

                if not re.match(pattern, value):
                    logger.warning(
                        f"[{self.config.name}] Pattern match error in {field.name}[{row_idx}]: "
                        f"Value '{value}' does not match pattern: {pattern}"
                    )
                    errors.append(
                        CellError(
                            row_idx=row_idx,
                            column=field.name,
                            value=value,
                            error_type=ErrorType.FORMAT,
                            message=f"String does not match pattern: {pattern}",
                        )
                    )
            except re.error:
                logger.warning(
                    f"[{self.config.name}] Invalid pattern constraint for {field.name}: {pattern}"
                )

    def _validate_numeric_constraints(
        self, field: SchemaField, value: Any, row_idx: int, errors: List[CellError]
    ) -> None:
        """Validate numeric constraints."""
        # Skip validation for None/"No Value"
        if value is None or value == "No Value":
            return

        # Convert string to numeric if needed
        if isinstance(value, str):
            if field.type == "integer":
                success, converted_value, _ = try_convert_to_int(value)
                if not success or converted_value is None:
                    return
                value = converted_value
            else:  # float
                success, converted_value, _ = try_convert_to_float(value)
                if not success or converted_value is None:
                    return
                value = converted_value

        # Now value should be numeric
        if not isinstance(value, (int, float)):
            return

        min_val = field.constraints.get("min")
        if min_val is not None:
            try:
                min_val = float(min_val)
                if value < min_val:
                    logger.warning(
                        f"[{self.config.name}] Range error in {field.name}[{row_idx}]: "
                        f"Value {value} is less than minimum {min_val}"
                    )
                    errors.append(
                        CellError(
                            row_idx=row_idx,
                            column=field.name,
                            value=value,
                            error_type=ErrorType.FORMAT,
                            message=f"Value {value} is less than minimum {min_val}",
                        )
                    )
            except (ValueError, TypeError):
                logger.warning(
                    f"[{self.config.name}] Invalid min constraint for {field.name}: {min_val}"
                )

        max_val = field.constraints.get("max")
        if max_val is not None:
            try:
                max_val = float(max_val)
                if value > max_val:
                    logger.warning(
                        f"[{self.config.name}] Range error in {field.name}[{row_idx}]: "
                        f"Value {value} is greater than maximum {max_val}"
                    )
                    errors.append(
                        CellError(
                            row_idx=row_idx,
                            column=field.name,
                            value=value,
                            error_type=ErrorType.FORMAT,
                            message=f"Value {value} is greater than maximum {max_val}",
                        )
                    )
            except (ValueError, TypeError):
                logger.warning(
                    f"[{self.config.name}] Invalid max constraint for {field.name}: {max_val}"
                )
