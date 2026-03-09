# Fix Metadata Notebooks

This directory contains two Jupyter notebooks specifically for the fix metadata workstream, which focuses on correcting invalid values in metadata:

## fix_metadata_demo.ipynb

A demonstration notebook that shows how to use the fix_metadata lambda function to correct invalid metadata values. This notebook walks through:

1. **Setup**:
   - AWS credentials configuration
   - S3 bucket and Lambda function setup
   - Environment preparation

2. **Fix Metadata Workflow**:
   - Schema file upload to S3
   - CSV data upload with invalid metadata values
   - Fix metadata lambda function invocation
   - Task progress monitoring
   - Results retrieval and analysis

3. **Results Analysis**:
   - Corrected metadata review
   - Correction history examination
   - Error log analysis
   - Ground truth comparison
   - Accuracy metrics calculation

Use this notebook when you need to correct metadata values in your own datasets.

## fix_metadata_evaluation.ipynb

An evaluation notebook that systematically tests the metadata correction pipeline's performance. This notebook:

1. **Evaluation Setup**:
   - Evaluation configuration
   - Results directory structure creation
   - Logging configuration
   - Test dataset preparation

2. **Pipeline Testing**:
   - Metadata correction processing
   - Ground truth validation
   - Performance metrics generation
   - Error analysis

3. **Analysis Output**:
   - Stage-wise performance plots
   - Field-level correction metrics
   - Overall evaluation metrics
   - Historical performance tracking

Use this notebook when you need to:

- Assess metadata correction accuracy
- Generate performance reports
- Compare pipeline versions
- Track correction improvements

## Requirements

- Python environment with required packages
- AWS credentials with appropriate permissions
- Access to configured S3 bucket and Lambda function
- Test datasets with metadata errors
- Ground truth datasets for comparison

### Virtual Environment Setup

To install the fix_values package in a virtual environment:

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Unix/macOS
   # or
   .\venv\Scripts\activate  # On Windows
   ```

2. Install the package in editable mode:
   From the project root:
   ```bash
   pip install -e lambdas/fix_metadata/fix_metadata/fix_values
   pip install -r client/requirements.txt
   ```
   
   Or if you're in the fix_metadata demos directory:
   ```bash
   pip install -e ../../../lambdas/fix_metadata/fix_metadata/fix_values
   pip install -r ../../requirements.txt
   ```

This will install all required packages including core dependencies (loguru, pydantic, pandas, etc.) and testing dependencies (pytest, mypy, etc.).

## Usage

1. For correcting metadata in your datasets:
   - Open `fix_metadata_demo.ipynb`
   - Set Python kernal to use venv
   - Configure AWS credentials and resources
   - Upload your schema and data files
   - Follow the metadata correction workflow
   - Review and validate corrections

2. For evaluating correction performance:
   - Open `fix_metadata_evaluation.ipynb`
   - Set Python kernal to use venv
   - Set up evaluation parameters
   - Execute the evaluation pipeline
   - Analyze the generated metrics and visualizations

## Output

Both notebooks produce structured results:

- Corrected metadata in CSV format
- Detailed correction logs
- Performance metrics and statistics
- Visualization plots (evaluation notebook)
- Ground truth comparison reports

Results are organized in dedicated directories for systematic analysis and reference.
