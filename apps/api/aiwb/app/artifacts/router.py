# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from textwrap import dedent

from fastapi import APIRouter, Body, Depends, Path, Query, Response, status

from api_common.auth.security import get_user_email
from api_common.schemas import QueryParam

from ..common_responses import PROJECT_ACCESS_RESPONSES, UNHEALTHY_PLATFORM_RESPONSES
from ..dispatch.kube_client import KubernetesClient, get_kube_client
from ..minio import MinioClient, get_minio_client, get_minio_client_optional, get_minio_external_client
from ..projects.security import ensure_access_to_project
from .schemas import (
    ARTIFACT_NAME_MAX_LENGTH,
    ARTIFACT_NAME_PATTERN,
    MAX_ARTIFACT_FILES,
    MAX_ARTIFACT_LISTING_ENTRIES,
    ArtifactDownloadResponse,
    ArtifactResponse,
    ArtifactsList,
    CreateArtifactRequest,
    CreateArtifactResponse,
    ListArtifactsQuery,
)
from .service import (
    create_adapter_artifact,
    delete_project_adapter_artifact,
    download_project_artifact,
    get_project_adapter_artifact,
    list_project_adapter_artifacts,
)

router = APIRouter(tags=["Artifacts"])


@router.post(
    "/projects/{project}/artifacts",
    response_model=CreateArtifactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an adapter",
    description=dedent(f"""
        Create an adapter artifact in the project, from one of two sources:

        - **`upload`** — AIWB allocates an S3 prefix and returns a presigned PUT URL per file in
          `files[]`. Upload the bytes there; the adapter reaches `Ready` once the required PEFT
          files (`adapter_config.json`, `adapter_model.safetensors`) are present. At most
          {MAX_ARTIFACT_FILES} files of your own may be declared, matching what one download covers;
          an `adapter-manifest.yaml` at the prefix root is not one of them — AIWB writes that key
          itself, so a listed copy is dropped rather than signed. That is what lets the file
          list a download returns be posted straight back here as a new upload.
        - **`s3`** — point at a prefix already holding those files. AIWB verifies both are
          reachable and returns no upload URLs. This is also how weights the project already holds
          are registered: post the prefix they sit at as an `s3` source.

        `compatibleWith` declares the canonical base-model IDs the adapter may attach to. Nothing
        resolves or owns them, so the adapter outlives every base it names and is `Ready` with none
        of them in the cluster; a mismatch surfaces at deploy time. Immutable once created.

        An `upload` source needs an object-storage endpoint that resolves from outside the cluster.
        Where the install has none, creation is refused rather than answered with URLs the client
        could never reach; registering weights already in storage with an `s3` source still works.

        The response is the list endpoint's shape plus `uploads`, so a client can drop it straight
        into the collection it is already rendering.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        400: {
            "description": (
                "The request is invalid: malformed S3 URI, required LoRA files missing at the source, or "
                "declared `compatibleWith` conflicting with the manifest already beside those files."
            )
        },
        409: {"description": "An artifact with the generated name already exists."},
        502: {"description": "Kubernetes or object-storage failure while creating the artifact."},
        **UNHEALTHY_PLATFORM_RESPONSES,
    },
)
async def create_artifact_endpoint(
    project: str = Depends(ensure_access_to_project),
    request: CreateArtifactRequest = Body(...),
    kube_client: KubernetesClient = Depends(get_kube_client),
    minio_client: MinioClient = Depends(get_minio_client),
    minio_external_client: MinioClient = Depends(get_minio_external_client),
    user_email: str = Depends(get_user_email),
) -> CreateArtifactResponse:
    return await create_adapter_artifact(
        kube_client=kube_client,
        minio_client=minio_client,
        minio_external_client=minio_external_client,
        namespace=project,
        request=request,
        submitter=user_email,
    )


@router.get(
    "/projects/{project}/artifacts",
    response_model=ArtifactsList,
    status_code=status.HTTP_200_OK,
    summary="List adapters",
    description=dedent("""
        List the project's LoRA adapters, newest first.

        Every adapter backed by an AIMArtifact appears here, whether onboarded through this API or
        produced by the fine-tuning engine. Weight files sitting in the project's storage that no
        AIMArtifact claims are not adapters and are not listed — register them first by POSTing
        their prefix as an `s3` source.

        Every item has two halves, one per source of truth. `storage` is where the files live
        (`uri`) and whether the ones the adapter needs are present (`readiness`). `artifact` is the
        AIMArtifact resource itself, passed through verbatim.

        The base models an adapter may attach to are read off `artifact.spec.compatibleWith`, a
        list of canonical model IDs checked only when a deployment resolves a concrete base.

        `artifact.metadata.name` is what clients should key rows on, and is the path segment for
        the by-name GET and DELETE.

        `?type=adapter` filters on `AIMArtifact.spec.type`. Adapters are the only type this
        collection exposes today, so the filter is a no-op until it grows another.

        `?readiness=Ready` filters on whether the artifact's files are all present. It reads
        storage for the whole collection rather than just the returned page, since the verdict
        decides which rows a page contains.

        `?servableBy=` reports, per row, whether that deployment can load the adapter, and is a
        404 when no such deployment exists in the project.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "Project or namespace not found, or `servableBy` names no deployment in the project."},
    },
)
async def list_artifacts_endpoint(
    query: QueryParam[ListArtifactsQuery],
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
    minio_client: MinioClient | None = Depends(get_minio_client_optional),
) -> ArtifactsList:
    return await list_project_adapter_artifacts(
        kube_client=kube_client,
        minio_client=minio_client,
        namespace=project,
        query=query,
    )


