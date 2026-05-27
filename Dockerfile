FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .


FROM python:3.12-slim

RUN addgroup --system warden && adduser --system --ingroup warden warden

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

RUN mkdir -p /data && chown warden:warden /data

USER warden

ENV DATABASE_URL="sqlite+aiosqlite:////data/warden.db"

EXPOSE 8000

CMD ["uvicorn", "warden.main:app", "--host", "0.0.0.0", "--port", "8000"]
