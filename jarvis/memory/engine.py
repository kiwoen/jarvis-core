"""
JARVIS Memory Engine.

A hybrid memory system combining:
1. Episodic Memory — conversation history, task records (ChromaDB)
2. Semantic Memory — facts, knowledge, learned patterns
3. Working Memory — active context window (short-term)
4. Procedural Memory — skill templates, code patterns, best practices

Memory Compression:
    When episodic memory exceeds threshold, the engine automatically
    summarizes older conversations into semantic summaries, preserving
    key facts while reducing token cost.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("jarvis.memory")


@dataclass
class MemoryEntry:
    """A unit of memory — conversation turn, fact, or observation."""

    key: str
    content: str
    entry_type: str  # "conversation", "fact", "skill", "observation"
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    importance: float = 0.5  # 0-1, used for retention priority
    access_count: int = 0

    def increment_access(self) -> None:
        self.access_count += 1
        # Importance decay model: frequently accessed = more important
        self.importance = min(1.0, self.importance + 0.01 * self.access_count)


class MemoryEngine:
    """Hybrid memory with automatic compression and retrieval."""

    def __init__(
        self,
        persist_dir: str = "./data/memory",
        max_entries: int = 100000,
        compression_threshold: int = 5000,
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.compression_threshold = compression_threshold

        # Episodic: ordered conversation history
        self.episodic: OrderedDict[str, MemoryEntry] = OrderedDict()

        # Semantic: key facts extracted from conversations
        self.semantic: dict[str, MemoryEntry] = {}

        # Working: current context (limited size)
        self.working: list[str] = []

        # Procedural: skill/pattern templates
        self.procedural: dict[str, Any] = {}

        self._load()

    async def store(
        self,
        key: str,
        value: Any,
        entry_type: str = "conversation",
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> None:
        """Store a new memory entry."""
        content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)

        entry = MemoryEntry(
            key=key,
            content=content,
            entry_type=entry_type,
            metadata=metadata or {},
            importance=importance,
        )

        if entry_type == "fact":
            self.semantic[key] = entry
        else:
            self.episodic[key] = entry
            if len(self.episodic) > self.compression_threshold:
                await self._compress()

        # Evict oldest if over capacity
        while len(self.episodic) > self.max_entries:
            oldest = next(iter(self.episodic))
            if self.episodic[oldest].importance > 0.8:
                # High-importance entries go to long-term storage
                await self._archive(self.episodic[oldest])
            del self.episodic[oldest]

        self._save()

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        entry_types: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Retrieve memories relevant to a query.

        Uses keyword + semantic matching (in production, ChromaDB embeddings).
        """
        results: list[tuple[float, MemoryEntry]] = []

        all_entries = list(self.episodic.values()) + list(self.semantic.values())
        if entry_types:
            all_entries = [e for e in all_entries if e.entry_type in entry_types]

        for entry in all_entries:
            score = self._compute_relevance(query, entry)
            if score > 0:
                results.append((score, entry))

        results.sort(key=lambda x: x[0], reverse=True)
        top_entries = [e for _, e in results[:top_k]]

        for entry in top_entries:
            entry.increment_access()

        return top_entries

    async def get_context_window(self, max_tokens: int = 100000) -> str:
        """Get the current context window for LLM consumption."""
        # Prioritize: working > recent episodic > high-importance semantic
        context_parts = list(self.working[-50:])  # Last 50 working items

        recent_episodic = list(self.episodic.values())[-100:]
        for entry in recent_episodic:
            context_parts.append(f"[{entry.entry_type}] {entry.content[:500]}")

        for entry in sorted(
            self.semantic.values(),
            key=lambda e: e.importance,
            reverse=True,
        )[:20]:
            context_parts.append(f"[fact:{entry.key}] {entry.content[:300]}")

        return "\n---\n".join(context_parts)

    async def add_fact(self, fact: str, source: str = "observation") -> None:
        """Add a semantic fact to memory."""
        fact_key = hashlib.sha256(fact.encode()).hexdigest()[:16]
        if fact_key not in self.semantic:
            await self.store(
                key=fact_key,
                value=fact,
                entry_type="fact",
                metadata={"source": source},
                importance=0.7,
            )

    async def add_skill_template(self, name: str, template: dict) -> None:
        """Store a reusable skill/code pattern."""
        self.procedural[name] = {
            "template": template,
            "added_at": time.time(),
            "use_count": 0,
        }
        self._save()

    async def _compress(self) -> None:
        """Compress old episodic memories into semantic summaries.

        Groups conversations by topic and extracts key facts,
        then replaces raw conversation turns with concise summaries.
        """
        if len(self.episodic) < self.compression_threshold:
            return

        logger.info("Compressing episodic memory (%d entries)", len(self.episodic))

        # Take the oldest third of entries for compression
        entries_to_compress = list(self.episodic.values())[: len(self.episodic) // 3]

        # Group by approximate topic (simplified — production uses clustering)
        topics: dict[str, list[str]] = {}
        for entry in entries_to_compress:
            topic = entry.metadata.get("domain", "general")
            if topic not in topics:
                topics[topic] = []
            topics[topic].append(entry.content[:300])

        # Generate summaries per topic
        for topic, contents in topics.items():
            combined = " | ".join(contents[-10:])  # Last 10 per topic
            summary = f"[Compressed {topic} conversation: {combined[:500]}]"
            await self.add_fact(summary, source=f"compression:{topic}")

        # Remove compressed entries
        for entry in entries_to_compress[: len(self.episodic) // 3]:
            if entry.key in self.episodic:
                del self.episodic[entry.key]

        logger.info("Compression complete — %d entries remaining", len(self.episodic))

    async def _archive(self, entry: MemoryEntry) -> None:
        """Archive high-importance entry to long-term storage."""
        archive_path = self.persist_dir / "archive.jsonl"
        record = {
            "key": entry.key,
            "content": entry.content,
            "entry_type": entry.entry_type,
            "metadata": entry.metadata,
            "timestamp": entry.timestamp,
            "importance": entry.importance,
            "access_count": entry.access_count,
        }
        with open(archive_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _compute_relevance(self, query: str, entry: MemoryEntry) -> float:
        """Compute relevance score between query and memory entry.

        Simplified BM25-like scoring. Production uses embedding cosine similarity.
        """
        query_terms = set(query.lower().split())
        content_terms = set(entry.content.lower().split())
        entry_terms = set(entry.metadata.get("tags", []))

        all_target_terms = content_terms | entry_terms
        if not all_target_terms:
            return 0.0

        overlap = query_terms & all_target_terms
        jaccard = len(overlap) / len(query_terms | all_target_terms)

        # Boost by importance and recency
        recency_boost = 1.0 / (1.0 + (time.time() - entry.timestamp) / 86400)
        importance_boost = entry.importance

        return jaccard * (0.5 + 0.3 * recency_boost + 0.2 * importance_boost)

    def _save(self) -> None:
        """Persist memory to disk."""
        # Save episodic
        episodic_path = self.persist_dir / "episodic.jsonl"
        episodic_items = list(self.episodic.values())[-5000:]
        with open(episodic_path, "w", encoding="utf-8") as f:
            for entry in episodic_items:
                f.write(json.dumps({
                    "key": entry.key,
                    "content": entry.content,
                    "entry_type": entry.entry_type,
                    "metadata": entry.metadata,
                    "timestamp": entry.timestamp,
                    "importance": entry.importance,
                    "access_count": entry.access_count,
                }, ensure_ascii=False) + "\n")

        # Save semantic
        semantic_path = self.persist_dir / "semantic.jsonl"
        with open(semantic_path, "w", encoding="utf-8") as f:
            for entry in self.semantic.values():
                f.write(json.dumps({
                    "key": entry.key,
                    "content": entry.content,
                    "entry_type": entry.entry_type,
                    "metadata": entry.metadata,
                    "timestamp": entry.timestamp,
                    "importance": entry.importance,
                }, ensure_ascii=False) + "\n")

    def _load(self) -> None:
        """Load memory from disk."""
        for filename, target, entry_type in [
            ("episodic.jsonl", self.episodic, "conversation"),
            ("semantic.jsonl", self.semantic, "fact"),
        ]:
            file_path = self.persist_dir / filename
            if file_path.exists():
                with open(file_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                data = json.loads(line)
                                entry = MemoryEntry(
                                    key=data["key"],
                                    content=data["content"],
                                    entry_type=data.get("entry_type", entry_type),
                                    metadata=data.get("metadata", {}),
                                    timestamp=data.get("timestamp", time.time()),
                                    importance=data.get("importance", 0.5),
                                    access_count=data.get("access_count", 0),
                                )
                                target[data["key"]] = entry
                            except (json.JSONDecodeError, KeyError):
                                pass
