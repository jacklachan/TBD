# Hugging Face Spaces, Docker SDK. Spaces expects the app on port 7860.
FROM python:3.12-slim

# Spaces runs as uid 1000 and only $HOME and /tmp are writable.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

EXPOSE 7860

# One worker, deliberately. Run state lives in memory in AppState, so a second
# worker would answer /runs/{id} for runs it has never seen and the UI would
# poll forever. Scale by making runs durable first, not by adding workers.
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
