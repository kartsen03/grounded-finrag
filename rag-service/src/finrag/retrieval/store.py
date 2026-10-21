"""pgvector storage for chunk embeddings: one table per chunking strategy, HNSW index.

Embeddings are L2-normalized, so inner product equals cosine similarity; the index uses
vector_ip_ops and queries order by the <#> (negative inner product) operator.
Filtered searches (metadata routing) use pgvector's iterative HNSW scan so a restrictive
WHERE clause does not starve the result list; exact=True disables the index to get the
true nearest neighbours, which is how HNSW recall is checked.
"""

from __future__ import annotations

import os

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

DEFAULT_DSN = "postgresql://finrag:finrag-dev@127.0.0.1:5432/finrag"
TABLES = {"fixed": "chunks_fixed", "structure": "chunks_structure"}
EF_SEARCH = 100
COLUMNS = ["chunk_id", "doc_name", "company", "doc_type", "fiscal_year", "fiscal_quarter", "page_idx", "pages",
           "section", "subsection", "has_table", "n_tokens", "text", "embed_text"]


def _table(strategy: str) -> str:
    return TABLES[strategy]  # whitelist: table names are never interpolated from user input


def _vector_literal(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in vec.tolist()) + "]"


class VectorStore:
    def __init__(self, dsn: str | None = None):
        self.conn = psycopg.connect(dsn or os.environ.get("FINRAG_PG_DSN", DEFAULT_DSN), autocommit=True)
        register_vector(self.conn)

    def reset(self, strategy: str, dim: int) -> None:
        t = _table(strategy)
        with self.conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {t}")
            cur.execute(f"""
                CREATE TABLE {t} (
                    chunk_id text PRIMARY KEY, doc_name text NOT NULL, company text NOT NULL,
                    doc_type text NOT NULL, fiscal_year int NOT NULL, fiscal_quarter int, page_idx int NOT NULL,
                    pages int[] NOT NULL, section text, subsection text, has_table boolean NOT NULL,
                    n_tokens int NOT NULL, text text NOT NULL, embed_text text NOT NULL,
                    embedding vector({int(dim)}) NOT NULL)""")

    def insert(self, strategy: str, chunks: list[dict], vectors: np.ndarray) -> None:
        t = _table(strategy)
        with self.conn.cursor() as cur, cur.copy(f"COPY {t} ({', '.join(COLUMNS)}, embedding) FROM STDIN") as copy:
            for chunk, vec in zip(chunks, vectors, strict=True):
                copy.write_row([chunk[c] for c in COLUMNS] + [_vector_literal(vec)])

    def create_indexes(self, strategy: str) -> None:
        t = _table(strategy)
        with self.conn.cursor() as cur:
            cur.execute(f"CREATE INDEX {t}_hnsw ON {t} USING hnsw (embedding vector_ip_ops) "
                        "WITH (m = 16, ef_construction = 64)")
            cur.execute(f"CREATE INDEX {t}_doc ON {t} (doc_name)")
            cur.execute(f"ANALYZE {t}")

    def count(self, strategy: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {_table(strategy)}")
            return cur.fetchone()[0]

    def search(self, strategy: str, query: np.ndarray, k: int, doc_names: frozenset[str] | None = None,
               exact: bool = False) -> list[tuple[str, float]]:
        t = _table(strategy)
        where = "WHERE doc_name = ANY(%(docs)s)" if doc_names is not None else ""
        sql = (f"SELECT chunk_id, -(embedding <#> %(q)s) AS score FROM {t} {where} "
               f"ORDER BY embedding <#> %(q)s LIMIT %(k)s")
        params = {"q": query.astype(np.float32), "k": k, "docs": sorted(doc_names) if doc_names else None}
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(f"SET LOCAL hnsw.ef_search = {EF_SEARCH}")
            cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            if exact:
                cur.execute("SET LOCAL enable_indexscan = off")
            cur.execute(sql, params)
            rows = cur.fetchall()
        # relaxed_order can return neighbours slightly out of order; restore exact order.
        return sorted(((cid, float(s)) for cid, s in rows), key=lambda r: (-r[1], r[0]))

    def close(self) -> None:
        self.conn.close()
