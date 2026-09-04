FROM golang:1.24-bookworm AS alpaca-cli
RUN go install github.com/alpacahq/cli/cmd/alpaca@v0.0.13

FROM python:3.13-slim

WORKDIR /app
COPY --from=alpaca-cli /go/bin/alpaca /usr/local/bin/alpaca
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip python -c "import subprocess,tomllib; p=tomllib.load(open('pyproject.toml','rb'))['project']; subprocess.check_call(['pip','install',*p['dependencies']])"
RUN --mount=type=cache,target=/root/.cache/pip python -c "import subprocess,tomllib; p=tomllib.load(open('pyproject.toml','rb'))['project']; subprocess.check_call(['pip','install',*p['optional-dependencies']['alpaca']])"
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
