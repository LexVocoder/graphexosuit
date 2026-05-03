from abc import ABC, abstractmethod
from graphexosuit.core import RunResult
from langgraph.graph import StateGraph
from typing import Any, Optional


class Liner(ABC):
    @abstractmethod
    def get_graph(self) -> StateGraph:
        pass

    @abstractmethod
    def get_checkpointer(self) -> Any:
        pass

    def transform_initial_state(self, initial_state: Optional[dict]) -> Optional[dict]:
        return initial_state

    def transform_result(self, result: RunResult) -> RunResult:
        return result
