# CPU image (the GPU path runs natively; see README). Models download to the /models volume.
FROM python:3.11-slim
RUN useradd --system --uid 10001 models && mkdir /models && chown 10001 /models
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV MODEL_DEVICE=cpu HF_HOME=/models
USER 10001
EXPOSE 8090
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
