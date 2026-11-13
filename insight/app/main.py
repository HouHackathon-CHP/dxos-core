# SPDX-License-Identifier: Apache-2.0
"""Stateless, internal text classification and similarity service with PhoBERT Multi-Task AI."""

import hmac
import json
import logging
import math
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("dxos.insight")

INTERNAL_SECRET = os.getenv("INTERNAL_GATEWAY_SECRET", "")
TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)

# ---------------------------------------------------------
# PhoBERT Multi-Task AI Model Loader (1 Backbone -> 3 Tasks)
# ---------------------------------------------------------
MULTITASK_DIR = Path(__file__).resolve().parent / "models" / "phobert_multitask"
LEGACY_DIR = Path(__file__).resolve().parent / "models" / "phobert_12labels"

phobert_model = None
phobert_tokenizer = None
phobert_meta = {}
LABEL12_TO_UNIT4 = {}
CLASSES_12 = []
URGENCY_CLASSES = ["high", "normal", "low"]
ID2LABEL = {}
ID2URG = {}
IS_MULTITASK = False

try:
    if (MULTITASK_DIR / "model.safetensors").exists() and (MULTITASK_DIR / "config.json").exists():
        import torch
        import torch.nn as nn
        from transformers import AutoTokenizer, AutoConfig, AutoModel
        from safetensors.torch import load_file

        class PhoBertMultiTask(nn.Module):
            def __init__(self, config, num_categories=12, num_urgencies=3):
                super().__init__()
                self.roberta = AutoModel.from_config(config)
                hidden_size = config.hidden_size
                self.category_classifier = nn.Sequential(
                    nn.Dropout(0.2),
                    nn.Linear(hidden_size, 256),
                    nn.GELU(),
                    nn.Dropout(0.2),
                    nn.Linear(256, num_categories),
                )
                self.urgency_classifier = nn.Sequential(
                    nn.Dropout(0.2),
                    nn.Linear(hidden_size, 128),
                    nn.GELU(),
                    nn.Dropout(0.2),
                    nn.Linear(128, num_urgencies),
                )

            def forward(self, input_ids, attention_mask):
                outputs = self.roberta(input_ids=input_ids, attention_mask=attention_mask, return_dict=True)
                sequence_output = outputs.last_hidden_state
                cls_output = sequence_output[:, 0, :]
                category_logits = self.category_classifier(cls_output)
                urgency_logits = self.urgency_classifier(cls_output)

                input_mask_expanded = attention_mask.unsqueeze(-1).expand(sequence_output.size()).float()
                sum_embeddings = torch.sum(sequence_output * input_mask_expanded, 1)
                sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
                mean_pooled = sum_embeddings / sum_mask
                sentence_embeddings = torch.nn.functional.normalize(mean_pooled, p=2, dim=1)

                return {
                    "category_logits": category_logits,
                    "urgency_logits": urgency_logits,
                    "sentence_embeddings": sentence_embeddings,
                }

        config = AutoConfig.from_pretrained(str(MULTITASK_DIR))
        phobert_tokenizer = AutoTokenizer.from_pretrained(str(MULTITASK_DIR))
        phobert_model = PhoBertMultiTask(config, num_categories=12, num_urgencies=3)
        state_dict = load_file(str(MULTITASK_DIR / "model.safetensors"))
        phobert_model.load_state_dict(state_dict)
        phobert_model.eval()
        IS_MULTITASK = True

        meta_path = MULTITASK_DIR / "phobert_multitask_metadata.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                phobert_meta = json.load(f)
            LABEL12_TO_UNIT4 = phobert_meta.get("label12_to_unit4", {})
            CLASSES_12 = phobert_meta.get("classes_12", [])
            ID2LABEL = {int(k): v for k, v in phobert_meta.get("id2cat", {}).items()}
            ID2URG = {int(k): v for k, v in phobert_meta.get("id2urg", {}).items()}
            URGENCY_CLASSES = phobert_meta.get("urgency_classes", ["high", "normal", "low"])
        logger.info("PhoBERT Multi-Task model (Civic + Urgency + Deduplication) loaded successfully")

    elif (LEGACY_DIR / "model.safetensors").exists() and (LEGACY_DIR / "config.json").exists():
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        phobert_tokenizer = AutoTokenizer.from_pretrained(str(LEGACY_DIR))
        phobert_model = AutoModelForSequenceClassification.from_pretrained(str(LEGACY_DIR))
        phobert_model.eval()
        IS_MULTITASK = False

        meta_path = LEGACY_DIR / "phobert_12labels_metadata.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                phobert_meta = json.load(f)
            LABEL12_TO_UNIT4 = phobert_meta.get("label12_to_unit4", {})
            CLASSES_12 = phobert_meta.get("classes_12", [])
            ID2LABEL = {int(k): v for k, v in phobert_meta.get("id2label", {}).items()}
        logger.info("Legacy PhoBERT 12-label civic model loaded successfully")
except Exception as e:
    logger.warning("PhoBERT model not loaded, running in fallback mode: %s", e)
    phobert_model = None
    IS_MULTITASK = False

