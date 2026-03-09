# This deliverable is considered developed content as defined in contract between BDF parties.


"""Fuzzy matching node for metadata correction pipeline."""

from typing import Any, Dict, List

from loguru import logger
from rapidfuzz import fuzz, process

from fix_values.pipeline.core.models import (
    CellError,
    CorrectionAttempt,
    CorrectionMethod,
    CorrectionResult,
    PipelineState,
    Schema,
)
from fix_values.pipeline.nodes.base import CorrectionNode, NodeConfig


class FuzzyMatchNode(CorrectionNode[List[CellError], List[CorrectionResult]]):
    """Fuzzy matching based correction node."""

    def __init__(
        self,
        schema: Schema,
        config: NodeConfig,
        threshold: float = 0.85,
        max_candidates: int = 3,
    ) -> None:
        """Initialize fuzzy matching node.

        Args:
            schema: Metadata schema
            config: Node configuration
            threshold: Minimum similarity score (0-1)
            max_candidates: Maximum number of candidates to consider
        """
        super().__init__(config)
        self.schema = schema
        self.threshold = threshold
        self.max_candidates = max_candidates

    async def _process_impl(
        self,
        state: PipelineState,
    ) -> Dict[str, Any]:
        """Apply fuzzy matching based corrections.

        Args:
            state: Current pipeline state containing errors to process

        Returns:
            Dictionary of state updates for LangGraph
        """
        logger.info("[FUZZY MATCH]")
        logger.info(f"Error Count: {len(state.errors)}")
        results: List[CorrectionResult] = []

        for error in state.errors:
            if error.error_type != "vocabulary":
                continue

            field = self.schema.get_field(error.column)
            if not field or not field.valid_values:
                logger.error(f"No Valid Values For Column: {error.column}")
                continue

            # Get fuzzy matches
            matches = process.extract(
                str(error.value),
                field.valid_values,
                scorer=fuzz.ratio,
                limit=self.max_candidates,
            )

            # Filter by threshold
            valid_matches = [
                (match, score)
                for match, score, _ in matches
                if score >= self.threshold * 100
            ]

            if not valid_matches:
                continue

            # Check for ambiguous matches with equal scores
            if len(valid_matches) >= 2:
                best_score = valid_matches[0][1]
                second_best_score = valid_matches[1][1]
                if (
                    abs(best_score - second_best_score) < 0.01
                ):  # Small epsilon for float comparison
                    logger.info(
                        f"Skipping ambiguous correction - multiple matches with score {best_score}"
                    )
                    continue

            # Use best match
            best_match, score = valid_matches[0]

            attempt = CorrectionAttempt(
                method=CorrectionMethod.FUZZY,
                row_idx=error.row_idx,
                column=error.column,
                proposed_value=best_match,
                confidence=score / 100,
                metadata={
                    "all_matches": [
                        {"value": match, "score": score / 100}
                        for match, score in valid_matches
                    ]
                },
            )

            result = CorrectionResult(error_id=error.id, attempt=attempt, success=True)
            results.append(result)

            # Update state
            error.correction_attempts.append(attempt)
            state.correction_history.append(attempt)
            state.metadata.at[error.row_idx, error.column] = best_match

        # Return state updates for LangGraph
        return {
            "metadata": state.metadata,
            "errors": state.errors,
            "correction_history": state.correction_history,
            "stats": state.stats,
            "iteration": state.iteration,
        }
