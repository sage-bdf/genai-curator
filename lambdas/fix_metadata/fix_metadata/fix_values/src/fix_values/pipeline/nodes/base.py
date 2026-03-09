# This deliverable is considered developed content as defined in contract between BDF parties.


"""Base classes for pipeline nodes."""

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, TypeVar

from loguru import logger
from pydantic import BaseModel

from fix_values.pipeline.core.models import PipelineState

InputType = TypeVar("InputType")
OutputType = TypeVar("OutputType")


class NodeConfig(BaseModel):
    """Base configuration for pipeline nodes."""

    name: str
    enabled: bool = True
    retry_count: int = 3
    timeout: float = 30.0
    max_concurrency: int = 4
    callbacks: Optional[List[Any]] = None


class CorrectionNode(Generic[InputType, OutputType], ABC):
    """Base class for correction pipeline nodes."""

    def __init__(self, config: NodeConfig) -> None:
        """Initialize node.

        Args:
            config: Node configuration
        """
        self.config = config

    @abstractmethod
    async def _process_impl(
        self,
        state: PipelineState,
    ) -> Dict[str, Any]:
        """Implementation of the node's processing logic.

        Args:
            state: Current pipeline state containing metadata to process

        Returns:
            Dictionary of state updates for LangGraph containing:
            - metadata: Current metadata state
            - errors: Current validation errors
            - correction_history: History of all corrections
            - stats: Pipeline statistics
            - iteration: Current pipeline iteration
        """
        raise NotImplementedError

    async def process(
        self,
        state: PipelineState,
    ) -> Dict[str, Any]:
        """Process pipeline state with timing.

        Args:
            state: Current pipeline state containing metadata to process

        Returns:
            Dictionary of state updates for LangGraph containing:
            - metadata: Current metadata state
            - errors: Current validation errors
            - correction_history: History of all corrections
            - stats: Pipeline statistics
            - iteration: Current pipeline iteration
        """
        start_time = time.perf_counter()
        result = await self._process_impl(state)
        duration = time.perf_counter() - start_time

        # Log the duration
        logger.info(
            f"[Node: {self.config.name}] Execution completed in {duration:.3f}s"
        )

        # Update stats with duration
        if "stats" not in result:
            result["stats"] = {}
        if "node_durations" not in result["stats"]:
            result["stats"]["node_durations"] = {}
        result["stats"]["node_durations"][self.config.name] = duration

        return result
