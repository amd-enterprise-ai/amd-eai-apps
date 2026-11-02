# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Reclaims AIWB-owned data whose project no longer exists."""

import argparse
import asyncio
import sys

from api_common import database
from api_common.database import dispose_db, init_db

from ..dispatch.config import load_k8s_config
from ..dispatch.kube_client import init_kube_client
from ..minio import init_minio_client
from ..openbao.client import init_openbao_client
from ..projects.gateway import get_namespaces
from .reap import reclaim


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be reclaimed and delete nothing",
    )
    return parser.parse_args()


async def async_main(dry_run: bool) -> None:
    minio_client = init_minio_client()
    if minio_client is None:
        sys.exit("Object storage is not configured; cannot reclaim orphaned data.")

    init_db()
    if database.session_maker is None:
        sys.exit("Database was not initialised.")

    await load_k8s_config()
    kube_client = await init_kube_client()
    # Not needed to preview, since nothing is revoked; required to act.
    openbao_client = init_openbao_client()

    try:
        if openbao_client is None and not dry_run:
            sys.exit("Refusing to reclaim anything: Object storage credentials cannot be revoked without OpenBao")

        live_namespaces = await get_namespaces(kube_client)
        if not live_namespaces:
            sys.exit(
                "Refusing to reclaim anything: No namespaces are visible; refusing to treat the estate as abandoned"
            )

        async with database.session_maker() as session:
            await reclaim(session, kube_client, minio_client, openbao_client, live_namespaces, dry_run=dry_run)
    finally:
        if openbao_client is not None:
            await openbao_client.close()
        await kube_client.close()
        await dispose_db()


def main() -> None:
    asyncio.run(async_main(dry_run=_parse_args().dry_run))


if __name__ == "__main__":
    main()
