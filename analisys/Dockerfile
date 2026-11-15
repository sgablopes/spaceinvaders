FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /service
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY *.xlsx *.zip ./
COPY data/faostat.sqlite3.gz data/faostat.manifest.json ./data/
RUN groupadd --gid 10001 agrion && useradd --uid 10001 --gid agrion agrion \
    && mkdir .runtime && chown agrion:agrion .runtime
USER agrion
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
