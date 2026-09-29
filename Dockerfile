# MOON Docker image
# Build: docker build -t moon-ai .
# Run:   docker run -d --name moon -p 8777:8777 moon-ai

FROM python:3.11-slim

WORKDIR /app

# --- system deps ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    espeak \
    sox \
    libespeak-dev \
    portaudio19-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# --- Python deps ---
COPY requirements.txt requirements-optional.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-optional.txt \
    || true \
    && pip install --no-cache-dir -e . \
    || true

# --- MOON source ---
COPY . .

# --- voice assets ---
RUN python install_moon.py --no-venv --no-service 2>/dev/null || true

# --- non-root user ---
RUN useradd -m -s /bin/bash moonuser \
    && chown -R moonuser:moonuser /app
USER moonuser

# --- env ---
ENV MOON_PORT=8777
ENV PYTHONUNBUFFERED=1

EXPOSE 8777

# --- healthcheck ---
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://127.0.0.1:8777/api/health || exit 1

# --- entrypoint ---
CMD ["./.venv/bin/python", "main.py", "terminal"]
