# This deliverable is considered developed content as defined in contract between BDF parties.


"""Schema loading and validation utilities."""

import json
from pathlib import Path
from typing import Union

import yaml
from pydantic import ValidationError

from fix_values.pipeline.models import Schema, SchemaField


def load_schema(path: Union[str, Path]) -> Schema:
    """Load schema from JSON or YAML file.

    Args:
        path: Path to schema file

    Returns:
        Loaded schema

    Raises:
        FileNotFoundError: If schema file doesn't exist
        ValueError: If schema format is invalid
        ValidationError: If schema validation fails
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Schema file not found: {path}")

    try:
        # Load raw schema
        if path.suffix == ".json":
            with open(path) as f:
                raw_schema = json.load(f)
        elif path.suffix in {".yaml", ".yml"}:
            with open(path) as f:
                raw_schema = yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported schema format: {path.suffix}")

        # Convert to internal schema format
        fields = []
        for field_data in raw_schema.get("fields", []):
            field = SchemaField(
                name=field_data["name"],
                type=field_data["type"],
                required=field_data.get("required", False),
                description=field_data.get("description"),
                constraints=field_data.get("constraints", {}),
                valid_values=field_data.get("valid_values"),
                examples=field_data.get("examples"),
            )
            fields.append(field)

        return Schema(
            fields=fields,
            version=raw_schema.get("version", "1.0.0"),
            description=raw_schema.get("description"),
            metadata=raw_schema.get("metadata", {}),
        )

    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise ValueError(f"Failed to parse schema file: {e}")
    except ValidationError as e:
        raise ValidationError(f"Invalid schema format: {e}")
    except KeyError as e:
        raise ValueError(f"Missing required field in schema: {e}")


def validate_schema(schema: Schema) -> None:
    """Validate schema constraints and relationships.

    Args:
        schema: Schema to validate

    Raises:
        ValueError: If schema validation fails
    """
    # Check for duplicate field names
    field_names = [field.name for field in schema.fields]
    if len(field_names) != len(set(field_names)):
        raise ValueError("Duplicate field names in schema")

    # Validate each field
    for field in schema.fields:
        # Check valid_values if provided
        if field.valid_values is not None:
            if not isinstance(field.valid_values, list):
                raise ValueError(f"Field {field.name}: valid_values must be a list")
            if not field.valid_values:
                raise ValueError(f"Field {field.name}: valid_values cannot be empty")

        # Check constraints
        if field.constraints:
            if field.type == "string":
                _validate_string_constraints(field)
            elif field.type == "integer":
                _validate_integer_constraints(field)
            elif field.type == "float":
                _validate_float_constraints(field)
            elif field.type == "boolean":
                _validate_boolean_constraints(field)
            elif field.type == "date":
                _validate_date_constraints(field)
            else:
                raise ValueError(f"Unknown field type: {field.type}")


def _validate_string_constraints(field: SchemaField) -> None:
    """Validate string field constraints."""
    for key in field.constraints:
        if key not in {"min_length", "max_length", "pattern"}:
            raise ValueError(f"Field {field.name}: Invalid string constraint: {key}")

    min_length = field.constraints.get("min_length")
    max_length = field.constraints.get("max_length")

    if min_length is not None:
        if not isinstance(min_length, int) or min_length < 0:
            raise ValueError(
                f"Field {field.name}: min_length must be a non-negative integer"
            )

    if max_length is not None:
        if not isinstance(max_length, int) or max_length < 0:
            raise ValueError(
                f"Field {field.name}: max_length must be a non-negative integer"
            )

    if min_length is not None and max_length is not None:
        if min_length > max_length:
            raise ValueError(
                f"Field {field.name}: min_length cannot be greater than max_length"
            )


def _validate_integer_constraints(field: SchemaField) -> None:
    """Validate integer field constraints."""
    for key in field.constraints:
        if key not in {"min", "max"}:
            raise ValueError(f"Field {field.name}: Invalid integer constraint: {key}")

    min_val = field.constraints.get("min")
    max_val = field.constraints.get("max")

    if min_val is not None:
        if not isinstance(min_val, int):
            raise ValueError(f"Field {field.name}: min must be an integer")

    if max_val is not None:
        if not isinstance(max_val, int):
            raise ValueError(f"Field {field.name}: max must be an integer")

    if min_val is not None and max_val is not None:
        if min_val > max_val:
            raise ValueError(f"Field {field.name}: min cannot be greater than max")


def _validate_float_constraints(field: SchemaField) -> None:
    """Validate float field constraints."""
    for key in field.constraints:
        if key not in {"min", "max"}:
            raise ValueError(f"Field {field.name}: Invalid float constraint: {key}")

    min_val = field.constraints.get("min")
    max_val = field.constraints.get("max")

    if min_val is not None:
        if not isinstance(min_val, (int, float)):
            raise ValueError(f"Field {field.name}: min must be a number")

    if max_val is not None:
        if not isinstance(max_val, (int, float)):
            raise ValueError(f"Field {field.name}: max must be a number")

    if min_val is not None and max_val is not None:
        if min_val > max_val:
            raise ValueError(f"Field {field.name}: min cannot be greater than max")


def _validate_boolean_constraints(field: SchemaField) -> None:
    """Validate boolean field constraints."""
    if field.constraints:
        raise ValueError(f"Field {field.name}: Boolean fields cannot have constraints")


def _validate_date_constraints(field: SchemaField) -> None:
    """Validate date field constraints."""
    for key in field.constraints:
        if key not in {"min", "max", "format"}:
            raise ValueError(f"Field {field.name}: Invalid date constraint: {key}")

    date_format = field.constraints.get("format")
    if date_format is not None and not isinstance(date_format, str):
        raise ValueError(f"Field {field.name}: date format must be a string")
