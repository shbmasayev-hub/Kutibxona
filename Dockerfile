FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system bot \
    && useradd --system --gid bot --home-dir /app bot \
    && mkdir -p /app/books/uploads /app/books/audio \
    && chown -R bot:bot /app

COPY --chown=bot:bot main.py local_library.py audio_library.py drive_library.py ./
COPY --chown=bot:bot resources /app/resources

USER bot
VOLUME ["/app/books"]

CMD ["python", "main.py"]
