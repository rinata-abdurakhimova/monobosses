FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/services/api
COPY services/api /app/services/api
# Editable install keeps the adjacent prompt files in the deployed source tree.
RUN pip install --no-cache-dir -e . && mkdir -p /data
EXPOSE 8000
# One process until R2 supplies persistent storage and coordinated workers.
# IPv6 wildcard supports Railway's private network; verify its health check on deploy.
CMD ["sh", "-c", "exec python -m uvicorn vic.main:app --host :: --port ${PORT:-8000} --workers 1"]
