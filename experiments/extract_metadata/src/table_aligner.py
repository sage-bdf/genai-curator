# This deliverable is considered developed content as defined in contract between BDF parties.


"""
Table Aligner Script

This script aligns and joins tables from inferred outputs and ground truth data.
It creates a joined table where columns are ordered alternating between "X_gt" and "X_pred",
with columns present in the ground truth table prioritized first.
"""

import argparse
import os
from pathlib import Path
from typing import List

import pandas as pd


class TableAligner:
    def __init__(
        self,
        pred_dir: str,
        gt_dir: str,
        output_dir: str,
        pred_prefix: str = "extracted_metadata_nf_",
        gt_prefix: str = "filtered_nf_",
    ):
        """
        Initialize the TableAligner.

        Args:
            pred_dir: Directory containing predicted/inferred tables
            gt_dir: Directory containing ground truth tables
            output_dir: Directory to save aligned tables
            pred_prefix: Prefix of predicted table filenames
            gt_prefix: Prefix of ground truth table filenames
        """
        self.pred_dir = Path(pred_dir)
        self.gt_dir = Path(gt_dir)
        self.output_dir = Path(output_dir)
        self.pred_prefix = pred_prefix
        self.gt_prefix = gt_prefix

        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)

    def get_matching_file_ids(self) -> List[str]:
        """
        Get IDs of files that exist in both directories.

        Returns:
            List of file IDs (e.g., ["1", "2", "3"])
        """
        pred_files = {f.name for f in self.pred_dir.glob(f"{self.pred_prefix}*.csv")}
        gt_files = {f.name for f in self.gt_dir.glob(f"{self.gt_prefix}*.csv")}

        pred_ids = {
            f.replace(self.pred_prefix, "").replace(".csv", "") for f in pred_files
        }
        gt_ids = {f.replace(self.gt_prefix, "").replace(".csv", "") for f in gt_files}

        # Find common IDs
        common_ids = pred_ids.intersection(gt_ids)
        return sorted(common_ids, key=lambda x: int(x) if x.isdigit() else x)

    def normalize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize column names to lowercase for case-insensitive matching.

        Args:
            df: DataFrame with columns to normalize

        Returns:
            DataFrame with normalized column names
        """
        # Create a mapping of lowercase column names to original column names
        column_mapping = {col.lower(): col for col in df.columns}

        # Create a new DataFrame with lowercase column names
        df_normalized = df.copy()
        df_normalized.columns = [col.lower() for col in df.columns]

        return df_normalized, column_mapping

    def align_tables(self, file_id: str) -> pd.DataFrame:
        """
        Align tables from predicted and ground truth directories.
        Creates a joined table where columns are ordered alternating between "X_gt" and "X_pred",
        with columns present in the ground truth table prioritized first.
        Rows are matched based on the 'name' field which is used as the primary key.

        Args:
            file_id: ID of the file to align

        Returns:
            DataFrame with aligned columns
        """
        # Load the tables
        pred_file = self.pred_dir / f"{self.pred_prefix}{file_id}.csv"
        gt_file = self.gt_dir / f"{self.gt_prefix}{file_id}.csv"

        if not pred_file.exists() or not gt_file.exists():
            raise FileNotFoundError(f"Files for ID {file_id} not found")

        pred_df = pd.read_csv(pred_file)
        gt_df = pd.read_csv(gt_file)

        # Normalize column names
        pred_df_norm, pred_mapping = self.normalize_column_names(pred_df)
        gt_df_norm, gt_mapping = self.normalize_column_names(gt_df)

        # Verify that 'name' column exists in both dataframes
        if "name" not in pred_df_norm.columns or "name" not in gt_df_norm.columns:
            raise ValueError(
                f"'name' column not found in one or both tables for file ID {file_id}"
            )

        # Get sets of column names
        pred_cols = set(pred_df_norm.columns)
        gt_cols = set(gt_df_norm.columns)

        # Find common columns and unique columns
        common_cols = pred_cols.intersection(gt_cols)
        pred_only_cols = pred_cols - gt_cols
        gt_only_cols = gt_cols - pred_cols

        # Create dictionaries to hold column data
        result_data = {}

        # Preserve the original column order from the ground truth table
        gt_col_order = [col.lower() for col in gt_df.columns]

        # Create a dictionary to map from name to row data for both dataframes
        gt_name_to_row = {row["name"]: row for _, row in gt_df_norm.iterrows()}
        pred_name_to_row = {row["name"]: row for _, row in pred_df_norm.iterrows()}

        # Get all unique names from both dataframes
        all_names = sorted(set(gt_name_to_row.keys()) | set(pred_name_to_row.keys()))

        # Initialize result data with empty lists for each column
        for col in gt_col_order:
            gt_original_col = gt_mapping[col]
            result_data[f"{gt_original_col}_gt"] = []

            # Add predicted column if it exists in pred
            if col in pred_cols:
                pred_original_col = pred_mapping[col]
                result_data[f"{pred_original_col}_pred"] = []
            else:
                # Add empty column for prediction
                result_data[f"{gt_original_col}_pred"] = []

        # Add columns that exist only in predictions
        for col in sorted(list(pred_only_cols)):
            pred_original_col = pred_mapping[col]
            result_data[f"{pred_original_col}_pred"] = []
            result_data[f"{pred_original_col}_gt"] = []

        # Populate the result data by iterating through all unique names
        for name in all_names:
            gt_row = gt_name_to_row.get(name)
            pred_row = pred_name_to_row.get(name)

            # Add ground truth columns
            for col in gt_col_order:
                gt_original_col = gt_mapping[col]
                result_data[f"{gt_original_col}_gt"].append(
                    gt_row[col] if gt_row is not None else None
                )

                # Add predicted column if it exists in pred
                if col in pred_cols:
                    pred_original_col = pred_mapping[col]
                    result_data[f"{pred_original_col}_pred"].append(
                        pred_row[col] if pred_row is not None else None
                    )
                else:
                    # Add empty value for prediction
                    result_data[f"{gt_original_col}_pred"].append(None)

            # Add columns that exist only in predictions
            for col in sorted(list(pred_only_cols)):
                pred_original_col = pred_mapping[col]
                result_data[f"{pred_original_col}_pred"].append(
                    pred_row[col] if pred_row is not None else None
                )
                result_data[f"{pred_original_col}_gt"].append(None)

        # Create DataFrame all at once to avoid fragmentation
        result_df = pd.DataFrame(result_data)
        return result_df

    def reorder_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Reorder columns to alternate between gt and pred, prioritizing columns in ground truth.
        Preserves the original column order from the ground truth table.

        Args:
            df: DataFrame with columns to reorder

        Returns:
            DataFrame with reordered columns
        """
        # The align_tables method already creates the DataFrame with columns in the desired order
        # This method is kept for compatibility but now just returns the DataFrame as is
        return df

    def process_file(self, file_id: str) -> None:
        """
        Process a single file pair and save the result.

        Args:
            file_id: ID of the file to process
        """
        try:
            # Align tables
            aligned_df = self.align_tables(file_id)

            # Reorder columns
            reordered_df = self.reorder_columns(aligned_df)

            # Save to output directory
            output_file = self.output_dir / f"aligned_nf_{file_id}.csv"
            reordered_df.to_csv(output_file, index=False)
            print(f"Processed file {file_id} and saved to {output_file}")

        except Exception as e:
            print(f"Error processing file {file_id}: {e}")

    def process_all_files(self) -> None:
        """Process all matching files in both directories."""
        file_ids = self.get_matching_file_ids()
        print(f"Found {len(file_ids)} matching files")

        for file_id in file_ids:
            self.process_file(file_id)


