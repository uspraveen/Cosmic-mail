FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --system --create-home --home-dir /home/cosmic cosmic

COPY --chown=cosmic:cosmic pyproject.toml README.md /app/
COPY --chown=cosmic:cosmic cosmic_mail /app/cosmic_mail
COPY --chown=cosmic:cosmic cosmic_mail/web/static /app/cosmic_mail/web/static

RUN chmod -R a+rX /app/cosmic_mail /app/README.md /app/pyproject.toml && \
    test -d /app/cosmic_mail/web/static && \
    test -f /app/cosmic_mail/web/static/index.html && \
    test -f /app/cosmic_mail/web/static/app.css && \
    test -f /app/cosmic_mail/web/static/app.js && \
    test -f /app/cosmic_mail/web/static/api.js && \
    test -f /app/cosmic_mail/web/static/state.js && \
    test -f /app/cosmic_mail/web/static/templates.js

RUN pip install --upgrade pip && \
    pip install .

USER cosmic

EXPOSE 8080

CMD ["uvicorn", "cosmic_mail.main:app", "--host", "0.0.0.0", "--port", "8080"]
