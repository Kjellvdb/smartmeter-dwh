FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg ca-certificates unixodbc-dev libatomic1 \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
 && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml requirements.txt requirements-dev.txt ./
COPY src ./src
COPY scripts ./scripts
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements-dev.txt && pip install --no-cache-dir --root-user-action=ignore -e . --no-deps && playwright install --with-deps chromium
