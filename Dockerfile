FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY reeflog ./reeflog

# Only /data is written; the image itself runs read-only.
RUN useradd --uid 1000 --user-group --home-dir /app --no-log-init reeflog \
    && mkdir /data \
    && chown -R reeflog:reeflog /app /data
USER 1000:1000

VOLUME ["/data"]
EXPOSE 8080

CMD ["python", "-m", "reeflog"]
