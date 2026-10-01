# Curator workflows

Curator workflows include comprehensive solutions for extracting, fixing, and transforming metadata using generative AI. Workflows streamline the process of ingesting research and managing metadata across different schemas.

Modules of these workflows can be exposed as tools for AI agents in a multi-agent framework.

This repository contains single-shot pipelines - no HITL iteration.

## Key Features

- **Metadata Extraction**: Extract structured metadata from research papers automatically
- **Metadata Fixing**: Correct invalid values in metadata tables to conform to approved values
- **Metadata Transformation**: Convert metadata from one schema to another

## Project Structure

- **`client/`**: Python client libraries for interacting with the API
- **`data/`**: Schema definitions and sample data
- **`documentation/`**: Project documentation
- **`experiments/`**: Evaluation tools and experiments
- **`infra/`**: AWS CDK infrastructure code
- **`lambdas/`**: AWS Lambda functions for the backend
- **`step_functions/`**: AWS Step Functions workflows

## Workflows

The project implements three main workflows:

1. **Extract Metadata**: Extracts structured metadata from research papers using AI
2. **Fix Metadata**: Corrects invalid values in metadata tables using AI validation
3. **Transform Metadata**: Converts metadata from one schema to another using AI

## Getting Started

See the [setup documentation](./documentation/setup.md) for instructions on how to set up and deploy the project.

## Additional Documentation

- [Project Context](./documentation/context.md): Background and motivation for the project
- [Workflows](./documentation/workflows.md): Detailed information about the application workflows
- [Architecture](./documentation/architecture.md): Solution architecture and design
- [API Reference](./documentation/api_reference.md): Comprehensive API documentation
- [Next Steps](./documentation/next_steps.md): Planned future work

## License

This project is licensed under the Apache License 2.0.