if IS_MULTITASK:
    default_version = "phobert-base-v2-multitask-civic"
elif phobert_model is not None:
    default_version = "phobert-base-v2-civic-12labels"
else:
    default_version = "multinomial-nb-bow-v1"

MODEL_VERSION = os.getenv("MODEL_VERSION", default_version)


class Example(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=3, max_length=2000)


class Candidate(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=3, max_length=2000)
    latitude: float | None = None
    longitude: float | None = None
    created_at: str | None = None


class AnalysisRequest(BaseModel):
    text: str = Field(min_length=5, max_length=4000)
    labels: list[str] = Field(min_length=2, max_length=20)
    examples: list[Example] = Field(min_length=2, max_length=120)
    candidates: list[Candidate] = Field(default_factory=list, max_length=150)
    latitude: float | None = None
    longitude: float | None = None
    created_at: str | None = None


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


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two GPS coordinates on Earth in meters."""
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r * c


def parse_iso_time(ts_str: str | None) -> float | None:
    """Parse ISO 8601 timestamp string into epoch seconds."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


def classify(text: str, labels: list[str], examples: list[Example]) -> tuple[list[dict], list[str]]:
    vocabulary = set()
    word_counts = {label: Counter() for label in labels}
    document_counts = Counter()
    for example in examples:
        words = tokens(example.text)
        word_counts[example.label].update(words)
        document_counts[example.label] += 1
        vocabulary.update(words)

    query = Counter(word for word in tokens(text) if word in vocabulary)
    if not query or not vocabulary:
        return ([{"label": label, "score": round(1 / len(labels), 4)} for label in labels], [])

    civic_units = {"infrastructure", "environment", "transport", "intake"}
    is_civic = all(l in civic_units or l in LABEL12_TO_UNIT4 for l in labels)
    is_urgency = set(labels) == {"high", "normal", "low"}

    ranked = None

    # Multi-Task PhoBERT Head 2: Urgency Classification
    if is_urgency and IS_MULTITASK and phobert_model is not None and phobert_tokenizer is not None:
        try:
            import torch

            enc = phobert_tokenizer(text, truncation=True, max_length=96, return_tensors="pt")
            with torch.no_grad():
                out = phobert_model(enc["input_ids"], enc["attention_mask"])
                urg_probs = torch.softmax(out["urgency_logits"], dim=-1).cpu().numpy()[0]

            scores = {u: float(urg_probs[idx]) for idx, u in ID2URG.items()}
            total_score = sum(scores.get(l, 0.0) for l in labels) or 1.0
            ranked = sorted(
                [{"label": l, "score": round(scores.get(l, 0.0) / total_score, 4)} for l in labels],
                key=lambda item: (-item["score"], item["label"]),
            )
        except Exception as e:
            logger.warning("PhoBERT urgency inference error, falling back to NB: %s", e)
            ranked = None

    # Multi-Task PhoBERT Head 1 / Legacy Model: Civic Classification
    elif is_civic and phobert_model is not None and phobert_tokenizer is not None:
        try:
            import torch

            enc = phobert_tokenizer(text, truncation=True, max_length=96, return_tensors="pt")
            with torch.no_grad():
                if IS_MULTITASK:
                    out = phobert_model(enc["input_ids"], enc["attention_mask"])
                    logits = out["category_logits"]
                else:
                    logits = phobert_model(**enc).logits
                probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]

            scores = {}
            for l in labels:
                if l in civic_units:
                    scores[l] = sum(
                        float(probs[idx]) for idx, c12 in ID2LABEL.items() if LABEL12_TO_UNIT4.get(c12) == l
                    )
                elif l in LABEL12_TO_UNIT4:
                    idx = CLASSES_12.index(l)
                    scores[l] = float(probs[idx])
                else:
                    scores[l] = 0.0

            total_score = sum(scores.values()) or 1.0
            ranked = sorted(
                [{"label": l, "score": round(scores[l] / total_score, 4)} for l in labels],
                key=lambda item: (-item["score"], item["label"]),
            )
        except Exception as e:
            logger.warning("PhoBERT civic inference error, falling back to NB: %s", e)
            ranked = None

    # Fallback to dynamic Naive Bayes (for arbitrary custom labels or when AI model unavailable)
    if ranked is None:
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
        ranked = sorted(
            ({"label": label, "score": round(weights[label] / total, 4)} for label in labels),
            key=lambda item: (-item["score"], item["label"]),
        )

    winner = ranked[0]["label"]
    signals = sorted(
        (word for word in query if word_counts[winner][word] > 0),
        key=lambda word: (-word_counts[winner][word], word),
    )[:6]
    return ranked, signals


