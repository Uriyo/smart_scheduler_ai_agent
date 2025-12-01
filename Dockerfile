FROM python:3.11-slim

# Install UV for deterministic dependency management
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency manifests first for better build caching
COPY pyproject.toml uv.lock ./

# Sync (install) dependencies in the image
RUN uv sync --no-cache

# Copy the rest of the project
COPY . .

# Download required model files (Silero VAD, Turn Detector, etc.)
RUN uv run python scheduler_agent.py download-files

# Default command runs the basic LiveKit agent
CMD ["uv", "run", "python", "scheduler_agent.py", "dev"]

