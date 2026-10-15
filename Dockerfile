FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/app/data PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
COPY app ./app
COPY data/profiles.json ./data/profiles.json
RUN python -m compileall -q app && python -c "from app.main import app; print(app.version)"
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --proxy-headers"]
