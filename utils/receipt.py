# utils/receipt.py
# Version 1.0.0
"""
Receipt dataclass for context assembly (SOW v7.6.0).

Replaces the implicit dict built in build_context_for_provider(). All fields
are explicit with defaults. to_dict() serializes to the legacy format used by
receipt_store and explain_commands so existing consumers need no changes.

CREATED v1.0.0: Receipt, PlannerInfo, AlwaysOnInfo, ContinuityInfo (SOW v7.6.0)
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class PlannerInfo:
    used: bool = False
    mode: Optional[str] = None
    author_filter: List[str] = field(default_factory=list)
    time_filter_after: Optional[str] = None
    time_filter_before: Optional[str] = None
    candidates: Optional[int] = None
    planner_latency_ms: int = 0
    note: Optional[str] = None
    content_query: Optional[str] = None

    def to_dict(self):
        d = {
            "used": self.used,
            "mode": self.mode,
            "author_filter": self.author_filter,
            "time_filter": {"after": self.time_filter_after,
                            "before": self.time_filter_before},
            "candidates": self.candidates,
            "planner_latency_ms": self.planner_latency_ms,
        }
        if self.note:
            d["note"] = self.note
        if self.content_query is not None:
            d["content_query"] = self.content_query
        return d


@dataclass
class AlwaysOnInfo:
    total_tokens: int = 0
    overview_tokens: int = 0
    control_file_tokens: int = 0
    key_facts_count: int = 0
    decisions_count: int = 0
    action_items_count: int = 0
    open_questions_count: int = 0


@dataclass
class ContinuityInfo:
    session_bridge_messages: int = 0
    unsummarized_messages: int = 0
    total_continuity_messages: int = 0
    continuity_tokens: int = 0
    trimmed: bool = False


@dataclass
class Receipt:
    query: str = ""
    query_type: str = "information"
    query_embedding_path: str = "unknown"
    planner: PlannerInfo = field(default_factory=PlannerInfo)
    always_on: AlwaysOnInfo = field(default_factory=AlwaysOnInfo)
    continuity: ContinuityInfo = field(default_factory=ContinuityInfo)
    retrieved_segments: Optional[list] = None
    score_gap_applied: bool = False
    fallback_used: bool = False
    fallback_messages: int = 0
    recent_messages: int = 0
    total_context_tokens: int = 0
    budget_tokens: int = 0
    budget_used_pct: float = 0.0
    provider: str = ""
    model: str = ""
    qc_failed: bool = False
    qc_fail_details: Optional[dict] = None
    retrieved_clusters: list = field(default_factory=list)
    clusters_below_threshold: list = field(default_factory=list)

    def to_dict(self):
        """Serialize to legacy dict format for receipt_store and explain_commands."""
        import dataclasses
        d = {
            "query": self.query,
            "query_type": self.query_type,
            "query_embedding_path": self.query_embedding_path,
            "always_on": dataclasses.asdict(self.always_on),
            "continuity": dataclasses.asdict(self.continuity),
            "retrieved_segments": self.retrieved_segments,
            "score_gap_applied": self.score_gap_applied,
            "retrieved_clusters": self.retrieved_clusters,
            "clusters_below_threshold": self.clusters_below_threshold,
            "fallback_used": self.fallback_used,
            "fallback_messages": self.fallback_messages,
            "query_planner": (self.planner.to_dict()
                              if self.planner and self.planner.used else None),
            "recent_messages": self.recent_messages,
            "total_context_tokens": self.total_context_tokens,
            "budget_tokens": self.budget_tokens,
            "budget_used_pct": self.budget_used_pct,
            "provider": self.provider,
            "model": self.model,
            "qc_failed": self.qc_failed,
        }
        if self.qc_fail_details:
            d["qc_fail_details"] = self.qc_fail_details
        return d
