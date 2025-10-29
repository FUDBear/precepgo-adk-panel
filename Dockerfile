FROM python:3.11-slim

# System deps (optional: add build tools if your ADK needs them)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PORT=8080
# USE_FIRESTORE=false lets you run without GCP during local tests
ENV USE_FIRESTORE=false
# EVALS_COLLECTION=evaluations  # set via Cloud Run env if you need

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
