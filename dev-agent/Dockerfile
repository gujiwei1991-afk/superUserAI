FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY dev-agent/ .
RUN pip install --no-cache-dir -e .
RUN mkdir -p /workspace
ENV WORKSPACE_DIR=/workspace
CMD ["python", "-m", "app.main"]
