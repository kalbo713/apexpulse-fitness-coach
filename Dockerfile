# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    GOOGLE_GENAI_USE_VERTEXAI=true \
    GOOGLE_CLOUD_PROJECT=project-281bf799-969f-49aa-917 \
    GOOGLE_CLOUD_LOCATION=us-central1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application, garmin sync, tokens, and frontend code
COPY garmin_sync.py ./
COPY .garmin_tokens ./.garmin_tokens
COPY app/ ./app/
COPY frontend/ ./frontend/

# Expose container port
EXPOSE 8080

# Run FastAPI frontend + Agent backend with uvicorn
CMD ["uvicorn", "frontend.main:app", "--host", "0.0.0.0", "--port", "8080"]
