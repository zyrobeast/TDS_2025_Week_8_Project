# ---------- Base Image ----------
FROM python:3.12-slim AS base

# ---------- System dependencies for Playwright ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    git \
    curl \
    unzip \
    xvfb \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcb1 \
    libxext6 \
    libxfixes3 \
    libgbm1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ---------- Set working directory ----------
WORKDIR /app

# ---------- Copy application code ----------
COPY . .

# ---------- Install `uv` and Python dependencies globally ----------
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir uv

# ---------- Use `uv` to create a virtual environment and sync dependencies ----------
RUN uv venv venv  # Create the virtual environment using `uv`
RUN . venv/bin/activate && uv sync

# ---------- Install Playwright and browsers within the virtual environment ----------
RUN . venv/bin/activate && pip install --no-cache-dir playwright
RUN . venv/bin/activate && playwright install --with-deps chromium

# ---------- Environment variables ----------
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ---------- Expose port ----------
EXPOSE 7860

# ---------- Run agent-quiz.py within the virtual environment ----------
CMD ["uv", "run", "agent-quiz.py"]
