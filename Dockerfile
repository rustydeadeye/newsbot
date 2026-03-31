FROM python:3.12-slim

WORKDIR /app

# Install system deps needed by psycopg binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy project definition first so pip install is cached separately from source
COPY pyproject.toml ./
COPY app/ ./app/

# Install the project and its dependencies
RUN pip install --no-cache-dir ".[standard]" || pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
