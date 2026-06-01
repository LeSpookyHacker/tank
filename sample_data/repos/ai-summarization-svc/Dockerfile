FROM python:3.11-slim@sha256:0000000000000000000000000000000000000000000000000000000000000000

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY src/ ./src/
ENV PYTHONPATH=/app/src
# Cloud Run injects PORT; Workload Identity provides GCP creds (no key files).
EXPOSE 8080
USER 10001
CMD ["uvicorn", "ai_summarization_svc.main:app", "--host", "0.0.0.0", "--port", "8080"]
