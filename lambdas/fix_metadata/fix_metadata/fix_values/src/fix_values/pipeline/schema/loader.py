# This deliverable is considered developed content as defined in contract between BDF parties.


"""Schema loading and validation utilities."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import yaml  # type: ignore
from loguru import logger
from pydantic import ValidationError

from fix_values.ontology.reader import OntologyReader
from fix_values.pipeline.core.models import Schema, SchemaField


def _find_display_name(graph: List[dict], id_str: str) -> Optional[str]:
    """Find the sms:displayName for a given @id in the graph."""
    for item in graph:
        if item.get("@id") == id_str:
            return item.get("sms:displayName")
    return None


def _process_graph_item(item: dict, graph: List[dict]) -> Optional[SchemaField]:
    """Process a graph item to extract field information."""
    if "@type" not in item or "@id" not in item or "sms:displayName" not in item:
        return None

    field_name = item["sms:displayName"]
    logger.debug(f"Processing field {field_name}")

    # Extract valid values from schema:rangeIncludes
    valid_values = None
    if "schema:rangeIncludes" in item:
        range_includes = item["schema:rangeIncludes"]
        if not isinstance(range_includes, list):
            range_includes = [range_includes]

        valid_values = []
        for option in range_includes:
            if isinstance(option, dict) and "@id" in option:
                display_name = _find_display_name(graph, option["@id"])
                if display_name:
                    valid_values.append(display_name)

    # Get description if available
    description = item.get("rdfs:comment", None)
    required = bool(item.get("sms:required", "sms:false") == "sms:true")

    # Default to string type, could be enhanced to infer from rangeIncludes
    field_type = "string"

    try:
        return SchemaField(
            name=field_name,
            type=field_type,
            required=required,  # Default to not required
            description=description,
            valid_values=valid_values,
        )
    except Exception as e:
        logger.error(f"Failed to create SchemaField for {field_name}: {e}")
        return None


def load_schema(
    path: Union[str, Path], ontology_path: Optional[Union[str, Path]] = None
) -> Schema:
    """Load schema from JSON/YAML file and enrich with ontology data.

    Args:
        path: Path to schema file
        ontology_path: Optional path to ontology file

    Returns:
        Loaded and enriched schema

    Raises:
        FileNotFoundError: If schema file doesn't exist
        ValueError: If schema format is invalid
        ValidationError: If schema validation fails
    """
    logger.info(f"Loading schema from: {path}")
    path = Path(path)
    if not path.exists():
        logger.error(f"Schema file not found: {path}")
        raise FileNotFoundError(f"Schema file not found: {path}")

    try:
        # Load raw schema
        logger.info(f"Reading schema file with format: {path.suffix}")
        if path.suffix in {".json", ".jsonld", ".jsonid"}:
            with open(path) as f:
                raw_schema = json.load(f)
                logger.debug("Successfully parsed JSON schema")
        elif path.suffix in {".yaml", ".yml"}:
            with open(path) as f:
                raw_schema = yaml.safe_load(f)
                logger.debug("Successfully parsed YAML schema")
        else:
            logger.error(f"Unsupported schema format: {path.suffix}")
            raise ValueError(f"Unsupported schema format: {path.suffix}")

        # Convert to internal schema format
        fields: List[SchemaField] = []
        field_sources: Dict[str, Tuple[int, str]] = (
            {}
        )  # Track where each field comes from {field_name: (index, id)}
        logger.info("Converting schema to internal format...")

        # Handle JSON-LD format with @graph
        if "@graph" in raw_schema:
            logger.info("Processing JSON-LD @graph structure")
            graph = raw_schema["@graph"]
            for item in graph:
                field = _process_graph_item(item, graph)
                if field:
                    if field.name in field_sources:
                        logger.warning(f"Duplicate field {field.name} found!")
                        logger.warning(f"Original @id: {field_sources[field.name]}")
                        logger.warning(f"Duplicate @id: {item.get('@id', 'unknown')}")
                        logger.warning(
                            f"Original valid_values: {fields[field_sources[field.name][0]].valid_values}"
                        )
                        logger.warning(f"Duplicate valid_values: {field.valid_values}")
                    else:
                        field_sources[field.name] = (
                            len(fields),
                            item.get("@id", "unknown"),
                        )
                        fields.append(field)
                        logger.debug(f"Created SchemaField for {field.name}")
        # Handle traditional schema format
        elif "fields" in raw_schema:
            logger.info("Processing traditional schema format")
            for field_data in raw_schema["fields"]:
                try:
                    field = SchemaField(
                        name=field_data["name"],
                        type=field_data["type"],
                        required=field_data.get("required", False),
                        description=field_data.get("description"),
                        constraints=field_data.get("constraints", {}),
                        valid_values=field_data.get("valid_values"),
                        examples=field_data.get("examples"),
                    )
                    logger.debug(f"Created SchemaField for {field_data['name']}")
                    fields.append(field)
                except Exception as e:
                    logger.error(
                        f"Failed to create SchemaField for {field_data['name']}: {e}"
                    )
                    raise
        else:
            logger.error("Schema must contain either @graph or fields")
            raise ValueError("Schema must contain either @graph or fields")

        # Load ontology if provided
        if ontology_path:
            logger.info(f"Loading ontology from: {ontology_path}")
            try:
                ontology = OntologyReader(str(ontology_path))
                ontology.read_ontology()
                logger.info("Successfully loaded ontology")

                # Enrich fields with ontology data
                for field in fields:
                    if not field.valid_values:
                        ontology_values = ontology.get_field_options(field.name)
                        if ontology_values:
                            field.valid_values = ontology_values
                            logger.debug(
                                f"Added {len(ontology_values)} valid values from ontology for {field.name}"
                            )
            except Exception as e:
                logger.error(f"Failed to load ontology: {e}")
                raise

        # Create final schema
        logger.info(f"Creating schema with {len(fields)} fields")
        schema = Schema(
            fields=fields,
            version=raw_schema.get("version", "1.0.0"),
            description=raw_schema.get("description"),
            metadata=raw_schema.get("metadata", {}),
        )
        logger.info("Schema creation successful")
        return schema

    except (json.JSONDecodeError, yaml.YAMLError) as e:
        logger.error(f"Failed to parse schema file: {e}")
        raise ValueError(f"Failed to parse schema file: {e}")
    except ValidationError as e:
        logger.error(f"Invalid schema format: {e}")
        raise ValidationError(f"Invalid schema format: {e}")
    except KeyError as e:
        logger.error(f"Missing required field in schema: {e}")
        raise ValueError(f"Missing required field in schema: {e}")
    except Exception as e:
        logger.error(f"Unexpected error loading schema: {e}")
        raise


def validate_schema(schema: Schema) -> None:
    """Validate schema constraints and relationships.

    Args:
        schema: Schema to validate

    Raises:
        ValueError: If schema validation fails
    """
    logger.info("Starting schema validation")

    # Check for duplicate field names
    field_names = [field.name for field in schema.fields]
    if len(field_names) != len(set(field_names)):
        logger.error("Found duplicate field names in schema")
        raise ValueError("Duplicate field names in schema")
    logger.debug("No duplicate field names found")

    # Validate each field
    logger.info(f"Validating {len(schema.fields)} fields")
    for field in schema.fields:
        logger.debug(f"Validating field: {field.name}")

        # Check valid_values if provided
        if field.valid_values is not None:
            logger.debug(f"Checking valid_values for {field.name}")
            if not isinstance(field.valid_values, list):
                logger.error(f"Field {field.name}: valid_values must be a list")
                raise ValueError(f"Field {field.name}: valid_values must be a list")
            if not field.valid_values:
                logger.error(f"Field {field.name}: valid_values cannot be empty")
                raise ValueError(f"Field {field.name}: valid_values cannot be empty")
            logger.debug(
                f"Field {field.name} has {len(field.valid_values)} valid values"
            )

        # Check constraints
        if field.constraints:
            logger.debug(f"Validating constraints for {field.name} ({field.type})")
            try:
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
                    logger.error(f"Unknown field type: {field.type}")
                    raise ValueError(f"Unknown field type: {field.type}")
                logger.debug(f"Successfully validated constraints for {field.name}")
            except ValueError as e:
                logger.error(f"Constraint validation failed for {field.name}: {e}")
                raise


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
