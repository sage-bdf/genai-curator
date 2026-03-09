# This deliverable is considered developed content as defined in contract between BDF parties.


import os
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


class CSVComparator:
    """
    A class to compare CSV files from two different folders, standardizing column names
    and matching rows based on specified key columns.
    """

    def __init__(
        self,
        generated_folder: str,
        original_folder: str,
        generated_key_column: str = "name",
        original_key_column: str = "name",
    ):
        """
        Initialize the CSVComparator with paths to the generated and original folders.

        Args:
            generated_folder: Path to the folder containing generated CSV files
            original_folder: Path to the folder containing original CSV files
            generated_key_column: Column name in generated files to use for matching rows
            original_key_column: Column name in original files to use for matching rows
        """
        self.generated_folder = generated_folder
        self.original_folder = original_folder
        self.generated_key_column = generated_key_column
        self.original_key_column = original_key_column

        # Will store the loaded dataframes
        self.generated_dfs: Dict[str, pd.DataFrame] = {}
        self.original_dfs: Dict[str, pd.DataFrame] = {}

        # Will store the mapping between file IDs
        self.file_mapping: Dict[str, str] = {}

    def _extract_id_from_filename(self, filename: str) -> str:
        """
        Extract the ID from a filename.

        Args:
            filename: The filename to extract ID from

        Returns:
            The extracted ID
        """
        # For generated files like "extracted_metadata_nf_2.csv"
        if filename.startswith("extracted_metadata_"):
            match = re.search(r"extracted_metadata_nf_(\d+)\.csv", filename)
            if match:
                return match.group(1)

        # For original files like "nf_2.csv"
        match = re.search(r"nf_(\d+)\.csv", filename)
        if match:
            return match.group(1)

        return None

    def _standardize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize column names to lowercase.

        Args:
            df: DataFrame to standardize

        Returns:
            DataFrame with standardized column names
        """
        df.columns = [col.lower() for col in df.columns]
        return df

    def load_files(self) -> None:
        """
        Load all CSV files from both folders and create a mapping between them.
        """
        # Load generated files
        for filename in os.listdir(self.generated_folder):
            if filename.endswith(".csv"):
                file_id = self._extract_id_from_filename(filename)
                if file_id:
                    file_path = os.path.join(self.generated_folder, filename)
                    df = pd.read_csv(file_path)
                    self.generated_dfs[file_id] = self._standardize_column_names(df)

        # Load original files
        for filename in os.listdir(self.original_folder):
            if filename.endswith(".csv"):
                file_id = self._extract_id_from_filename(filename)
                if file_id:
                    file_path = os.path.join(self.original_folder, filename)
                    df = pd.read_csv(file_path)
                    self.original_dfs[file_id] = self._standardize_column_names(df)

                    # Create mapping if this file has a corresponding generated file
                    if file_id in self.generated_dfs:
                        self.file_mapping[file_id] = file_id

    def get_available_ids(self) -> List[str]:
        """
        Get a list of IDs that have both generated and original files.

        Returns:
            List of available IDs
        """
        return list(self.file_mapping.keys())

    def get_columns_for_id(self, file_id: str) -> Tuple[List[str], List[str]]:
        """
        Get the column names for both generated and original files for a given ID.

        Args:
            file_id: The ID to get columns for

        Returns:
            Tuple of (generated_columns, original_columns)
        """
        if file_id not in self.file_mapping:
            return [], []

        generated_columns = list(self.generated_dfs[file_id].columns)
        original_columns = list(self.original_dfs[self.file_mapping[file_id]].columns)

        return generated_columns, original_columns

    def get_common_columns(self, file_id: str) -> List[str]:
        """
        Get column names that are common between generated and original files for a given ID.

        Args:
            file_id: The ID to get common columns for

        Returns:
            List of common column names
        """
        if file_id not in self.file_mapping:
            return []

        generated_columns = set(self.generated_dfs[file_id].columns)
        original_columns = set(self.original_dfs[self.file_mapping[file_id]].columns)

        return list(generated_columns.intersection(original_columns))

    def compare_values(
        self,
        file_id: str,
        column: str,
        generated_key_value: Optional[str] = None,
        original_key_value: Optional[str] = None,
    ) -> Tuple[List[Any], List[Any]]:
        """
        Compare values from a specific column between generated and original files.

        Args:
            file_id: The ID of the files to compare
            column: The column name to compare (must be in standardized form)
            generated_key_value: Optional value to filter the generated file by key column
            original_key_value: Optional value to filter the original file by key column

        Returns:
            Tuple of (generated_values, original_values)
        """
        if file_id not in self.file_mapping:
            return [], []

        # Get the dataframes
        generated_df = self.generated_dfs[file_id]
        original_df = self.original_dfs[self.file_mapping[file_id]]

        # Check if column exists in both dataframes
        if column not in generated_df.columns or column not in original_df.columns:
            return [], []

        # Filter by key value if provided
        if generated_key_value:
            generated_df = generated_df[
                generated_df[self.generated_key_column.lower()] == generated_key_value
            ]

        if original_key_value:
            original_df = original_df[
                original_df[self.original_key_column.lower()] == original_key_value
            ]

        # Get the values
        generated_values = generated_df[column].tolist()
        original_values = original_df[column].tolist()

        return generated_values, original_values

    def get_side_by_side_comparison(self, file_id: str, column: str) -> pd.DataFrame:
        """
        Get a side-by-side comparison of values from a specific column.

        Args:
            file_id: The ID of the files to compare
            column: The column name to compare (must be in standardized form)

        Returns:
            DataFrame with side-by-side comparison
        """
        if file_id not in self.file_mapping:
            return pd.DataFrame()

        # Get the dataframes
        generated_df = self.generated_dfs[file_id]
        original_df = self.original_dfs[self.file_mapping[file_id]]

        # Check if column exists in both dataframes
        if column not in generated_df.columns or column not in original_df.columns:
            return pd.DataFrame()

        # Create a merged dataframe based on key columns
        generated_key = self.generated_key_column.lower()
        original_key = self.original_key_column.lower()

        # Select only the key column and the column of interest
        generated_subset = generated_df[[generated_key, column]].copy()
        original_subset = original_df[[original_key, column]].copy()

        # Rename columns to avoid conflicts
        generated_subset.columns = [generated_key, f"generated_{column}"]
        original_subset.columns = [original_key, f"original_{column}"]

        # Merge the dataframes
        merged = pd.merge(
            generated_subset,
            original_subset,
            left_on=generated_key,
            right_on=original_key,
            how="inner",
        )

        return merged[[generated_key, f"generated_{column}", f"original_{column}"]]

    def get_all_side_by_side_comparisons(self, file_id: str) -> pd.DataFrame:
        """
        Get side-by-side comparisons for all common columns.

        Args:
            file_id: The ID of the files to compare

        Returns:
            DataFrame with side-by-side comparisons for all common columns
        """
        if file_id not in self.file_mapping:
            return pd.DataFrame()

        common_columns = self.get_common_columns(file_id)
        if not common_columns:
            return pd.DataFrame()

        # Get the dataframes
        generated_df = self.generated_dfs[file_id]
        original_df = self.original_dfs[self.file_mapping[file_id]]

        # Create a merged dataframe based on key columns
        generated_key = self.generated_key_column.lower()
        original_key = self.original_key_column.lower()

        # Select the key column and all common columns
        generated_subset = generated_df[[generated_key] + common_columns].copy()
        original_subset = original_df[[original_key] + common_columns].copy()

        # Rename columns to avoid conflicts
        generated_columns = [generated_key] + [
            f"generated_{col}" for col in common_columns
        ]
        original_columns = [original_key] + [
            f"original_{col}" for col in common_columns
        ]

        generated_subset.columns = generated_columns
        original_subset.columns = original_columns

        # Merge the dataframes
        merged = pd.merge(
            generated_subset,
            original_subset,
            left_on=generated_key,
            right_on=original_key,
            how="inner",
        )

        return merged
