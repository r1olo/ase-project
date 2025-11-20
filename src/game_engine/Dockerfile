# Multi-stage Dockerfile for Game Engine Microservice

# ============== BUILD STAGE ==============
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt


# ============== PRODUCTION STAGE ==============
FROM python:3.11-slim

WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 gameuser && \
    chown -R gameuser:gameuser /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/gameuser/.local

# Copy application code
COPY --chown=gameuser:gameuser . .

# Switch to non-root user
USER gameuser

# Add local bin to PATH
ENV PATH=/home/gameuser/.local/bin:$PATH

# Environment variables
ENV FLASK_APP=game_engine
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "-m", "game_engine"]
