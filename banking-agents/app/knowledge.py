"""Small BM25 retriever over data/docs/*.md (the diagram's knowledge layer).

Pure Python, no embeddings. Add an embedding score here later and merge it with the BM25 score
to get hybrid retrieval.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .config import ROOT

DOCS_DIR = ROOT / "data" / "docs"
_STOP = {"a", "an", "the", "of", "to", "and", "or", "is", "are", "in", "on", "for", "with", "be", "by", "at", "it", "that", "this", "as", "can", "i", "my"}


def _tok(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in _STOP]


class Index:
    def __init__(self, docs_dir: Path):
        self.chunks: list[dict] = []
        for path in sorted(docs_dir.glob("*.md")):
            title = path.stem
            section = "overview"
            buf: list[str] = []

            def flush() -> None:
                text = " ".join(buf).strip()
                if text:
                    self.chunks.append({"doc": path.name, "section": section, "text": text, "tokens": _tok(f"{title} {section} {text}")})
                buf.clear()

            for line in path.read_text().splitlines():
                if line.startswith("## "):
                    flush()
                    section = line[3:].strip()
                elif line.startswith("# "):
                    continue
                elif line.strip():
                    buf.append(line.strip())
            flush()
        self.df: Counter = Counter()
        for c in self.chunks:
            self.df.update(set(c["tokens"]))
        self.avg = (sum(len(c["tokens"]) for c in self.chunks) / len(self.chunks)) if self.chunks else 1.0

    def search(self, query: str, k: int = 2, k1: float = 1.5, b: float = 0.75) -> list[dict]:
        q = _tok(query)
        n = len(self.chunks)
        scored = []
        for c in self.chunks:
            tf = Counter(c["tokens"])
            score = 0.0
            for t in q:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(c["tokens"]) / self.avg))
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        return [{"doc": c["doc"], "section": c["section"], "text": c["text"], "score": round(s, 3)} for s, c in scored[:k]]


@lru_cache(maxsize=1)
def get_index() -> Index:
    return Index(DOCS_DIR)


def search(query: str, k: int = 2) -> list[dict]:
    return get_index().search(query, k)
