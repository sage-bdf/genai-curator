# Table Alignment and Analysis Tool

This tool aligns and joins tables from inferred outputs and ground truth data, and provides analysis capabilities for the aligned tables. It creates a joined table where columns are ordered alternating between "X_pred" and "X_gt", with columns present in the ground truth table prioritized first.

## Features

- Case-insensitive column matching between inferred and ground truth tables
- Prioritizes columns that exist in ground truth tables
- Alternates columns between prediction and ground truth for easy comparison
- Handles columns that exist in only one of the tables
- Preserves original column names with \_pred and \_gt suffixes
- Analyzes aligned tables to calculate statistics and match rates

## Directory Structure

```
extract_metadata/
├── README.md                 # Main documentation
├── src/                      # Core implementation
│   ├── __init__.py
│   ├── analyzer.py           # Table analysis functionality
│   ├── csv_comparator.py     # CSV comparison functionality
│   └── table_aligner.py      # Table alignment functionality
├── scripts/                  # Command-line interface scripts
│   ├── align_tables.py       # Script to run the aligner
│   └── analyze_tables.py     # Script to analyze aligned tables
├── data/                     # Data directory
│   ├── ground_truth/         # Ground truth data
│   ├── predicted/            # Predicted/inferred data
│   └── output/               # Output directory for aligned tables
└── notebooks/                # Jupyter notebooks for demonstrations
    ├── README.md             # Notebook usage instructions
    ├── compare_demo.ipynb    # Demo of CSV comparison
    └── example_analysis.ipynb # Demo of table analysis
```

## Usage

### Basic Usage

Run the script to process all matching files:

```bash
cd scripts
python align_tables.py
```

This will:

1. Find all matching files between the inferred and ground truth directories
2. Align and join the tables
3. Save the results to the output directory

### List Available Files

To see which files are available for processing:

```bash
cd scripts
python align_tables.py --list-files
```

### Process a Single File

To process only a specific file:

```bash
cd scripts
python align_tables.py --file-id 1  # Process only nf_1
```

### Custom Directories

You can specify custom directories for input and output:

```bash
cd scripts
python align_tables.py \
  --pred-dir /path/to/predicted/tables \
  --gt-dir /path/to/ground/truth/tables \
  --output-dir /path/to/output/directory
```

## Output Format

The output tables have columns ordered as follows:

1. Columns present in both tables, alternating between pred and gt
2. Columns present only in ground truth tables
3. Columns present only in predicted tables

For example, if the original tables have columns:

- Predicted: "name", "age", "height"
- Ground Truth: "Name", "Age", "Weight"

The output will have columns:

- "name_pred", "Name_gt", "age_pred", "Age_gt", "Weight_gt", "height_pred"

## Implementation Details

The alignment process works as follows:

1. Load corresponding files from both directories
2. Normalize column names for case-insensitive matching
3. Identify columns present in both files and unique to each file
4. Create a joined table with alternating columns
5. Reorder columns to prioritize those present in ground truth
6. Save the output to a new file

## Analyzing Aligned Tables

After aligning tables, you can use the `analyze_tables.py` script to analyze the results:

### Generate a Summary Report

```bash
cd scripts
python analyze_tables.py --report
```

This will show:

- Total number of files processed
- Total unique columns across all files
- Number of columns in predictions only
- Number of columns in ground truth only
- Number of common columns
- Average match rate between predicted and ground truth values

### Column Statistics

```bash
cd scripts
python analyze_tables.py --column-stats
```

This will show which columns appear in which tables (predicted, ground truth, or both).

### Calculate Match Rates

For all files:

```bash
cd scripts
python analyze_tables.py --match-rates
```

For a specific file:

```bash
cd scripts
python analyze_tables.py --match-rates --file-id 1
```

This will calculate how often the predicted values match the ground truth values for each column.

### Save Results to CSV

```bash
cd scripts
python analyze_tables.py --column-stats --output column_stats.csv
python analyze_tables.py --match-rates --output match_rates.csv
```

This will save the analysis results to CSV files for further processing.

## Jupyter Notebooks

The `notebooks` directory contains Jupyter notebooks that demonstrate how to use the table alignment and analysis tools. See the README.md file in the notebooks directory for more information.
