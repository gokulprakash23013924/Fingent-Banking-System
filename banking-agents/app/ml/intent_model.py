"""Tier 1: TF-IDF (character + word n-grams) with logistic regression. Trains in a few seconds, no GPU, no API."""
from __future__ import annotations

import os
import threading

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from ..config import get_settings
from ..gateway.pii import mask_pii
from ..intents import normalize
from .training_data import generate

_lock = threading.RLock()
_cache: dict[str, "IntentModel"] = {}


class IntentModel:
    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        self.classes = list(pipeline.classes_)

    def predict(self, text: str) -> tuple[str, float, dict[str, float]]:
        probs = self.pipeline.predict_proba([normalize(text)])[0]
        dist = {c: float(p) for c, p in zip(self.classes, probs)}
        best = max(dist, key=dist.get)
        return best, dist[best], dist


def _build() -> Pipeline:
    feats = FeatureUnion([
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)),
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True)),
    ])
    return Pipeline([("feats", feats), ("clf", LogisticRegression(C=20, max_iter=3000))])


def model_path() -> str:
    return os.path.join(get_settings().models_dir, "intent.joblib")


def train_and_save(seed: int = 7, per_intent: int = 70) -> dict:
    xs, ys = generate(seed=seed, per_intent=per_intent)
    xs = [normalize(mask_pii(x).text) for x in xs]
    pipe = _build()
    pipe.fit(xs, ys)
    os.makedirs(get_settings().models_dir, exist_ok=True)
    joblib.dump(pipe, model_path())
    with _lock:
        _cache.pop(model_path(), None)
    return {"examples": len(xs), "intents": len(set(ys)), "path": model_path()}


def get_intent_model() -> IntentModel:
    path = model_path()
    with _lock:
        if path not in _cache:
            if not os.path.exists(path):
                train_and_save()
            _cache[path] = IntentModel(joblib.load(path))
        return _cache[path]


def reset_cache() -> None:
    with _lock:
        _cache.clear()