def main():
    parser = argparse.ArgumentParser(
        description="Align and join tables from inferred outputs and ground truth."
    )
    parser.add_argument(
        "--pred-dir",
        type=str,
        default="/home/ec2-user/project/genai-curator/client/demos/extract_metadata/output",
        help="Directory containing predicted/inferred tables",
    )
    parser.add_argument(
        "--gt-dir",
        type=str,
        default="/home/ec2-user/project/sandbox/data/extract_metadata_gt/neurofibromatosis-dataset-analysis-main/CIM_update",
        help="Directory containing ground truth tables",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/home/ec2-user/project/genai-curator/experiments/extract_metadata/output",
        help="Directory to save aligned tables",
    )
    parser.add_argument(
        "--pred-prefix",
        type=str,
        default="extracted_metadata_nf_",
        help="Prefix of predicted table filenames",
    )
    parser.add_argument(
        "--gt-prefix",
        type=str,
        default="filtered_nf_",
        help="Prefix of ground truth table filenames",
    )
    parser.add_argument(
        "--file-id",
        type=str,
        help="Process only a specific file ID (e.g., '1' for nf_1)",
    )

    args = parser.parse_args()

    # Create the aligner
    aligner = TableAligner(
        args.pred_dir,
        args.gt_dir,
        args.output_dir,
        args.pred_prefix,
        args.gt_prefix,
    )

    # Process files
    if args.file_id:
        aligner.process_file(args.file_id)
    else:
        aligner.process_all_files()


if __name__ == "__main__":
    main()
