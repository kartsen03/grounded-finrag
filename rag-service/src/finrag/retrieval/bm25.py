"""Okapi BM25 over chunk text, written out so every term of the formula is visible.

score(q, d) = sum over query terms t of
    idf(t) * tf(t, d) * (k1 + 1) / (tf(t, d) + k1 * (1 - b + b * |d| / avgdl))
idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))

Tokens: lowercase alphanumerics; thousands separators are dropped so "1,577" matches
"1577"; a short stopword list is removed. No stemming: filings are full of exact terms
(line-item names, tickers, years) where stemming does more harm than good.
"""

from __future__ import annotations

import re

import numpy as np
from scipy import sparse

_TOKEN = re.compile(r"[a-z0-9]+(?:[.'][a-z0-9]+)*")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was were will with "
    "what which who how did does do their our we you your".split())


def tokenize(text: str) -> list[str]:
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text.lower())
    return [t for t in _TOKEN.findall(text) if t not in STOPWORDS]


class BM25:
    def __init__(self, texts: list[str], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        vocab: dict[str, int] = {}
        rows, cols, vals = [], [], []
        lengths = np.zeros(len(texts), dtype=np.float32)
        for i, text in enumerate(texts):
            counts: dict[int, int] = {}
            tokens = tokenize(text)
            lengths[i] = len(tokens)
            for tok in tokens:
                j = vocab.setdefault(tok, len(vocab))
                counts[j] = counts.get(j, 0) + 1
            rows.extend([i] * len(counts))
            cols.extend(counts.keys())
            vals.extend(counts.values())
        self.vocab = vocab
        n_docs = len(texts)
        tf = sparse.csr_matrix((np.asarray(vals, np.float32), (rows, cols)), shape=(n_docs, len(vocab)))
        df = np.bincount(tf.indices, minlength=len(vocab)).astype(np.float32)
        self.idf = np.log1p((n_docs - df + 0.5) / (df + 0.5)).astype(np.float32)
        avgdl = float(lengths.mean()) if n_docs else 0.0
        # Precompute the per-(doc, term) BM25 weight so a query is one sparse column sum.
        norm = self.k1 * (1 - self.b + self.b * lengths / max(avgdl, 1e-9))
        tf = tf.tocoo()
        weights = tf.data * (self.k1 + 1) / (tf.data + norm[tf.row])
        self.weights = sparse.csc_matrix((weights * self.idf[tf.col], (tf.row, tf.col)), shape=tf.shape)

    def scores(self, query: str) -> np.ndarray:
        cols = [self.vocab[t] for t in tokenize(query) if t in self.vocab]
        if not cols:
            return np.zeros(self.weights.shape[0], dtype=np.float32)
        return np.asarray(self.weights[:, cols].sum(axis=1)).ravel()
