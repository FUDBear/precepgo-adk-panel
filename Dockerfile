FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (all Python files)
COPY *.py ./

# Copy agents directory
COPY agents/ ./agents/

# Copy vectordb directory (for vector search tools)
COPY vectordb/ ./vectordb/

# Copy data files needed at runtime (create directory first)
RUN mkdir -p data
COPY data/cases.json data/patient_templates.json data/concepts.json data/students.json data/comments_example.json data/task-time-benchmarks.json data/sites.json data/standards.json data/

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8080

# Run the application (use shell form to support $PORT variable)
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
