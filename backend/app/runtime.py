"""Build the settings-dependent runtime (retriever and assistant engine).

Used at startup and again when DevSpace saves new settings, so both take one code path.
Construction makes no model or embedding calls.
"""

from app.agent.runner import PrimaryAgent
from app.config import Settings
from app.graph.workflow import AssistantGraph
from app.rag.retrieval import HybridRetriever


def build_runtime(settings: Settings):
    retriever = HybridRetriever(settings)
    graph = (
        PrimaryAgent(settings, retriever)
        if settings.assistant_engine == "primary_agent"
        else AssistantGraph(settings, retriever)
    )
    return retriever, graph
