from abc import ABC, abstractmethod
from graphexosuit.core.runtime import RunResult
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from typing import Any


class ExosuitLiner(ABC):
    @abstractmethod
    def get_graph(self) -> StateGraph | CompiledStateGraph:
        pass

    @abstractmethod
    def get_checkpointer(self) -> BaseCheckpointSaver:
        pass

    def on_retry(self, thread_id: str, checkpoint_id: str) -> None:
        return

    def transform_initial_state(self, initial_state: Any) -> Any:
        return initial_state
    
    def transform_resume_value(self, resume_value: Any) -> Any:
        return resume_value

    def transform_run_result(self, result: RunResult) -> RunResult:
        return result
