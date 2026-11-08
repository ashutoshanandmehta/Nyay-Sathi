"""Authoritative Indian Legal Knowledge Factory, OpenSearch index, and editorial governance."""

from app.knowledge.editorial import EditorialRegistry, LanguagePackRegistry
from app.knowledge.propositions import LegalKnowledgeFactory, LegalProposition
from app.knowledge.search_index import OpenSearchLegalIndex, is_generic_index_or_snippet

__all__ = [
    "EditorialRegistry",
    "LanguagePackRegistry",
    "LegalKnowledgeFactory",
    "LegalProposition",
    "OpenSearchLegalIndex",
    "is_generic_index_or_snippet",
]
