FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/agrion

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 agrion
COPY --chown=agrion:agrion app/ app/
USER agrion
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "24", "--timeout", "360", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
