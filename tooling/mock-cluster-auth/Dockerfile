# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

FROM astral/uv:python3.13-bookworm AS uv

WORKDIR /app

COPY pyproject.toml .
RUN uv pip install --system .

COPY app/ ./app/

EXPOSE 48012

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "48012"]
