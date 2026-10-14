"""Read-only StockResearchPack adapter; independent from TradingAgents internals."""

from app.research.adapter import ResearchPackError, ResearchReport, parse_research_pack

__all__ = ["ResearchPackError", "ResearchReport", "parse_research_pack"]