def similar(
    text: str,
    candidates: list[Candidate],
    query_lat: float | None = None,
    query_lon: float | None = None,
    query_time: str | None = None,
) -> list[dict]:
    if not candidates:
        return []

    # 1. Semantic Similarity (Head 3: L2-Normalized PhoBERT Embeddings OR Fallback TF-IDF)
    semantic_scores = []
    if IS_MULTITASK and phobert_model is not None and phobert_tokenizer is not None:
        try:
            import torch

            all_texts = [text] + [c.text for c in candidates]
            enc = phobert_tokenizer(all_texts, padding=True, truncation=True, max_length=96, return_tensors="pt")
            with torch.no_grad():
                out = phobert_model(enc["input_ids"], enc["attention_mask"])
                embs = out["sentence_embeddings"]
                # Cosine similarity between query (idx 0) and candidates (idx 1:)
                q_emb = embs[0:1]
                cand_embs = embs[1:]
                cos_sims = torch.mm(cand_embs, q_emb.t()).squeeze(-1).cpu().numpy()
                semantic_scores = [max(0.0, float(s)) for s in cos_sims]
        except Exception as e:
            logger.warning("PhoBERT sentence embedding error, falling back to TF-IDF: %s", e)
            semantic_scores = []

    if not semantic_scores:
        documents = [set(tokens(text)), *(set(tokens(item.text)) for item in candidates)]
        frequencies = Counter(word for document in documents for word in document)
        count = len(documents)

        def vector(document: set[str]) -> dict[str, float]:
            return {word: math.log((count + 1) / (frequencies[word] + 1)) + 1 for word in document}

        query = vector(documents[0])
        query_norm = math.sqrt(sum(value * value for value in query.values()))
        for candidate, document in zip(candidates, documents[1:]):
            other = vector(document)
            other_norm = math.sqrt(sum(value * value for value in other.values()))
            score = sum(query.get(word, 0) * other.get(word, 0) for word in document)
            score = score / (query_norm * other_norm) if query_norm and other_norm else 0.0
            semantic_scores.append(float(score))

    # 2. Spatiotemporal Fusion (GPS Location + Submission Timestamp)
    q_time_sec = parse_iso_time(query_time)
    matches = []

    for idx, candidate in enumerate(candidates):
        s_sem = semantic_scores[idx]

        # Geographic distance factor (Haversine)
        has_geo = (
            query_lat is not None
            and query_lon is not None
            and candidate.latitude is not None
            and candidate.longitude is not None
        )
        s_geo = 1.0
        geo_mismatch = False
        if has_geo:
            dist_m = haversine_distance_meters(query_lat, query_lon, candidate.latitude, candidate.longitude)
            if dist_m <= 50.0:
                s_geo = 1.0
            elif dist_m <= 1000.0:
                s_geo = max(0.0, 1.0 - (dist_m - 50.0) / 950.0)
            else:
                s_geo = 0.0

            # Far apart (> 2000 meters) in physical space cannot be the same incident
            if dist_m > 2000.0:
                geo_mismatch = True

        # Temporal delta factor (ISO 8601 created_at)
        cand_time_sec = parse_iso_time(candidate.created_at)
        has_time = q_time_sec is not None and cand_time_sec is not None
        s_time = 1.0
        if has_time:
            delta_hours = abs(q_time_sec - cand_time_sec) / 3600.0
            if delta_hours <= 24.0:
                s_time = 1.0
            elif delta_hours <= 168.0:  # Within 7 days
                s_time = max(0.0, 1.0 - (delta_hours - 24.0) / 144.0)
            else:
                s_time = 0.0

        # Composite Deduplication Score
        if geo_mismatch:
            # Physically far apart: heavily discount to avoid false duplicates
            final_score = s_sem * 0.20
        elif has_geo and has_time:
            final_score = 0.50 * s_sem + 0.35 * s_geo + 0.15 * s_time
        elif has_geo:
            final_score = 0.60 * s_sem + 0.40 * s_geo
        elif has_time:
            final_score = 0.80 * s_sem + 0.20 * s_time
        else:
            final_score = s_sem

        if final_score >= 0.35:
            matches.append({"id": candidate.id, "similarity": round(final_score, 4)})

    return sorted(matches, key=lambda item: (-item["similarity"], item["id"]))[:3]


@app.get("/health")
def health() -> dict:
    if phobert_model is not None:
        ai_status = "phobert-base-v2-multitask" if IS_MULTITASK else "phobert-base-v2-12labels"
    else:
        ai_status = "fallback-nb"
    return {"status": "ok", "service": "insight", "ai_model": ai_status}


@app.post("/analyze")
def analyze(body: AnalysisRequest, tenant: str = Depends(internal_caller)) -> dict:
    labels = list(dict.fromkeys(body.labels))
    if len(labels) != len(body.labels) or any(example.label not in labels for example in body.examples):
        raise HTTPException(status_code=422, detail="Examples must use unique declared labels")
    ranked, signals = classify(body.text, labels, body.examples)
    return {
        "model_version": MODEL_VERSION if phobert_model is not None else "multinomial-nb-bow-v1",
        "ranked_labels": ranked,
        "signals": signals,
        "similar": similar(
            body.text,
            body.candidates,
            query_lat=body.latitude,
            query_lon=body.longitude,
            query_time=body.created_at,
        ),
    }
