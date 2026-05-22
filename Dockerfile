FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e '.[dev]'

COPY backend/ backend/
COPY scripts/ scripts/
COPY tests/ tests/
COPY run.py .

EXPOSE 8100

CMD ["python", "run.py", "--no-browser"]
