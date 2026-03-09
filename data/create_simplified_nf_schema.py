#!/usr/bin/env python3
"""
Script to create a simplified schema from NF.json based on column names from a CSV file.

This script reads column names from a CSV file, loads a JSON schema, filters elements
based on the column names, and creates a simplified schema with sample values.
"""

import json
import logging
import random
from pathlib import Path
from typing import Any, List, Dict

import pandas as pd


def setup_logging() -> None:
    """Configure logging for the script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def read_evaluate_columns(csv_path: Path) -> List[str]:
    """
    Read column names from a CSV file that have "Evaluate" classification.

    Args:
        csv_path: Path to the CSV file

    Returns:
        List of column names with "Evaluate" classification
    """
    try:
        df = pd.read_csv(csv_path)
        # Filter for columns with "Evaluate" classification
        evaluate_columns = df[df["Classification"] == "Evaluate"]["Column"].tolist()
        logging.info(
            f"Found {len(evaluate_columns)} columns with 'Evaluate' classification"
        )
        return evaluate_columns
    except Exception as e:
        logging.error(f"Failed to read CSV file {csv_path}: {e}")
        raise


def load_json_schema(json_path: Path) -> Dict[str, Any]:
    """
    Load JSON schema from a file.

    Args:
        json_path: Path to the JSON file

    Returns:
        Loaded JSON schema as a dictionary
    """
    try:
        with open(json_path, "r") as jfile:
            return json.load(jfile)
    except Exception as e:
        logging.error(f"Failed to load JSON schema from {json_path}: {e}")
        raise


def create_simplified_schema(
    nf_json: Dict[str, Any], column_names: List[str], max_sample_values: int = 5
) -> List[Dict[str, Any]]:
    """
    Create a simplified schema by filtering elements based on column names.

    Args:
        nf_json: The loaded JSON schema
        column_names: List of column names to filter by
        max_sample_values: Maximum number of sample values to include

    Returns:
        Simplified schema as a list of dictionaries
    """
    # Create custom Filename field to be added as the first field
    filename_field = {
        "name": "name",
        "description": "The primary key of this schema, representing the raw data for a single specimen.",
        "sample_values": ["MS02-2.txt", "AS-167591-LR-25156_R1.fastq.gz"],
    }

    # Create lists to store fields by priority
    id_fields = []
    other_fields = []

    # Process the fields from the JSON schema
    for element in nf_json.get("@graph", []):
        field_name = element.get("sms:displayName", "")
        description = element.get("rdfs:comment", "")

        # Skip elements not in column names
        if field_name not in column_names or field_name == "Filename":
            # Skip the Filename field since we've already added our custom version
            continue

        field = {
            "name": field_name,
            "description": description,
        }

        # Add sample values if available
        if "schema:rangeIncludes" in element:
            approved_values = [
                val["@id"].split(":")[-1]
                for val in element["schema:rangeIncludes"]
                if "@id" in val
            ]

            if approved_values:
                if len(approved_values) <= max_sample_values:
                    field["sample_values"] = approved_values
                else:
                    field["sample_values"] = random.sample(
                        approved_values, max_sample_values
                    )

        # Sort fields into ID fields and other fields
        if "ID" in field_name or field_name.endswith("Id"):
            id_fields.append(field)
        else:
            other_fields.append(field)

    # Combine fields in priority order: Filename, ID fields, other fields
    schema = [filename_field] + id_fields + other_fields

    logging.info(f"Prioritized {len(id_fields)} ID fields after Filename")

    return schema


def write_simplified_schema(schema: List[Dict[str, Any]], output_path: Path) -> None:
    """
    Write the simplified schema to a JSON file.

    Args:
        schema: The simplified schema to write
        output_path: Path to write the schema to
    """
    try:
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Wrap the schema in a "fields" object to match the expected output format
        schema_wrapper = {"fields": schema}

        with open(output_path, "w") as jfile:
            json.dump(schema_wrapper, jfile, indent=2)

        logging.info(f"Successfully wrote simplified schema to {output_path}")
    except Exception as e:
        logging.error(f"Failed to write simplified schema to {output_path}: {e}")
        raise


def main() -> None:
    """Main function to run the script."""
    setup_logging()

    # Define file paths
    evaluate_columns_csv_path = Path("./NF_schema_column_list_7_11_25.csv")
    original_schema_json_path = Path("./NF.jsonld")
    output_path = Path("./extract_metadata/nf/schema.json")

    logging.info(
        f"Reading columns with 'Evaluate' classification from {evaluate_columns_csv_path}"
    )
    evaluate_columns = read_evaluate_columns(evaluate_columns_csv_path)

    logging.info(f"Loading JSON schema from {original_schema_json_path}")
    nf_json = load_json_schema(original_schema_json_path)

    logging.info("Creating simplified schema with filtered 'Evaluate' columns")
    schema = create_simplified_schema(nf_json, evaluate_columns)

    logging.info(f"Writing simplified schema to {output_path}")
    write_simplified_schema(schema, output_path)

    logging.info(f"Processed {len(schema)} schema elements")


if __name__ == "__main__":
    main()
