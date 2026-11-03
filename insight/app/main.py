# SPDX-License-Identifier: Apache-2.0
"""Stateless, internal text classification and similarity service."""

import hmac
import math
import os
import re
from collections import Counter
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


INTERNAL_SECRET = os.getenv("INTERNAL_GATEWAY_SECRET", "")
MODEL_VERSION = "multinomial-nb-bow-v1"
TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


class Example(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=3, max_length=2000)


class Candidate(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=3, max_length=2000)


class AnalysisRequest(BaseModel):
    text: str = Field(min_length=5, max_length=4000)
    labels: list[str] = Field(min_length=2, max_length=20)
    examples: list[Example] = Field(min_length=2, max_length=120)
    candidates: list[Candidate] = Field(default_factory=list, max_length=150)


app = FastAPI(title="DX-OS Insight API", docs_url=None, redoc_url=None)


def internal_caller(
    x_internal_secret: Annotated[str | None, Header()] = None,
    x_dxos_tenant: Annotated[str | None, Header()] = None,
    x_dxos_user: Annotated[str | None, Header()] = None,
) -> str:
    if not INTERNAL_SECRET or not x_internal_secret or not hmac.compare_digest(x_internal_secret, INTERNAL_SECRET):
        raise HTTPException(status_code=403, detail="Gateway access required")
    if not x_dxos_tenant or not x_dxos_user:
        raise HTTPException(status_code=403, detail="Identity context required")
    return x_dxos_tenant


def tokens(text: str) -> list[str]:
    return [word for word in TOKEN_PATTERN.findall(text.casefold()) if len(word) > 1]


def classify(text: str, labels: list[str], examples: list[Example]) -> tuple[list[dict], list[str]]:
    vocabulary = set()
    word_counts = {label: Counter() for label in labels}
    document_counts = Counter()
    for example in examples:
        words = tokens(example.text)
        word_counts[example.label].update(words)
        document_counts[example.label] += 1
        vocabulary.update(words)
    query = Counter(tokens(text))
    if not query or not vocabulary:
        return ([{"label": label, "score": round(1 / len(labels), 4)} for label in labels], [])
    total_docs = sum(document_counts.values())
    log_scores = {}
    for label in labels:
        counts = word_counts[label]
        denominator = sum(counts.values()) + len(vocabulary)
        score = math.log((document_counts[label] + 1) / (total_docs + len(labels)))
        for word, frequency in query.items():
            score += frequency * math.log((counts[word] + 1) / denominator)
        log_scores[label] = score
    offset = max(log_scores.values())
    weights = {label: math.exp(value - offset) for label, value in log_scores.items()}
    total = sum(weights.values())
    ranked = sorted(({"label": label, "score": round(weights[label] / total, 4)} for label in labels),
                    key=lambda item: (-item["score"], item["label"]))
    winner = ranked[0]["label"]
    signals = sorted(
        (word for word in query if word_counts[winner][word] > 0),
        key=lambda word: (-word_counts[winner][word], word),
    )[:6]
    return ranked, signals


def similar(text: str, candidates: list[Candidate]) -> list[dict]:
    if not candidates:
        return []
    documents = [set(tokens(text)), *(set(tokens(item.text)) for item in candidates)]
    frequencies = Counter(word for document in documents for word in document)
    count = len(documents)

    def vector(document: set[str]) -> dict[str, float]:
        return {word: math.log((count + 1) / (frequencies[word] + 1)) + 1 for word in document}

    query = vector(documents[0])
    query_norm = math.sqrt(sum(value * value for value in query.values()))
    matches = []
    for candidate, document in zip(candidates, documents[1:]):
        other = vector(document)
        other_norm = math.sqrt(sum(value * value for value in other.values()))
        score = sum(query.get(word, 0) * other.get(word, 0) for word in document)
        score = score / (query_norm * other_norm) if query_norm and other_norm else 0.0
        if score >= 0.35:
            matches.append({"id": candidate.id, "similarity": round(score, 4)})
    return sorted(matches, key=lambda item: (-item["similarity"], item["id"]))[:3]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "insight"}


@app.post("/analyze")
def analyze(body: AnalysisRequest, tenant: str = Depends(internal_caller)) -> dict:
    labels = list(dict.fromkeys(body.labels))
    if len(labels) != len(body.labels) or any(example.label not in labels for example in body.examples):
        raise HTTPException(status_code=422, detail="Examples must use unique declared labels")
    ranked, signals = classify(body.text, labels, body.examples)
    return {
        "model_version": MODEL_VERSION,
        "ranked_labels": ranked,
        "signals": signals,
        "similar": similar(body.text, body.candidates),
    }
