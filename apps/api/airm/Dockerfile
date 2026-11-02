# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

FROM python:3.14

WORKDIR /code

# Install uv and uvicorn globally
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir uv uvicorn

COPY apps/api/airm/pyproject.toml apps/api/airm/uv.lock /code/apps/api/airm/
COPY apps/api/api_common /code/apps/api/api_common

# Copy application code
COPY apps/api/airm/app /code/apps/api/airm/app
COPY apps/api/airm/migrations /code/migrations

# Create non-root user and set permissions
RUN useradd -m -u 1000 apiserver && \
    chown -R 1000:1000 /code
USER apiserver

# Install dependencies with uv as non-root user
WORKDIR /code/apps/api/airm
RUN uv sync --locked --no-dev

# Run the application
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
