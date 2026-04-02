FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY shared/ /shared/
RUN pip install --no-cache-dir -e /shared/
COPY backend/ .
RUN pip install --no-cache-dir -e .
RUN mkdir -p templates static
EXPOSE 8000 9000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
