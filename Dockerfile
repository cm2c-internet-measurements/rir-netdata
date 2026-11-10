# rir-netdata container image: runs `rir-netdata get` and writes the db to /data/var.
#
#   docker build -t rir-netdata .
#   docker run --rm -v "$PWD/var:/data/var" -v "$PWD/tmp:/data/tmp" rir-netdata

FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so they stay cached when only the source changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-slim
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH
# Relative defaults resolve here: output in /data/var, download cache in /data/tmp.
WORKDIR /data
ENTRYPOINT ["rir-netdata"]
CMD ["get"]
