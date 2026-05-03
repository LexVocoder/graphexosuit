from abc import ABC, abstractmethod
from graphexosuit.core import ResumeValue, RunResult
from langgraph.graph import StateGraph
from typing import Any, Optional


class Liner(ABC):
    @abstractmethod
    def get_graph(self) -> StateGraph:
        pass

    @abstractmethod
    def get_checkpointer(self) -> Any:
        pass

    def on_retry(self, thread_id: str, checkpoint_id: Optional[str]) -> None:
        return

    def transform_initial_state(self, initial_state: Optional[dict]) -> Optional[dict]:
        return initial_state
    
    def transform_resume_value(self, resume_value: Optional[ResumeValue]) -> Optional[ResumeValue]:
        return resume_value

    def transform_run_result(self, result: RunResult) -> RunResult:
        return result