@router.get(
    "/projects/{project}/artifacts/{name}",
    response_model=ArtifactResponse,
    status_code=status.HTTP_200_OK,
    summary="Get an adapter",
    description="Return a single adapter by name, in the same shape the list endpoint returns.",
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "No artifact with that name exists in the project."},
    },
)
async def get_artifact_endpoint(
    name: str = Path(
        ...,
        pattern=ARTIFACT_NAME_PATTERN,
        max_length=ARTIFACT_NAME_MAX_LENGTH,
        description="AIMArtifact CR resource name",
    ),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
    minio_client: MinioClient | None = Depends(get_minio_client_optional),
) -> ArtifactResponse:
    return await get_project_adapter_artifact(
        kube_client=kube_client,
        minio_client=minio_client,
        namespace=project,
        name=name,
    )


@router.get(
    "/projects/{project}/artifacts/{name}/download",
    response_model=ArtifactDownloadResponse,
    status_code=status.HTTP_200_OK,
    summary="Download an artifact",
    description=dedent(f"""
        Return a set of time-limited direct links to the artifact's files — not the bytes. Each link
        is signed for object storage, so the transfer runs between the client and storage rather
        than through this API.

        Every file stored under the artifact's prefix is included, each keyed on its path relative
        to that prefix; empty directory markers are not, as a download rebuilds directories from
        the files under them. A nested file keeps the path it is stored at, so writing every entry
        in `files` to its own path reproduces the prefix's files as they stand.

        One download covers at most {MAX_ARTIFACT_FILES} of the artifact's own files — the adapter
        manifest AIWB writes beside them is served on top of that rather than counted against it —
        and reads at most {MAX_ARTIFACT_LISTING_ENTRIES} entries at the prefix to find them. A
        prefix over either is refused rather than served in part. The links expire at `expiresAt` — request the download
        again for a fresh set.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "No artifact with that name exists in the project."},
        409: {
            "description": (
                "The artifact cannot be handed out as it stands: its recorded storage location does "
                "not parse or is outside this project's storage, its prefix holds an object whose "
                "path escapes that prefix or whose key names a directory yet carries bytes, its "
                "prefix holds more files than one download covers or more entries than one download "
                "reads, or — for an adapter — its PEFT weights are not present there."
            )
        },
        502: {
            "description": (
                "Kubernetes or object-storage failure while assembling the download — reading the "
                "resource, listing the artifact's files, or signing the links."
            )
        },
        **UNHEALTHY_PLATFORM_RESPONSES,
    },
)
async def download_artifact_endpoint(
    response: Response,
    name: str = Path(
        ...,
        pattern=ARTIFACT_NAME_PATTERN,
        max_length=ARTIFACT_NAME_MAX_LENGTH,
        description="AIMArtifact CR resource name",
    ),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
    minio_client: MinioClient = Depends(get_minio_client),
    minio_external_client: MinioClient = Depends(get_minio_external_client),
) -> ArtifactDownloadResponse:
    # Each link carries its own credentials and stays usable until it expires, so a cache holding
    # the body would keep handing out working links to whoever reaches it, including after the
    # caller's access to the artifact is taken away.
    response.headers["Cache-Control"] = "no-store"
    return await download_project_artifact(
        kube_client=kube_client,
        minio_client=minio_client,
        minio_external_client=minio_external_client,
        namespace=project,
        name=name,
    )


@router.delete(
    "/projects/{project}/artifacts/{name}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Delete an adapter",
    description=dedent("""
        Delete an adapter artifact from the project.

        A delete is refused while any AIMService in the project still references the artifact as
        an adapter — removing live-referenced weights does not disturb a running deployment, but
        breaks it the next time it reloads them, on restart or redeploy.

        Weights uploaded through this API are removed with the adapter, reclaiming the project
        storage they occupied. An adapter produced by a fine-tuning job takes its whole run folder
        with it: the adapter weights and the run-level files beside them. An adapter onboarded
        from a prefix the caller already owned is deregistered without touching those files, and
        storage still claimed by another adapter is left in place.

        Pass `force=true` to delete anyway. It overrides only the check for adapters in use by a
        running service; the referencing services are left running and unmodified, so a replica
        keeps serving the adapter it already loaded and fails to reload it on restart. To remove
        the adapter cleanly instead, detach it from those services first.

        Storage cleanup must succeed either way: where weights are the platform's to remove and
        removing them fails, the adapter is not deleted, so a failed cleanup never orphans them.
        The cases above that leave files in place skip cleanup deliberately, not on failure.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        202: {"description": "Delete accepted; the AIMArtifact CR is being removed."},
        204: {"description": "No artifact with that name exists; nothing to delete."},
        409: {
            "description": (
                "One or more AIMServices in the project still reference this artifact. "
                "The response names the blocking services; pass force=true to override."
            )
        },
        502: {
            "description": (
                "Kubernetes API failure while reading or deleting the AIMArtifact CR, or an object-storage "
                "failure while reclaiming the adapter's weights."
            )
        },
    },
)
async def delete_artifact_endpoint(
    name: str = Path(
        ...,
        pattern=ARTIFACT_NAME_PATTERN,
        max_length=ARTIFACT_NAME_MAX_LENGTH,
        description="AIMArtifact CR resource name",
    ),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
    minio_client: MinioClient | None = Depends(get_minio_client_optional),
    force: bool = Query(False, description="Delete even if AIMServices still reference the artifact"),
) -> Response:
    deleted = await delete_project_adapter_artifact(
        kube_client=kube_client,
        minio_client=minio_client,
        namespace=project,
        name=name,
        force=force,
    )
    return Response(status_code=status.HTTP_202_ACCEPTED if deleted else status.HTTP_204_NO_CONTENT)
