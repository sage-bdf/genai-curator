# This deliverable is considered developed content as defined in contract between BDF parties.


"""LLM-based correction node for metadata correction pipeline."""

import json
import asyncio
from textwrap import dedent
from enum import Enum
from itertools import groupby
from operator import attrgetter
from textwrap import dedent
from typing import Any, Dict, List, Mapping, Optional, Tuple

from langchain.chat_models.base import BaseChatModel
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain.schema.messages import AIMessage, BaseMessage
from langchain.schema.runnable import Runnable
from langchain_aws import ChatBedrock
from loguru import logger
from pydantic import BaseModel

from fix_values.pipeline.core.models import (
    CellError,
    CorrectionAttempt,
    CorrectionMethod,
    CorrectionResult,
    PipelineState,
    Schema,
    SchemaField,
)
from fix_values.pipeline.nodes.base import CorrectionNode, NodeConfig


class ConfidenceLevel(str, Enum):
    """Confidence levels for LLM corrections."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREMELY_HIGH = "extremely_high"

    @classmethod
    def from_float(cls, score: float) -> "ConfidenceLevel":
        """Convert a float confidence score to a confidence level."""
        if score < 0.5:
            return cls.LOW
        elif score < 0.7:
            return cls.MEDIUM
        elif score < 0.9:
            return cls.HIGH
        else:
            return cls.EXTREMELY_HIGH

    def is_sufficient(self) -> bool:
        """Check if confidence level is sufficient for making corrections."""
        return self in [self.HIGH, self.EXTREMELY_HIGH]

    def to_float(self) -> float:
        """Convert confidence level to float value."""
        confidence_map = {
            self.LOW: 0.3,
            self.MEDIUM: 0.6,
            self.HIGH: 0.8,
            self.EXTREMELY_HIGH: 1.0,
        }
        return confidence_map[self]


class Correction(BaseModel):
    """Individual correction with its confidence level."""

    value: str
    confidence: ConfidenceLevel


class RowLLMResponse(BaseModel):
    """Structured response from LLM for entire row corrections."""

    corrections: Dict[str, Correction]  # column -> Correction object
    reasoning: Optional[str] = None


class BatchLLMResponse(BaseModel):
    """Response from LLM for multiple rows."""

    row_corrections: Dict[int, Dict[str, Correction]]  # row_idx -> column -> Correction
    reasoning: Optional[Dict[int, str]] = None  # row_idx -> reasoning


class LLMNode(CorrectionNode[List[CellError], List[CorrectionResult]]):
    """LLM-based correction node."""

    def __init__(
        self,
        schema: Schema,
        config: NodeConfig,
        llm_config: Mapping[str, Any],
        batch_size: int,
        batch_mode: str,
    ) -> None:
        """Initialize LLM correction node.

        Args:
            schema: Metadata schema
            config: Node configuration
            llm_config: Configuration for AWS Bedrock containing:
                - model_id: The Bedrock model ID
                - temperature: (optional) Temperature for sampling
                - max_tokens: (optional) Maximum tokens to generate
        """
        super().__init__(config)
        self.schema = schema

        # Create output parser
        self.parser = PydanticOutputParser(pydantic_object=RowLLMResponse)
        self.batch_size = batch_size
        self.batch_mode = batch_mode

        # Create prompt templates
        self.single_row_template = dedent(
            """You are helping to correct metadata values in a row of data.

            Row current values:
            {row_values}

            Errors to fix:
            {errors_list}

            Context:
            {context}

            {format_instructions}

            Please suggest corrections for errors in this row, return an element for each correction you are confident in. Return a JSON object with:
            - 'corrections': an object where each key is a column name and each value is an object containing:
              - 'value': the corrected value
              - 'confidence': one of ["low", "medium", "high", "extremely_high"] based on your certainty for this specific correction
            - 'reasoning': explanation of your corrections and confidence levels

            Only provide corrections you are highly confident about!
            If you are not confident enough (low or medium confidence) for any correction, explain why in the reasoning.
            You may provide corrections with different confidence levels - each correction will be evaluated individually."""
        )

        self.batch_template = dedent(
            """You are helping to correct metadata values in multiple rows of data.

            For each row, here are the current values and errors to fix:
            {batch_data}
            
            Context for all fields:
            {context}
            
            Please suggest corrections for errors in each row. Return a JSON object with:
            - 'row_corrections': an object where:
              - each key is a row index
              - each value is an object containing column corrections where:
                - key is the column name
                - value is an object containing:
                  - 'value': the corrected value
                  - 'confidence': one of ["low", "medium", "high", "extremely_high"]
            - 'reasoning': an object where:
              - each key is a row index
              - each value is the reasoning for that row's corrections
            
            Only provide corrections you are highly confident about!
            If you are not confident enough (low or medium confidence) for any correction, explain why in the reasoning."""
        )

        # Create parsers and prompts
        self.single_row_parser = PydanticOutputParser(pydantic_object=RowLLMResponse)
        self.batch_parser = PydanticOutputParser(pydantic_object=BatchLLMResponse)

        self.single_row_prompt = PromptTemplate(
            template=self.single_row_template,
            input_variables=["row_values", "errors_list", "context"],
            partial_variables={
                "format_instructions": self.single_row_parser.get_format_instructions()
            },
        )

        self.batch_prompt = PromptTemplate(
            template=self.batch_template,
            input_variables=["batch_data", "context"],
            partial_variables={
                "format_instructions": self.batch_parser.get_format_instructions()
            },
        )

        logger.info(f"[{self.config.name}] Initializing LLMNode:")
        logger.info(f"[{self.config.name}] - Model: {llm_config['model_id']}")
        logger.debug(f"[{self.config.name}] - Config: {llm_config}")

        # Initialize Bedrock client
        self.llm: BaseChatModel = ChatBedrock(
            model=llm_config["model_id"],  # model instead of model_id for ChatBedrock
            model_kwargs={
                "temperature": float(llm_config.get("temperature", 0.7)),
                "max_tokens": int(llm_config.get("max_tokens", 100)),
            },
            streaming=False,
            verbose=False,
            callbacks=self.config.callbacks,
            cache=None,
            tags=None,
        )

        # Create the chains using RunnableSequence with cleaning step
        self.single_row_chain: Runnable[Dict[str, Any], RowLLMResponse] = (
            self.single_row_prompt
            | self.llm
            | (lambda x: self.clean_llm_response(x))  # Add cleaning step
            | self.single_row_parser
        ).with_retry(retry_if_exception_type=(Exception,), stop_after_attempt=3)

        self.batch_chain: Runnable[Dict[str, Any], BatchLLMResponse] = (
            self.batch_prompt
            | self.llm
            | (lambda x: self.clean_llm_response(x))  # Add cleaning step
            | self.batch_parser
        ).with_retry(retry_if_exception_type=(Exception,), stop_after_attempt=3)

    def clean_llm_response(self, response: BaseMessage) -> str:
        """Clean LLM response of any unwanted markers or formatting"""
        # Remove common response markers
        markers = [
            # Response markers
            "<\\response_begin>",
            "<\\response_end>",
            "<response_begin>",
            "<response_end>",
            "Here is the JSON object containing the requested information:",
            # Code block markers
            "```json",
            "```python",
            "```",
            # JSON response markers
            "JSON response:",
            "Here's the JSON:",
            "The JSON object is:",
            # Common prefixes/suffixes
            "Here is the analysis:",
            "Analysis:",
            # XML-style tags
            "<output>",
            "</output>",
            "<result>",
            "</result>",
            # Markdown formatting
            "`",
            # Other common artifacts
            "\n\n",  # Multiple newlines
        ]

        # Get content as string, handling AIMessage case
        content: str
        if isinstance(response, AIMessage):
            msg_content = response.content
            content = str(msg_content) if msg_content is not None else ""
        else:
            content = str(response)

        # Clean the content
        cleaned = content
        for marker in markers:
            cleaned = cleaned.replace(str(marker), "")  # Ensure marker is string

        # Additional cleaning steps
        cleaned = cleaned.strip()  # Remove leading/trailing whitespace

        # Handle multiple newlines
        while "\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n", "\n")

        # Remove any lines that don't look like JSON
        cleaned_lines = []
        for line in cleaned.split("\n"):
            line = line.strip()
            if line and (
                line.startswith("{")
                or line.startswith("}")
                or line.startswith('"')
                or ":" in line
                or line.startswith("[")
                or line.startswith("]")
                or line.startswith(",")
            ):
                cleaned_lines.append(line)

        cleaned = "\n".join(cleaned_lines)

        # Start of JSON
        index = cleaned.find("{")
        if index != -1:
            cleaned = cleaned[index:]

        # End of JSON
        index = cleaned.rfind("}")
        if index != -1:
            cleaned = cleaned[: index + 1]

        return cleaned

    async def _process_impl(
        self,
        state: PipelineState,
    ) -> Dict[str, Any]:
        """Apply LLM-based corrections by processing rows in batches.

        Args:
            state: Current pipeline state containing errors to process

        Returns:
            Dictionary of state updates for LangGraph
        """
        logger.info("[LLM]")
        logger.info(f"Error Count: {len(state.errors)}")
        results: List[CorrectionResult] = []

        # Group errors by row_idx and materialize the groups
        sorted_errors = sorted(state.errors, key=attrgetter("row_idx"))
        row_groups = [
            (k, list(g)) for k, g in groupby(sorted_errors, key=attrgetter("row_idx"))
        ]

        # Process rows in batches
        total_batches = (len(row_groups) + self.batch_size - 1) // self.batch_size
        logger.info(
            f"[{self.config.name}] Processing {len(row_groups)} rows in {total_batches} batches"
        )

        for i in range(0, len(row_groups), self.batch_size):
            batch = row_groups[i : i + self.batch_size]
            if not batch:
                continue

            logger.info(
                f"[{self.config.name}] Processing batch {i//self.batch_size + 1} of {total_batches}"
            )
            logger.debug(f"[{self.config.name}] Batch size: {len(batch)}")

            # Filter out rows with no errors or missing fields
            valid_batch = []
            batch_fields = {}
            for row_idx, row_errors in batch:
                if not row_errors:
                    logger.debug(
                        f"[{self.config.name}] No errors to process for row {row_idx}"
                    )
                    continue

                logger.debug(
                    f"[{self.config.name}] Processing {len(row_errors)} errors for row {row_idx}"
                )

                # Get fields for all errors in this row
                fields = {
                    error.column: self.schema.get_field(error.column)
                    for error in row_errors
                }

                # Skip if any field is missing
                if not all(fields.values()):
                    continue

                valid_batch.append((row_idx, row_errors))
                batch_fields[row_idx] = fields

            if not valid_batch:
                continue

            # Process batch based on mode
            if self.batch_mode == "combined" and len(valid_batch) > 1:
                # Process multiple rows in single LLM request
                batch_response = await self._get_valid_batch_response(
                    valid_batch, batch_fields, state
                )

                if batch_response and batch_response.row_corrections:
                    # Process corrections for each row
                    for row_idx, corrections in batch_response.row_corrections.items():
                        row_errors = next(
                            errors for idx, errors in valid_batch if idx == row_idx
                        )
                        fields = batch_fields[row_idx]

                        # Create correction attempts for each corrected column
                        for error in row_errors:
                            if error.column in corrections:
                                correction = corrections[error.column]
                                if correction.confidence.is_sufficient():
                                    # Create correction attempt
                                    attempt = CorrectionAttempt(
                                        method=CorrectionMethod.LLM,
                                        row_idx=error.row_idx,
                                        column=error.column,
                                        proposed_value=correction.value,
                                        confidence=correction.confidence.to_float(),
                                        metadata={
                                            "field_name": fields[error.column].name,
                                            "error_type": error.error_type,
                                            "confidence_level": correction.confidence.value,
                                            "reasoning": (
                                                batch_response.reasoning.get(row_idx)
                                                if batch_response.reasoning
                                                else None
                                            ),
                                        },
                                    )

                                    result = CorrectionResult(
                                        error_id=error.id, attempt=attempt, success=True
                                    )
                                    results.append(result)

                                    # Update state
                                    error.correction_attempts.append(attempt)
                                    state.correction_history.append(attempt)
                                    state.metadata.at[error.row_idx, error.column] = (
                                        correction.value
                                    )
                                    logger.info(
                                        f"[{self.config.name}] Applied correction: "
                                        f"{error.value} -> {correction.value}"
                                    )

                        if (
                            batch_response.reasoning
                            and row_idx in batch_response.reasoning
                        ):
                            logger.debug(
                                f"[{self.config.name}] Row {row_idx} reasoning: {batch_response.reasoning[row_idx]}"
                            )

                        # Log any skipped corrections
                        skipped = [
                            (col, corr.confidence.value)
                            for col, corr in corrections.items()
                            if not corr.confidence.is_sufficient()
                        ]
                        if skipped:
                            logger.info(
                                f"[{self.config.name}] Skipping corrections for row {row_idx} due to "
                                f"insufficient confidence: {', '.join(f'{col}({conf})' for col, conf in skipped)}"
                            )
            else:
                # Process rows in parallel
                batch_tasks = [
                    self._get_valid_response(row_errors, fields, state)
                    for row_idx, row_errors in valid_batch
                ]

                # Process all rows in batch concurrently
                batch_results = await asyncio.gather(
                    *batch_tasks, return_exceptions=True
                )

                # Process results for each row
                for (row_idx, row_errors), result in zip(valid_batch, batch_results):
                    fields = batch_fields[row_idx]

                    # Handle exceptions from async processing
                    if isinstance(result, Exception):
                        logger.error(
                            f"[{self.config.name}] Failed to process row {row_idx}: {result}"
                        )
                        continue

                    # Skip if no valid response
                    if not result:
                        logger.warning(
                            f"[{self.config.name}] Could not get valid corrections for row {row_idx}"
                        )
                        continue

                    # Process valid response
                    parsed = cast(RowLLMResponse, result)
                    if parsed.corrections:
                        # Create correction attempts for each corrected column
                        for error in row_errors:
                            if error.column in parsed.corrections:
                                correction = parsed.corrections[error.column]
                                # Only apply corrections with sufficient confidence
                                if correction.confidence.is_sufficient():
                                    # Create correction attempt
                                    attempt = CorrectionAttempt(
                                        method=CorrectionMethod.LLM,
                                        row_idx=error.row_idx,
                                        column=error.column,
                                        proposed_value=correction.value,
                                        confidence=correction.confidence.to_float(),
                                        metadata={
                                            "field_name": fields[error.column].name,
                                            "error_type": error.error_type,
                                            "confidence_level": correction.confidence.value,
                                            "reasoning": parsed.reasoning,
                                        },
                                    )

                                    result = CorrectionResult(
                                        error_id=error.id, attempt=attempt, success=True
                                    )
                                    results.append(result)

                                    # Update state
                                    error.correction_attempts.append(attempt)
                                    state.correction_history.append(attempt)
                                    state.metadata.at[error.row_idx, error.column] = (
                                        correction.value
                                    )
                                    logger.info(
                                        f"[{self.config.name}] Applied correction: "
                                        f"{error.value} -> {parsed.corrections[error.column].value}"
                                    )

                        if parsed.reasoning:
                            logger.debug(
                                f"[{self.config.name}] Row reasoning: {parsed.reasoning}"
                            )

                        # Log any skipped corrections
                        skipped = [
                            (col, corr.confidence.value)
                            for col, corr in parsed.corrections.items()
                            if not corr.confidence.is_sufficient()
                        ]
                        if skipped:
                            logger.info(
                                f"[{self.config.name}] Skipping corrections for row {row_idx} due to "
                                f"insufficient confidence: {', '.join(f'{col}({conf})' for col, conf in skipped)}"
                            )

        # Return state updates for LangGraph
        return {
            "metadata": state.metadata,
            "errors": state.errors,
            "correction_history": state.correction_history,
            "stats": state.stats,
            "iteration": state.iteration,
        }

    def _build_context(
        self, fields: Dict[str, SchemaField], state: PipelineState, row_idx: int
    ) -> str:
        """Build context string for prompt including all fields in the row.

        Args:
            fields: Dictionary of field schemas by column name
            state: Current pipeline state
            row_idx: Index of row being processed

        Returns:
            Context string
        """
        context_parts = []

        # Add field information
        for column, field in fields.items():
            field_parts = [f"\nField: {field.name} ({field.type})"]
            field_parts.append(f"Is Required: {field.required}")
            if field.description:
                field_parts.append(f"Description: {field.description}")
            if field.valid_values:
                field_parts.append(f"Valid values: {', '.join(field.valid_values)}")
            if field.examples:
                field_parts.append(f"Examples: {', '.join(field.examples)}")
            context_parts.append("\n".join(field_parts))

        # Add complete row data
        context_parts.append(
            f"\nComplete row data: {dict(state.metadata.iloc[row_idx])}"
        )
        return "\n".join(context_parts)

    async def _get_valid_batch_response(
        self,
        batch: List[Tuple[int, List[CellError]]],
        fields: Dict[str, Dict[str, SchemaField]],
        state: PipelineState,
    ) -> Optional[BatchLLMResponse]:
        """Get valid LLM response for multiple rows.

        Args:
            batch: List of (row_idx, errors) tuples to process
            fields: Dictionary of field schemas by row_idx and column
            state: Current pipeline state

        Returns:
            Parsed and validated response, or None if all retries fail
        """
        try:
            # Format batch data
            batch_data = []
            for row_idx, row_errors in batch:
                row_values = state.metadata.iloc[row_idx].to_dict()
                errors_list = []
                for error in row_errors:
                    errors_list.append(
                        f"Column: {error.column}\n"
                        f"Current value: {error.value}\n"
                        f"Error type: {error.error_type}\n"
                        f"Error message: {error.message}\n"
                    )
                batch_data.append(
                    f"Row {row_idx}:\n"
                    f"Values: {json.dumps(row_values, indent=2)}\n"
                    f"Errors:\n{' '.join(errors_list)}\n"
                )

            # Get LLM response using batch chain
            parsed = cast(
                BatchLLMResponse,
                self.batch_chain.invoke(
                    {
                        "batch_data": "\n".join(batch_data),
                        "context": self._build_context(
                            fields[batch[0][0]], state, batch[0][0]
                        ),  # Use first row's fields for context
                    }
                ),
            )
            logger.debug(f"[{self.config.name}] Batch response:\n{parsed}")

            # Validate all corrections against their schemas
            invalid_corrections = []
            for row_idx, corrections in list(parsed.row_corrections.items()):
                row_fields = fields[row_idx]
                for column, correction in list(corrections.items()):
                    field = row_fields.get(column)
                    if (
                        field
                        and field.valid_values
                        and correction.value not in field.valid_values
                    ):
                        invalid_corrections.append(
                            (row_idx, column, correction.value, field.valid_values)
                        )
                        del corrections[column]

            if invalid_corrections:
                logger.warning(
                    f"[{self.config.name}] Skipping invalid corrections: "
                    f"{', '.join(f'row {row_idx} {col}={val} (valid: {valid})' for row_idx, col, val, valid in invalid_corrections)}"
                )

            return parsed

        except Exception as e:
            logger.error(
                f"[{self.config.name}] Failed to get valid batch response: {e}"
            )
            return None

    async def _get_valid_response(
        self,
        errors: List[CellError],
        fields: Dict[str, SchemaField],
        state: PipelineState,
    ) -> Optional[RowLLMResponse]:
        """Get valid LLM response with retries for entire row.

        Args:
            errors: List of errors in the row to correct
            fields: Dictionary of field schemas by column name
            state: Current pipeline state

        Returns:
            Parsed and validated response, or None if all retries fail
        """
        try:
            # Validate input
            if not errors:
                logger.warning(f"[{self.config.name}] No errors provided to process")
                return None

            # Format row values and errors list
            row_idx = errors[0].row_idx
            row_values = state.metadata.iloc[row_idx].to_dict()
            errors_list = []
            for error in errors:
                errors_list.append(
                    f"Column: {error.column}\n"
                    f"Current value: {error.value}\n"
                    f"Error type: {error.error_type}\n"
                    f"Error message: {error.message}\n"
                )

            # Get LLM response using single row chain
            parsed: RowLLMResponse = self.chain.invoke(
                {
                    "row_values": json.dumps(row_values, indent=2),
                    "errors_list": "\n".join(errors_list),
                    "context": self._build_context(fields, state, row_idx),
                }
            )
            logger.debug(f"[{self.config.name}] Response:\n{parsed}")

            # Validate all corrections against their schemas
            invalid_corrections = []
            for column, correction in list(
                parsed.corrections.items()
            ):  # Use list() to avoid modification during iteration
                field = fields.get(column)
                if (
                    field
                    and field.valid_values
                    and correction.value not in field.valid_values
                ):
                    invalid_corrections.append(
                        (column, correction.value, field.valid_values)
                    )
                    del parsed.corrections[column]  # Remove invalid correction

            if invalid_corrections:
                logger.warning(
                    f"[{self.config.name}] Skipping invalid corrections for row {row_idx}: "
                    f"{', '.join(f'{col}={val} (valid: {valid})' for col, val, valid in invalid_corrections)}"
                )

            if (
                parsed.corrections
            ):  # Only log if we have any valid corrections remaining
                logger.info(
                    f"[{self.config.name}] Valid response for row {row_idx}: "
                    f"corrections={[(col, corr.value, corr.confidence.value) for col, corr in parsed.corrections.items()]}"
                )
            return parsed

        except Exception as e:
            logger.error(f"[{self.config.name}] Failed to get valid response: {e}")
            return None
