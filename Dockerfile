FROM python:3.14-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .
COPY . .
RUN useradd -u 10001 -m app && mkdir -p /app/data && chown -R app /app/data
USER app
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
