from __future__ import annotations

import re
from collections import Counter


HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@(\w+)")
URL_RE = re.compile(r"https?://\S+")
EMOJI_RE = re.compile(r"[^\w\s,.:;!?'\-/]")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = URL_RE.sub(" ", text)
    text = HASHTAG_RE.sub(r"\1", text)
    text = MENTION_RE.sub(r"\1", text)
    text = EMOJI_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def chunk_text(text: str, max_words: int = 40) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    for index in range(0, len(words), max_words):
        chunk = " ".join(words[index : index + max_words])
        if chunk:
            chunks.append(chunk)
    return chunks


def keyword_counts(texts: list[str], top_k: int = 10) -> list[str]:
    stop_words = {
        "the", "a", "an", "and", "or", "to", "for", "of", "in", "with", "is", "on",
        "my", "your", "this", "that", "it", "i",
    }
    counter: Counter[str] = Counter()
    for text in texts:
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+.-]+", text.lower()):
            if token not in stop_words and len(token) > 2:
                counter[token] += 1
    return [word for word, _ in counter.most_common(top_k)]
