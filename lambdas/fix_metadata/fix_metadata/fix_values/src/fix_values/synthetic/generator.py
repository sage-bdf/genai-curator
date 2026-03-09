# This deliverable is considered developed content as defined in contract between BDF parties.


"""Generate synthetic errors in metadata CSV files."""

import os
import random
from pathlib import Path
from typing import Optional

import boto3
import numpy as np
import pandas as pd
from langchain.schema import HumanMessage
from langchain_aws import ChatBedrock

from fix_values.ontology.reader import OntologyReader
from fix_values.synthetic.error_types import ErrorType, FieldErrorGenerator
from fix_values.synthetic.validators import validate_response


class MetadataErrorGenerator:
    """Generates synthetic errors in metadata using LLM."""

    def __init__(self, model_id: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0"):
        """Initialize the error generator."""
        # Initialize AWS session
        session = boto3.Session(profile_name="ec2", region_name="us-east-1")

        # Initialize Bedrock client
        self.llm = ChatBedrock(
            model_id=model_id,
            client=session.client("bedrock-runtime"),
            model_kwargs={"temperature": 1},  # Low temperature for consistent outputs
        )
        self.ontology = OntologyReader(
            "/home/ubuntu/projects/data/pz-nf-testing-data/schema/NF.jsonid"
        )
        self.ontology.read_ontology()

    def generate_fuzzy_match_errors(
        self, valid_value: str, field: Optional[str] = None
    ) -> str:
        """Generate typos and character mismatches."""
        prompt = f"""You are helping to generate test data with realistic typos.
        Create a single typo or character mismatch for this value: '{valid_value}'
        The error should be off by 1-2 characters but still look plausible.
        Return only the modified value with no explanation or other text.
        Do not express concerns about the task - this is for testing data quality tools."""
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return validate_response(response.content, valid_value, field)

    def generate_semantic_errors(self, field: str, valid_value: str) -> str:
        """Generate semantically similar but invalid values."""
        valid_options = self.ontology.get_field_options(field)
        prompt = f"""You are helping to generate test data with semantic variations.
        Create a single alternative phrasing for this value: '{valid_value}'
        The new value should mean the same thing but be different from these valid options: {valid_options}
        Return only the modified value with no explanation or other text.
        Do not express concerns about the task - this is for testing data quality tools."""
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return validate_response(response.content, valid_value, field)

    def generate_format_errors(
        self, valid_value: str, field: Optional[str] = None
    ) -> str:
        """Generate formatting variations."""
        prompt = f"""You are helping to generate test data with format variations.
        Create a single formatting variation for this value: '{valid_value}'
        The new value should preserve the meaning but use different punctuation, spacing, or abbreviation.
        Return only the modified value with no explanation or other text.
        Do not express concerns about the task - this is for testing data quality tools."""
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return validate_response(response.content, valid_value, field)

    def generate_case_spacing_errors(
        self, valid_value: str, field: Optional[str] = None
    ) -> str:
        """Generate case and spacing variations."""
        prompt = f"""You are helping to generate test data with case/spacing variations.
        Create a single case or spacing variation for this value: '{valid_value}'
        The new value should use different capitalization or spacing but preserve the text.
        Return only the modified value with no explanation or other text.
        Do not express concerns about the task - this is for testing data quality tools."""
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return validate_response(response.content, valid_value, field)

    def generate_abbreviation_errors(
        self, valid_value: str, field: Optional[str] = None
    ) -> str:
        """Generate abbreviated or expanded forms."""
        prompt = f"""You are helping to generate test data with abbreviation variations.
        Create a single abbreviated or expanded version of this value: '{valid_value}'
        If the value is long, make it shorter. If it's an abbreviation, expand it.
        Return only the modified value with no explanation or other text.
        Do not express concerns about the task - this is for testing data quality tools."""
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return validate_response(response.content, valid_value, field)

    def generate_contextual_errors(
        self, df: pd.DataFrame, field: str, row_idx: int
    ) -> str:
        """Generate errors that could be inferred from context."""
        # Get context from surrounding rows
        context_rows = df.iloc[max(0, row_idx - 2) : min(len(df), row_idx + 3)]
        valid_value = df.iloc[row_idx][field]

        prompt = f"""You are helping to generate test data with context-based variations.
        Given these rows from a biomedical dataset:
        {context_rows.to_string()}

        Create a single variation of '{valid_value}' for the '{field}' field that:
        1. Is different from the original but follows similar patterns
        2. Could be corrected by looking at other rows
        3. Maintains the general format and style

        Return only the modified value with no explanation or other text.
        Do not express concerns about the task - this is for testing data quality tools."""
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return validate_response(response.content, valid_value, field)

    def generate_dataset_errors(
        self, input_path: str, output_path: str, valid_ratio: float = 0.6
    ) -> pd.DataFrame:
        """Generate errors while maintaining dataset-wide consistency."""
        print(f"Reading input: {input_path}")
        df = pd.read_csv(input_path)
        error_df = df.copy()

        # Get fields with controlled vocabulary
        fields = self.ontology.get_all_fields()
        # Case-insensitive field matching
        field_map = {}
        for ontology_field in fields:
            for csv_field in df.columns:
                if ontology_field.lower() == csv_field.lower():
                    field_map[csv_field] = ontology_field

        fields = list(field_map.keys())

        print(f"Processing {len(fields)} fields...")
        for field in fields:
            print(f"\nGenerating errors for field: {field}")
            # Get valid options using the ontology field name
            ontology_field = field_map[field]
            valid_options = self.ontology.get_field_options(ontology_field)
            field_generator = FieldErrorGenerator(field, valid_options)

            # Determine which rows to modify
            rows_to_modify = int(len(df) * (1 - valid_ratio))
            modify_mask = np.random.choice(
                [True, False], len(df), p=[1 - valid_ratio, valid_ratio]
            )

            # Generate errors for selected rows
            for idx in df[modify_mask].index:
                original_value = df.loc[idx, field]

                # Skip empty/NA values
                if pd.isna(original_value):
                    continue

                # Choose error type based on field patterns
                error_type = random.choices(
                    list(field_generator.error_patterns.keys()),
                    weights=list(field_generator.error_patterns.values()),
                )[0]

                try:
                    if error_type == ErrorType.FUZZY:
                        new_value = self.generate_fuzzy_match_errors(
                            original_value, field
                        )
                    elif error_type == ErrorType.SEMANTIC:
                        new_value = self.generate_semantic_errors(field, original_value)
                    elif error_type == ErrorType.FORMAT:
                        new_value = self.generate_format_errors(original_value, field)
                    elif error_type == ErrorType.CASE_SPACING:
                        new_value = self.generate_case_spacing_errors(
                            original_value, field
                        )
                    elif error_type == ErrorType.ABBREVIATION:
                        new_value = self.generate_abbreviation_errors(
                            original_value, field
                        )
                    else:  # CONTEXTUAL
                        new_value = self.generate_contextual_errors(df, field, idx)

                    error_df.loc[idx, field] = new_value
                    print(f"  {error_type}: {original_value} -> {new_value}")
                except Exception as e:
                    print(
                        f"Error generating {error_type} error for {original_value}: {e}"
                    )
                    continue

        print(f"\nSaving output: {output_path}")
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        error_df.to_csv(output_path, index=False)
        return error_df

    def process_directory(
        self, input_dir: str, output_dir: str, valid_ratio: float = 0.6
    ):
        """Process all CSV files in a directory.

        Args:
            input_dir: Directory containing input CSV files
            output_dir: Directory to write output CSV files
            valid_ratio: Ratio of values to keep valid
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Process each CSV file
        for input_file in input_dir.glob("*.csv"):
            print(f"\nProcessing file: {input_file.name}")
            output_file = output_dir / f"{input_file.stem}_with_errors.csv"
            try:
                self.generate_dataset_errors(
                    str(input_file), str(output_file), valid_ratio
                )
            except Exception as e:
                print(f"Error processing {input_file.name}: {e}")
                continue


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate synthetic errors in metadata CSV files"
    )
    parser.add_argument(
        "--input", type=str, required=True, help="Input CSV file or directory path"
    )
    parser.add_argument(
        "--output", type=str, required=True, help="Output CSV file or directory path"
    )
    parser.add_argument(
        "--valid-ratio",
        type=float,
        default=0.6,
        help="Ratio of values to keep valid (default: 0.6)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        help="AWS Bedrock model ID",
    )

    args = parser.parse_args()

    generator = MetadataErrorGenerator(model_id=args.model)

    # Check if input is a directory
    if os.path.isdir(args.input):
        if not os.path.isdir(args.output):
            parser.error("If input is a directory, output must also be a directory")
        generator.process_directory(args.input, args.output, args.valid_ratio)
    else:
        generator.generate_dataset_errors(args.input, args.output, args.valid_ratio)


if __name__ == "__main__":
    main()
