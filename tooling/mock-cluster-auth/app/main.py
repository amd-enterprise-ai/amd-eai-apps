# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os
import sys

from fastapi import FastAPI
from loguru import logger

from .routes import router

# Configure logging
logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="Mock Cluster Auth Service",
    description="Mock implementation of cluster-auth API for local development",
    version="1.0.0",
)

app.include_router(router)
