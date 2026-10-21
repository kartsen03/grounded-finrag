# rag-service API. Data (downloaded corpus, processed chunks) and results are mounted from the
# repository at /repo, which FINRAG_REPO_ROOT points to; nothing from FinanceBench is baked in.
FROM python:3.11-slim
RUN useradd --system --uid 10001 rag
WORKDIR /app
COPY pyproject.toml .
COPY src src
RUN pip install --no-cache-dir .
ENV FINRAG_REPO_ROOT=/repo HF_HOME=/tmp/hf
USER 10001
EXPOSE 8000
CMD ["uvicorn", "finrag.api:app", "--host", "0.0.0.0", "--port", "8000"]
