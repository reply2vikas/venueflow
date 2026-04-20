FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (Docker caching optimisation)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run provides PORT env variable — default to 8080
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

# Single worker — most reliable for Cloud Run free tier
# Use --timeout 120 to give startup enough time
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--timeout-keep-alive", "120"]
