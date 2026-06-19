FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    gcc \
    g++ \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

RUN mkdir -p /app/backend

# Copy requirements file
COPY requirement.txt /app/backend

# Install Python dependencies with increased timeout and retries
RUN cd /app/backend && pip install --no-cache-dir --upgrade pip --default-timeout=100 && \
    pip install --no-cache-dir --default-timeout=100 --retries 5 -r requirement.txt

# Copy project files
COPY . /app/backend

# Create logs directory
RUN mkdir -p /app/backend/logs

# Create directory for static files
RUN mkdir -p /var/www/shikshalokam/static

# Expose port (default Django development server port, adjust as needed)
EXPOSE 9000

WORKDIR /app/backend

# Default command - can be overridden in docker-compose or run command
# For production, you might want to use daphne or gunicorn
CMD ["uvicorn", "shikshalokam_mohini.asgi:application", "--host", "0.0.0.0", "--port", "9000", "--workers", "4", "--ws-ping-interval", "30", "--ws-ping-timeout", "600"]