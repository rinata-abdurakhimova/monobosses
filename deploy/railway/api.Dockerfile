FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/services/api
COPY services/api /app/services/api
# Editable install keeps the adjacent prompt files in the deployed source tree.
RUN pip install --no-cache-dir -e ".[anthropic]" && mkdir -p /data
EXPOSE 8000
# One process until R2 supplies persistent storage and coordinated workers.
# Accept IPv4 health checks and IPv6 private-network traffic on the same port.
CMD ["python", "scripts/serve.py"]
