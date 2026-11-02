# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level custom-model preview, onboard, list, and detail testing keywords.
...                 Provides BDD-friendly keywords for exercising
...                 POST /v1/projects/{project}/models/preview,
...                 POST /v1/projects/{project}/models/onboard,
...                 GET /v1/projects/{project}/models, and
...                 GET /v1/projects/{project}/models/{model_name}.
Resource            api/custom_models.resource
Resource            api/models.resource
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource
Resource            aiwb_secrets.resource
Resource            aiwb_storages.resource
Resource            aiwb_common.resource
Resource            aiwb_aims.resource
Resource            api/cluster.resource
Library             Collections
Library             String
Library             AIMModelHelper
Library             Process
Library             TestPrefix


*** Variables ***
# A small ungated public repo used as the default source across the suite.
# Keep this model inference-compatible on cluster accelerators so deploy tests
# exercise runtime behavior instead of failing on backend incompatibility.
${CUSTOM_MODELS_PUBLIC_REPO}         Qwen/Qwen2.5-0.5B-Instruct
${CUSTOM_MODELS_GATED_REPO}          meta-llama/Llama-3.2-1B
# Private repo whose metadata Hub gates behind auth: requests without valid access
# get 401 (which the API surfaces as 403). A gated repo like the one above exposes
# metadata publicly, so it cannot exercise the invalid-token credential path.
${CUSTOM_MODELS_PRIVATE_REPO}        hf-internal-testing/private-model-for-testing
${CUSTOM_MODELS_MISSING_REPO}        aiwb-e2e-nonexistent-org-xyz/no-such-model-zzzzzz
${CUSTOM_MODELS_ONBOARD_IMAGE}       docker.io/amdenterpriseai/aim-base:0.13.1
${CUSTOM_MODELS_E2E_MINIO_STORAGE}   custom-model-e2e-minio


*** Keywords ***
Use discovered cluster onboarding image for custom model tests
    [Documentation]    Overrides the default onboard image with a discovered cluster image
    ...    (repository + tag) so deploy tests pull a runtime known to this environment.
    ${catalog_response}=    List aim image families    expected_status=200
    ${catalog}=    Get From Dictionary    ${catalog_response.json()}    data
    ${accel_response}=    List cluster accelerators    expected_status=200
    ${accelerators}=    Get From Dictionary    ${accel_response.json()}    data
    ${onboard_family}=    Resolve Onboard Base Image Family From Cluster Discovery    ${catalog}    ${accelerators}
    Should Not Be Empty    ${onboard_family}
    ...    msg=Could not resolve onboard base image family from cluster discovery
    ${repository}=    Set Variable    ${EMPTY}
    ${tag}=    Set Variable    ${EMPTY}
    FOR    ${family}    IN    @{catalog}
        ${family_id}=    Get From Dictionary    ${family}    familyId
        IF    "${family_id}" == "${onboard_family}"
            ${candidate_repo}=    Get From Dictionary    ${family}    repository    default=${EMPTY}
            ${candidate_tags}=    Get From Dictionary    ${family}    tags    default=@{EMPTY}
            IF    "${candidate_repo}" != "" and len($candidate_tags) > 0
                ${repository}=    Set Variable    ${candidate_repo}
                ${tag}=    Set Variable    ${candidate_tags}[0]
                BREAK
            END
        END
    END
    IF    "${repository}" == ""
        FOR    ${family}    IN    @{catalog}
            ${family_id}=    Get From Dictionary    ${family}    familyId
            ${candidate_repo}=    Get From Dictionary    ${family}    repository    default=${EMPTY}
            ${candidate_tags}=    Get From Dictionary    ${family}    tags    default=@{EMPTY}
            IF    "${family_id}" != "automatic" and "${candidate_repo}" != "" and len($candidate_tags) > 0
                ${repository}=    Set Variable    ${candidate_repo}
                ${tag}=    Set Variable    ${candidate_tags}[0]
                BREAK
            END
        END
    END
    Should Not Be Empty    ${repository}
    ...    msg=No discovered base-image repository with tags found in /cluster/aim-images response
    Should Not Be Empty    ${tag}
    ...    msg=No discovered base-image tag found in /cluster/aim-images response
    ${resolved_image}=    Build Catalog Image Ref    ${repository}    ${tag}
    Set Suite Variable    ${CUSTOM_MODELS_ONBOARD_IMAGE}    ${resolved_image}
    Log    Using discovered custom model onboard image: ${CUSTOM_MODELS_ONBOARD_IMAGE}    INFO

Minio credentials and project S3 storage are ready for custom model tests
    [Documentation]    Assigns minio-credentials-fetcher, waits for the synced
    ...    minio-credentials secret in the project namespace, and registers an
    ...    AIWB S3 storage ConfigMap referenced by s3StorageName in preview/onboard.
    Secret "minio-credentials-fetcher" is assigned to project
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Minio Credentials Secret Exists In Project Namespace    ${namespace}
    A project S3 storage is registered from minio credentials secret

A project S3 storage is registered from minio credentials secret
    [Documentation]    Creates a project-scoped S3 storage via the AIWB storages API,
    ...    backed by the minio-credentials secret synced by minio-credentials-fetcher.
    ...    Reuses an existing storage with the same display name when the project is
    ...    shared across tests in the suite.
    ${project}=    Get Project Namespace
    ${display_name}=    Test Name    ${CUSTOM_MODELS_E2E_MINIO_STORAGE}
    ${existing_name}=    Find AIWB Storage Kubernetes Name By Display Name    ${project}    ${display_name}
    IF    $existing_name is not None
        ${already_tracked}=    Run Keyword And Return Status    List Should Contain Value    ${CREATED_AIWB_STORAGE_NAMES}    ${existing_name}
        IF    not ${already_tracked}
            Append To List    ${CREATED_AIWB_STORAGE_NAMES}    ${existing_name}
        END
        Set Test Variable    ${TEST_S3_STORAGE_K8S_NAME}    ${existing_name}
        Set Suite Variable    ${TEST_S3_STORAGE_K8S_NAME}    ${existing_name}
        RETURN
    END
    &{spec}=    Create Dictionary    bucketUrl=${AIWB_E2E_S3_BUCKET_URL}
    &{body}=    Create Dictionary
    ...    displayName=${display_name}
    ...    type=S3
    ...    secretName=minio-credentials
    ...    spec=${spec}
    ${response}=    Create AIWB Storage    ${project}    ${body}    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    201
    ...    msg=Failed to register project S3 storage: ${response.text}
    VAR    ${created_name}    ${response.json()['name']}
    Append To List    ${CREATED_AIWB_STORAGE_NAMES}    ${created_name}
    Set Test Variable    ${TEST_S3_STORAGE_K8S_NAME}    ${created_name}
    Set Suite Variable    ${TEST_S3_STORAGE_K8S_NAME}    ${created_name}

An S3 storage configuration references the Hugging Face preview secret for mismatch testing
    [Documentation]    Registers an AIWB storage ConfigMap whose backing secret is the
    ...    HuggingFace-labelled preview secret, so preview rejects it before touching S3.
    Should Not Be Empty    ${CUSTOM_MODELS_HF_SECRET_NAME}
    ...    msg=CUSTOM_MODELS_HF_SECRET_NAME not set; create the Hugging Face preview secret first
    ${namespace}=    Get Project Namespace
    ${storage_name}=    Evaluate    f"wb-storage-e2e-hf-mismatch-{uuid.uuid4().hex[:10]}"    modules=uuid
    Register AIWB S3 Storage ConfigMap Referencing Secret
    ...    ${namespace}
    ...    ${storage_name}
    ...    ${CUSTOM_MODELS_HF_SECRET_NAME}
    Append To List    ${CREATED_AIWB_STORAGE_NAMES}    ${storage_name}
    Set Test Variable    ${TEST_S3_STORAGE_K8S_NAME}    ${storage_name}

Project S3 storage name should be set
    Should Not Be Empty    ${TEST_S3_STORAGE_K8S_NAME}
    ...    msg=TEST_S3_STORAGE_K8S_NAME not set; register project S3 storage first

A custom model preview is requested for "${source}"
    ${namespace}=    Get Project Namespace
    ${response}=    Preview Custom Model Source    ${namespace}    ${source}
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    IF    ${response.status_code} == 200
        VAR    ${TEST_PREVIEW_JSON}    ${response.json()}    scope=TEST
    END

A custom model preview is requested for "${source}" with secret "${secret_name}"
    ${namespace}=    Get Project Namespace
    ${response}=    Preview Custom Model Source    ${namespace}    ${source}    hf_token_secret_name=${secret_name}
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    IF    ${response.status_code} == 200
        VAR    ${TEST_PREVIEW_JSON}    ${response.json()}    scope=TEST
    END

A custom S3 model preview is requested for "${source}" with project S3 storage
    Project S3 storage name should be set
    ${namespace}=    Get Project Namespace
    ${response}=    Preview Custom Model Source
    ...    ${namespace}
    ...    ${source}
    ...    source_type=s3
    ...    s3_storage_name=${TEST_S3_STORAGE_K8S_NAME}
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    IF    ${response.status_code} == 200
        VAR    ${TEST_PREVIEW_JSON}    ${response.json()}    scope=TEST
    END

A prepared custom model S3 preview is requested
    ${source}=    Get Variable Value    ${TEST_S3_PREVIEW_SOURCE}    ${None}
    Should Not Be Equal    ${source}    ${None}
    ...    msg=TEST_S3_PREVIEW_SOURCE not set. Prepare an S3 source first.
    A custom S3 model preview is requested for "${source}" with project S3 storage

A custom S3 model preview is requested for "${source}" with secret "${secret_name}"
    [Documentation]    Deprecated alias: ``secret_name`` must be the AIWB storage ConfigMap
    ...    resource name. Prefer ``with project S3 storage`` after registering storage.
    IF    "${secret_name}" == "minio-credentials"
        A custom S3 model preview is requested for "${source}" with project S3 storage
    ELSE
        ${namespace}=    Get Project Namespace
        ${response}=    Preview Custom Model Source
        ...    ${namespace}
        ...    ${source}
        ...    source_type=s3
        ...    s3_storage_name=${secret_name}
        Set Test Variable    ${TEST_RESPONSE}    ${response}
        IF    ${response.status_code} == 200
            VAR    ${TEST_PREVIEW_JSON}    ${response.json()}    scope=TEST
        END
    END

A prepared custom model S3 preview is requested with secret "${secret_name}"
    A prepared custom model S3 preview is requested

A missing S3 source is prepared for custom model preview
    ${namespace}=    Get Project Namespace
    ${suffix}=    Evaluate    uuid.uuid4().hex    modules=uuid
    ${source}=    Set Variable    s3://default-bucket/${namespace}/aiwb-custom-model-preview-e2e/${suffix}/missing
    Set Test Variable    ${TEST_S3_PREVIEW_SOURCE}    ${source}

An empty S3 source is prepared for custom model preview
    ${namespace}=    Get Project Namespace
    ${source}=    Prepare Empty S3 Source For Custom Model Preview    ${namespace}
    Set Test Variable    ${TEST_S3_PREVIEW_SOURCE}    ${source}

A config-only S3 source is prepared for custom model preview
    ${namespace}=    Get Project Namespace
    ${source}=    Prepare Config-Only S3 Source For Custom Model Preview    ${namespace}
    Set Test Variable    ${TEST_S3_PREVIEW_SOURCE}    ${source}

A valid S3 source is prepared for custom model preview
    ${namespace}=    Get Project Namespace
    ${source}=    Prepare Valid S3 Source For Custom Model Preview    ${namespace}
    Set Test Variable    ${TEST_S3_PREVIEW_SOURCE}    ${source}

An object-storage model with no discoverable tags is prepared for custom model preview
    ${namespace}=    Get Project Namespace
    ${source}=    Prepare Untagged S3 Source For Custom Model Preview    ${namespace}
    VAR    ${TEST_S3_PREVIEW_SOURCE}    ${source}    scope=TEST

An object-storage model with author-written tags is prepared for custom model preview
    ${namespace}=    Get Project Namespace
    ${source}=    Prepare Card-Tagged S3 Source For Custom Model Preview    ${namespace}
    VAR    ${TEST_S3_PREVIEW_SOURCE}    ${source}    scope=TEST

An object-storage model derived from "${base_model}" is prepared for custom model preview
    ${namespace}=    Get Project Namespace
    ${source}=    Prepare Base-Model-Derived S3 Source For Custom Model Preview    ${namespace}    ${base_model}
    VAR    ${TEST_S3_PREVIEW_SOURCE}    ${source}    scope=TEST

The previewed custom model is onboarded with image "${image}"
    ${namespace}=    Get Project Namespace
    ${preview_json}=    Get Variable Value    ${TEST_PREVIEW_JSON}    ${None}
    IF    $preview_json is None
        VAR    ${preview_json}    ${TEST_RESPONSE.json()}
    END
    ${response}=    Onboard Custom Model From Preview    ${namespace}    ${preview_json}    ${image}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The previewed custom model is onboarded with image "${image}" and secret "${secret_name}"
    ${namespace}=    Get Project Namespace
    ${preview_json}=    Get Variable Value    ${TEST_PREVIEW_JSON}    ${None}
    IF    $preview_json is None
        VAR    ${preview_json}    ${TEST_RESPONSE.json()}
    END
    ${response}=    Onboard Custom Model From Preview
    ...    ${namespace}
    ...    ${preview_json}
    ...    ${image}
    ...    hf_token_secret_name=${secret_name}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The previewed custom model is onboarded from S3 with image "${image}"
    Project S3 storage name should be set
    ${namespace}=    Get Project Namespace
    ${preview_json}=    Get Variable Value    ${TEST_PREVIEW_JSON}    ${None}
    IF    $preview_json is None
        VAR    ${preview_json}    ${TEST_RESPONSE.json()}
    END
    ${response}=    Onboard Custom Model From Preview
    ...    ${namespace}
    ...    ${preview_json}
    ...    ${image}
    ...    source_type=s3
    ...    s3_storage_name=${TEST_S3_STORAGE_K8S_NAME}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The previewed custom model is onboarded from S3 with image "${image}" and secret "${secret_name}"
    The previewed custom model is onboarded from S3 with image "${image}"

An S3 custom model onboard request is sent for source "${source}" with image "${image}"
    Project S3 storage name should be set
    ${namespace}=    Get Project Namespace
    &{preview_like}=    Create Dictionary
    ...    repoId=${source}
    ...    revision=s3
    ...    sha=s3
    ...    displayName=Onboard S3 Negative
    ...    description=${EMPTY}
    ${response}=    Onboard Custom Model From Preview
    ...    ${namespace}
    ...    ${preview_like}
    ...    ${image}
    ...    source_type=s3
    ...    s3_storage_name=${TEST_S3_STORAGE_K8S_NAME}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

An S3 custom model onboard request is sent for source "${source}" with image "${image}" and secret "${secret_name}"
    An S3 custom model onboard request is sent for source "${source}" with image "${image}"

The previewed custom model is onboarded with image "${image}" and runtime profile overrides
    [Documentation]    Onboard the previewed source with the given image and a
    ...    runtime profile overrides block, supplied as ``key=value`` kwargs
    ...    after the call. The dict is forwarded verbatim as the request's
    ...    ``customProfile`` field and lands on
    ...    ``AIMModel.spec.profiles.overrides``.
    [Arguments]    &{custom_profile}
    ${namespace}=    Get Project Namespace
    ${preview_json}=    Get Variable Value    ${TEST_PREVIEW_JSON}    ${None}
    IF    $preview_json is None
        VAR    ${preview_json}    ${TEST_RESPONSE.json()}
    END
    ${response}=    Onboard Custom Model From Preview
    ...    ${namespace}
    ...    ${preview_json}
    ...    ${image}
    ...    custom_profile=${custom_profile}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The previewed custom model is onboarded with image "${image}" overriding display name to "${display_name}"
    [Documentation]    Onboard the previewed source with the given image but replace the
    ...    preview-seeded display name with a user-supplied value, mirroring the wizard's
    ...    information step where users can change the name before submitting.
    ${namespace}=    Get Project Namespace
    ${preview_json}=    Get Variable Value    ${TEST_PREVIEW_JSON}    ${None}
    IF    $preview_json is None
        VAR    ${preview_json}    ${TEST_RESPONSE.json()}
    END
    &{overridden_preview}=    Copy Dictionary    ${preview_json}
    Set To Dictionary    ${overridden_preview}    displayName=${display_name}
    ${response}=    Onboard Custom Model From Preview    ${namespace}    ${overridden_preview}    ${image}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The previewed custom model is onboarded with image "${image}" and a conflicting profile image "${profile_image}"
    [Documentation]    Onboard with a deliberately disagreeing ``image`` and
    ...    ``customProfile.image``. The API must reject the payload at the
    ...    schema boundary so two image refs never land on the emitted profile.
    ${namespace}=    Get Project Namespace
    ${preview_json}=    Get Variable Value    ${TEST_PREVIEW_JSON}    ${None}
    IF    $preview_json is None
        VAR    ${preview_json}    ${TEST_RESPONSE.json()}
    END
    &{conflicting_profile}=    Create Dictionary    image=${profile_image}
    ${response}=    Onboard Custom Model From Preview
    ...    ${namespace}
    ...    ${preview_json}
    ...    ${image}
    ...    custom_profile=${conflicting_profile}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Custom model preview response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

Custom model preview response should explain the credential failure
    [Documentation]    Asserts the 403 response carries a non-empty, human-readable detail
    ...    message so the UI can prompt the user to verify their credentials rather than
    ...    showing a generic error.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    403
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    detail
    ${detail}=    Get From Dictionary    ${json}    detail
    Should Not Be Empty    ${detail}
    ...    msg=403 response must include a non-empty detail message explaining the credential failure

Custom model onboard response detail should contain "${expected_substring}"
    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    detail
    ${detail}=    Get From Dictionary    ${json}    detail
    Should Contain    ${detail}    ${expected_substring}

Custom model preview response detail should contain "${expected_substring}"
    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    detail
    ${detail}=    Get From Dictionary    ${json}    detail
    Should Contain    ${detail}    ${expected_substring}

Custom model preview response should include warning containing "${expected_substring}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    warnings
    ${warnings}=    Get From Dictionary    ${json}    warnings
    Should Not Be Empty    ${warnings}
    ${warnings_text}=    Catenate    SEPARATOR=\n    @{warnings}
    Should Contain    ${warnings_text}    ${expected_substring}

Custom model preview should offer no tags
    [Documentation]    A source with nothing to infer tags from must still preview
    ...    successfully, offering an empty tag list the user can fill in themselves.
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    tags
    Should Be Empty    ${json}[tags]
    ...    msg=Expected no suggested tags; got '${json}[tags]'

Custom model preview should offer tags
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    tags
    Should Not Be Empty    ${json}[tags]

Custom model preview should suggest the tag "${expected_tag}"
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    tags
    Should Contain    ${json}[tags]    ${expected_tag}
    ...    msg=Expected suggested tags to include '${expected_tag}'; got '${json}[tags]'

Custom model preview should still offer selectable weight files
    [Documentation]    Tag discovery is display metadata, so missing tags must not hide
    ...    the weights offered by preview.
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${weight_files}=    Get From Dictionary    ${json}    weightFiles
    Should Not Be Empty    ${weight_files}
    ...    msg=Preview must still present weight files when no tags were discoverable

Custom model onboard response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

Copy request is sent for custom model "${model_name}"
    [Documentation]    Sends a copy request for a custom model resource name in
    ...    the current project namespace.
    ${namespace}=    Get Project Namespace
    ${response}=    Copy Custom Model    ${namespace}    ${model_name}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The onboarded custom model is copied for source "${source}"
    [Documentation]    Finds the onboarded model resource by canonical repo id and
    ...    sends a copy request for that model.
    ${namespace}=    Get Project Namespace
    ${list_response}=    List Custom Models    ${namespace}    expected_status=200
    ${models}=    Get From Dictionary    ${list_response.json()}    data
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        IF    "${canonical}" == "${source}"
            ${name}=    Get From Dictionary    ${model}[metadata]    name
            ${response}=    Copy Custom Model    ${namespace}    ${name}
            Set Test Variable    ${TEST_RESPONSE}    ${response}
            RETURN
        END
    END
    Fail    No onboarded model with canonical-repo-id '${source}' found; cannot copy

Custom model copy response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

Record listed custom model count for source "${expected_repo_id}"
    [Documentation]    Counts list entries matching the canonical repo id and stores
    ...    the value for later comparison within the test.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${models}=    Get From Dictionary    ${json}    data
    VAR    ${count}    ${0}
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        IF    "${canonical}" == "${expected_repo_id}"
            ${count}=    Evaluate    ${count} + 1
        END
    END
    VAR    ${TEST_CUSTOM_MODEL_MATCH_COUNT}    ${count}    scope=TEST

Listed custom model count for source "${expected_repo_id}" should increase
    [Documentation]    Verifies the list now contains more entries for the same
    ...    canonical repo id than the previously recorded count.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${models}=    Get From Dictionary    ${json}    data
    VAR    ${count}    ${0}
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        IF    "${canonical}" == "${expected_repo_id}"
            ${count}=    Evaluate    ${count} + 1
        END
    END
    Should Be True    ${count} > ${TEST_CUSTOM_MODEL_MATCH_COUNT}
    ...    msg=Expected custom model count for '${expected_repo_id}' to increase (before=${TEST_CUSTOM_MODEL_MATCH_COUNT}, after=${count})

Custom model preview response should describe model "${expected_repo_id}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Should Be Equal    ${json}[repoId]    ${expected_repo_id}
    Dictionary Should Contain Key    ${json}    revision
    Dictionary Should Contain Key    ${json}    sha
    Should Not Be Empty    ${json}[sha]    msg=Preview response must include a pinnable SHA
    Dictionary Should Contain Key    ${json}    weightFiles
    Dictionary Should Contain Key    ${json}    gated
    Dictionary Should Contain Key    ${json}    hfTokenRecommended
    ${weight_files}=    Get From Dictionary    ${json}    weightFiles
    Should Not Be Empty    ${weight_files}    msg=Preview response should include candidate files
    @{allowed_roles}=    Create List    primary    shard    config
    FOR    ${wf}    IN    @{weight_files}
        Dictionary Should Contain Key    ${wf}    path
        Dictionary Should Contain Key    ${wf}    role
        Dictionary Should Contain Key    ${wf}    sizeBytes
        Should Not Be Empty    ${wf}[path]
        List Should Contain Value    ${allowed_roles}    ${wf}[role]
    END
    VAR    ${selectable_count}    ${0}
    FOR    ${wf}    IN    @{weight_files}
        IF    "${wf}[role]" == "primary" or "${wf}[role]" == "shard"
            ${selectable_count}=    Evaluate    ${selectable_count} + 1
            Should Be True    ${wf}[sizeBytes] > 0
            ...    msg=Selectable weight file ${wf}[path] must have a positive sizeBytes
        END
    END
    Should Be True    ${selectable_count} > 0
    ...    msg=Preview response should include at least one selectable weight file

Custom model preview response revision should be "${expected_revision}"
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Should Be Equal    ${json}[revision]    ${expected_revision}

A Hugging Face token secret "${name}" exists for custom model preview
    A secret "${name}" with use case "HuggingFace" is created via AIWB
    # The preview/onboard API resolves hfTokenSecretName by the secret's Kubernetes
    # resource name (read_namespaced_secret), not its AIWB display name. AIWB generates
    # a distinct k8s name (wb-secret-*) from the displayName, so pass the k8s name here.
    Set Test Variable    ${CUSTOM_MODELS_HF_SECRET_NAME}    ${TEST_AIWB_SECRET_K8S_NAME}

Custom model preview secret cleanup is performed
    Clean Up All Created AIWB Secrets

The project custom model list is retrieved
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Models    ${namespace}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The runtime profile options for the project are retrieved
    ${namespace}=    Get Project Namespace
    ${response}=    Get Runtime Profile Options    ${namespace}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The base-image runtime profile options for a discovered image are retrieved
    [Documentation]    Reads the cluster image catalog, selects one discovered concrete
    ...    base image (repository + tag), and fetches its runtime options.
    ${namespace}=    Get Project Namespace
    ${catalog_response}=    List aim image families    expected_status=200
    ${catalog}=    Get From Dictionary    ${catalog_response.json()}    data
    VAR    ${repository}    ${EMPTY}
    VAR    ${tag}    ${EMPTY}
    FOR    ${family}    IN    @{catalog}
        ${family_id}=    Get From Dictionary    ${family}    familyId
        ${candidate_repo}=    Get From Dictionary    ${family}    repository    default=${EMPTY}
        ${tags}=    Get From Dictionary    ${family}    tags    default=@{EMPTY}
        IF    "${family_id}" != "automatic" and "${candidate_repo}" != "" and len($tags) > 0
            VAR    ${repository}    ${candidate_repo}
            VAR    ${tag}    ${tags}[0]
            BREAK
        END
    END
    Should Not Be Empty    ${repository}
    ...    msg=No discovered base-image repository with tags found in /cluster/aim-images response
    Should Not Be Empty    ${tag}
    ...    msg=No discovered base-image tag found in /cluster/aim-images response
    ${response}=    Get Runtime Profile Options By Image    ${namespace}    ${repository}    ${tag}    expected_status=any
    VAR    ${TEST_BASE_IMAGE_REPOSITORY}    ${repository}    scope=TEST
    VAR    ${TEST_BASE_IMAGE_TAG}    ${tag}    scope=TEST
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Runtime profile options response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

Runtime profile options response should expose the runtime matrix fields
    [Documentation]    The onboard wizard presets precision/accelerator/count from these
    ...    lists, so every field must be present and list-shaped even when the base model
    ...    has not emitted profiles yet (empty lists, never missing keys).
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    FOR    ${field}    IN    acceleratorModels    precisions    acceleratorCounts    optimizationClasses    metrics
        Dictionary Should Contain Key    ${json}    ${field}
        ...    msg=Runtime profile options response is missing '${field}'
        ${value}=    Get From Dictionary    ${json}    ${field}
        Should Be True    isinstance($value, list)
        ...    msg=Runtime profile options field '${field}' must be a list
    END
    Dictionary Should Contain Key    ${json}    combinations
    ...    msg=Runtime profile options response is missing 'combinations'
    Runtime Profile Options Combinations Should Be Consistent    ${json}

Base-image runtime profile options response should expose the per-image runtime matrix fields
    [Documentation]    The base-image runtime options endpoint must echo the selected image
    ...    and expose runtime matrix fields keyed by accelerator model.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Should Be Equal    ${json}[imageRepository]    ${TEST_BASE_IMAGE_REPOSITORY}
    Should Be Equal    ${json}[imageTag]    ${TEST_BASE_IMAGE_TAG}
    FOR    ${field}    IN    acceleratorTypes    acceleratorModels
        Dictionary Should Contain Key    ${json}    ${field}
        ...    msg=Base-image runtime profile options response is missing '${field}'
        ${value}=    Get From Dictionary    ${json}    ${field}
        Should Be True    isinstance($value, list)
        ...    msg=Base-image runtime profile options field '${field}' must be a list
    END
    FOR    ${field}    IN    acceleratorCountsByModel    precisionsByModel    metricsByModel    optimizationClassesByModel
        Dictionary Should Contain Key    ${json}    ${field}
        ...    msg=Base-image runtime profile options response is missing '${field}'
        ${value}=    Get From Dictionary    ${json}    ${field}
        Should Be True    isinstance($value, dict)
        ...    msg=Base-image runtime profile options field '${field}' must be an object
    END
    Dictionary Should Contain Key    ${json}    combinations
    ...    msg=Base-image runtime profile options response is missing 'combinations'
    Base Image Runtime Profile Options Combinations Should Be Consistent    ${json}

No custom model has been imported into the project
    [Documentation]    Asserts the project has never gone through the custom-model import flow.
    ...                Used as a regression precondition: a fine-tuned model that becomes
    ...                deployable in such a project proves the base needed for profile
    ...                generation is provisioned at fine-tune launch, not as a side effect
    ...                of a custom import.
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Models    ${namespace}    expected_status=200
    ${models}=    Get From Dictionary    ${response.json()}    data
    Should Be Empty    ${models}
    ...    msg=Project already has imported custom models — regression precondition not met

The custom model list should be empty
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    ${models}=    Get From Dictionary    ${TEST_RESPONSE.json()}    data
    Should Be Empty    ${models}    msg=Expected an empty data array but got ${models}

Custom model list should contain a model from "${expected_repo_id}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${models}=    Get From Dictionary    ${json}    data
    Should Not Be Empty    ${models}    msg=No custom models returned in list
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        IF    "${canonical}" == "${expected_repo_id}"
            RETURN
        END
    END
    Fail    No custom model with canonical-repo-id '${expected_repo_id}' found in list response

Listed custom model from "${expected_repo_id}" should include display name and tags
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${models}=    Get From Dictionary    ${json}    data
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        IF    "${canonical}" == "${expected_repo_id}"
            ${display_name}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/model-display-name    default=${EMPTY}
            Should Not Be Empty    ${display_name}
            ...    msg=Custom model '${expected_repo_id}' must have a non-empty model-display-name annotation
            ${tags_raw}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/source-tags    default=${EMPTY}
            Should Not Be Equal    ${tags_raw}    ${EMPTY}
            ...    msg=Custom model '${expected_repo_id}' must have a source-tags annotation
            RETURN
        END
    END
    Fail    No custom model with canonical-repo-id '${expected_repo_id}' found in list response

Listed custom model from "${source}" should show display name "${expected_name}"
    [Documentation]    Asserts the display-name annotation on the listed model matches
    ...    the user-provided name supplied at onboard time rather than the preview default.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${models}=    Get From Dictionary    ${json}    data
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        IF    "${canonical}" == "${source}"
            ${display_name}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/model-display-name    default=${EMPTY}
            Should Be Equal    ${display_name}    ${expected_name}
            ...    msg=Expected display name '${expected_name}', got '${display_name}' for model '${source}'
            RETURN
        END
    END
    Fail    No custom model with canonical-repo-id '${source}' found in list response

Custom model preview response should signal no authentication is required
    [Documentation]    Asserts the preview response for a public model carries
    ...    ``hfTokenRecommended: false`` so the UI does not prompt for a Hugging Face
    ...    token when importing a model that does not need one.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    hfTokenRecommended
    ${flag}=    Get From Dictionary    ${json}    hfTokenRecommended
    Should Be Equal    ${flag}    ${False}
    ...    msg=Public model preview should report hfTokenRecommended=false; got '${flag}'

Custom AIMModel for source "${expected_repo_id}" should exist in the namespace
    [Documentation]    Finds the custom-onboarded AIMModel CR by its canonical-repo-id annotation
    ...    and stores it in ${CUSTOM_MODEL_AIM_CR} for subsequent spec assertions.
    ...    Uses the custom-models list endpoint (GET /projects/{ns}/models) which only
    ...    returns custom-imported models, not fine-tuned ones.
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Models    ${namespace}    expected_status=200
    ${models}=    Get From Dictionary    ${response.json()}    data
    Should Not Be Empty    ${models}    msg=No custom AIMModel CRs found in namespace ${namespace}
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        IF    "${canonical}" == "${expected_repo_id}"
            Set Test Variable    ${CUSTOM_MODEL_AIM_CR}    ${model}
            Stamp Custom Model With This Run    ${namespace}    ${model}[metadata][name]
            RETURN
        END
    END
    Fail    No custom AIMModel CR with canonical-repo-id '${expected_repo_id}' found in namespace ${namespace}

No custom AIMModel for source "${expected_repo_id}" should exist in the namespace
    [Documentation]    Verifies a rejected onboard request did not persist a custom model.
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Models    ${namespace}    expected_status=200
    ${models}=    Get From Dictionary    ${response.json()}    data
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        Should Not Be Equal    ${canonical}    ${expected_repo_id}
        ...    msg=Rejected onboard persisted a custom AIMModel for '${expected_repo_id}'
    END

Custom AIMModel for source "${expected_repo_id}" should keep Hugging Face source URI
    [Documentation]    Verifies the custom AIMModel keeps the source as
    ...    ``hf://owner/model`` in ``spec.profiles.overrides.modelSources[0].sourceUri``.
    Custom AIMModel for source "${expected_repo_id}" should exist in the namespace
    ${spec}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    spec
    ${profiles}=    Get From Dictionary    ${spec}    profiles    default=&{EMPTY}
    ${overrides}=    Get From Dictionary    ${profiles}    overrides    default=&{EMPTY}
    ${sources}=    Get From Dictionary    ${overrides}    modelSources    default=${EMPTY}
    Should Not Be Empty    ${sources}    msg=AIMModel has no modelSources for Hugging Face source
    ${first_source}=    Get From List    ${sources}    0
    ${source_uri}=    Get From Dictionary    ${first_source}    sourceUri    default=${EMPTY}
    Should Be Equal    ${source_uri}    hf://${expected_repo_id}
    ...    msg=Expected sourceUri hf://${expected_repo_id}, got ${source_uri}

Exactly one custom AIMModel for source "${expected_repo_id}" should exist in the namespace
    [Documentation]    Asserts the namespace contains exactly one custom-onboarded AIMModel CR
    ...    for the given canonical repo id — the idempotency guarantee for repeated onboard calls.
    ...    Uses the canonical-repo-id annotation, which is the stable identity for custom imports.
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Models    ${namespace}    expected_status=200
    ${models}=    Get From Dictionary    ${response.json()}    data
    ${matches}=    Create List
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        IF    "${canonical}" == "${expected_repo_id}"
            Append To List    ${matches}    ${model}
        END
    END
    ${count}=    Get Length    ${matches}
    Should Be Equal As Integers    ${count}    1
    ...    msg=Expected exactly one AIMModel for source '${expected_repo_id}', found ${count}

Custom AIMModel for source "${expected_repo_id}" should wire HF token secret "${expected_secret_name}"
    [Documentation]    Asserts the AIMModel CR wires the HF token secret into the
    ...    first model source's env as an HF_TOKEN secretKeyRef. This is the v1alpha2
    ...    behavioral guarantee that gated/private models get their token plumbed by
    ...    aim-engine. Token wiring lives at spec.profiles.overrides.modelSources[0].env,
    ...    not the legacy top-level spec.env which is empty for custom onboarded models.
    Custom AIMModel for source "${expected_repo_id}" should exist in the namespace
    ${spec}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    spec
    ${profiles}=    Get From Dictionary    ${spec}    profiles    default=&{EMPTY}
    Should Not Be Empty    ${profiles}    msg=AIMModel has no spec.profiles; HF_TOKEN wiring not present
    ${overrides}=    Get From Dictionary    ${profiles}    overrides    default=&{EMPTY}
    Should Not Be Empty    ${overrides}    msg=AIMModel has no spec.profiles.overrides; HF_TOKEN wiring not present
    ${sources}=    Get From Dictionary    ${overrides}    modelSources    default=${EMPTY}
    Should Not Be Empty    ${sources}    msg=AIMModel has no spec.profiles.overrides.modelSources; HF_TOKEN wiring not present
    ${first_source}=    Get From List    ${sources}    0
    ${env}=    Get From Dictionary    ${first_source}    env    default=${EMPTY}
    Should Not Be Empty    ${env}    msg=First model source has no env entries; HF_TOKEN not wired
    VAR    ${hf_token_entry}    ${None}
    FOR    ${entry}    IN    @{env}
        ${name}=    Get From Dictionary    ${entry}    name    default=${EMPTY}
        IF    "${name}" == "HF_TOKEN"
            VAR    ${hf_token_entry}    ${entry}
            BREAK
        END
    END
    Should Not Be Equal    ${hf_token_entry}    ${None}
    ...    msg=No HF_TOKEN entry in spec.profiles.overrides.modelSources[0].env
    ${value_from}=    Get From Dictionary    ${hf_token_entry}    valueFrom
    ${secret_ref}=    Get From Dictionary    ${value_from}    secretKeyRef
    Should Be Equal    ${secret_ref}[name]    ${expected_secret_name}
    Should Be Equal    ${secret_ref}[key]    token

Custom AIMModel for source "${expected_source}" should wire S3 secret "${expected_secret_name}"
    [Documentation]    Asserts the model source remains the external S3 URI and wires
    ...    access credentials from the supplied S3 secret through modelSources env refs.
    Custom AIMModel for source "${expected_source}" should exist in the namespace
    ${spec}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    spec
    ${profiles}=    Get From Dictionary    ${spec}    profiles    default=&{EMPTY}
    Should Not Be Empty    ${profiles}    msg=AIMModel has no spec.profiles for S3 source
    ${overrides}=    Get From Dictionary    ${profiles}    overrides    default=&{EMPTY}
    Should Not Be Empty    ${overrides}    msg=AIMModel has no spec.profiles.overrides for S3 source
    ${sources}=    Get From Dictionary    ${overrides}    modelSources    default=${EMPTY}
    Should Not Be Empty    ${sources}    msg=AIMModel has no modelSources for S3 source
    ${first_source}=    Get From List    ${sources}    0
    ${source_uri}=    Get From Dictionary    ${first_source}    sourceUri    default=${EMPTY}
    Should Be Equal    ${source_uri}    ${expected_source}
    ${env}=    Get From Dictionary    ${first_source}    env    default=${EMPTY}
    Should Not Be Empty    ${env}    msg=S3 model source env wiring is missing
    VAR    ${access_entry}    ${None}
    VAR    ${secret_entry}    ${None}
    FOR    ${entry}    IN    @{env}
        ${name}=    Get From Dictionary    ${entry}    name    default=${EMPTY}
        IF    "${name}" == "AWS_ACCESS_KEY_ID"
            VAR    ${access_entry}    ${entry}
        END
        IF    "${name}" == "AWS_SECRET_ACCESS_KEY"
            VAR    ${secret_entry}    ${entry}
        END
    END
    Should Not Be Equal    ${access_entry}    ${None}
    ...    msg=No AWS_ACCESS_KEY_ID env entry in modelSources env for S3 source
    Should Not Be Equal    ${secret_entry}    ${None}
    ...    msg=No AWS_SECRET_ACCESS_KEY env entry in modelSources env for S3 source
    ${access_ref}=    Get From Dictionary    ${access_entry}[valueFrom]    secretKeyRef
    ${secret_ref}=    Get From Dictionary    ${secret_entry}[valueFrom]    secretKeyRef
    Should Be Equal    ${access_ref}[name]    ${expected_secret_name}
    Should Be Equal    ${secret_ref}[name]    ${expected_secret_name}
    Should Not Be Empty    ${access_ref}[key]
    Should Not Be Empty    ${secret_ref}[key]
    # Optional endpoint/region values may be omitted, but must never be emitted as blanks.
    Custom S3 source env should not include blank optional values    ${env}

Custom S3 source env should not include blank optional values
    [Documentation]    Validates optional S3 env entries are either omitted or non-empty.
    ...    Blank optional values are invalid because they break endpoint/region fallback semantics.
    [Arguments]    ${env}
    FOR    ${entry}    IN    @{env}
        ${name}=    Get From Dictionary    ${entry}    name    default=${EMPTY}
        IF    "${name}" == "AWS_ENDPOINT_URL" or "${name}" == "AWS_DEFAULT_REGION"
            ${value}=    Get From Dictionary    ${entry}    value    default=${EMPTY}
            ${trimmed}=    Strip String    ${value}
            Should Not Be Empty    ${trimmed}
            ...    msg=Optional S3 env ${name} must be omitted when unknown, not emitted as blank
        END
    END

Custom AIMModel for source "${expected_repo_id}" should use image "${expected_image}"
    [Documentation]    Asserts the AIMModel CR's container image matches the expected value.
    ...    v1alpha2 CRs store the image at spec.profiles.overrides.image, not the
    ...    legacy top-level spec.image which is always empty for custom onboarded models.
    Custom AIMModel for source "${expected_repo_id}" should exist in the namespace
    ${spec}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    spec
    ${profiles}=    Get From Dictionary    ${spec}    profiles    default=&{EMPTY}
    Should Not Be Empty    ${profiles}    msg=AIMModel has no spec.profiles; image override not present
    ${overrides}=    Get From Dictionary    ${profiles}    overrides    default=&{EMPTY}
    Should Not Be Empty    ${overrides}    msg=AIMModel has no spec.profiles.overrides; image override not present
    ${image}=    Get From Dictionary    ${overrides}    image
    Should Be Equal    ${image}    ${expected_image}

The onboarded custom model from "${expected_repo_id}" should use runtime family from image "${expected_image}"
    [Documentation]    The selected runtime image must supply both the model container
    ...    and the profile family used by the onboarded model. Also records
    ...    ``${TEST_CUSTOM_MODEL_NAME}``, ``${TEST_SELECTED_BASE_FAMILY}``,
    ...    and ``${TEST_SELECTED_BASE_SCOPE}``.
    Custom AIMModel for source "${expected_repo_id}" should exist in the namespace
    ${metadata}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    metadata
    ${resource_name}=    Get From Dictionary    ${metadata}    name
    VAR    ${TEST_CUSTOM_MODEL_NAME}    ${resource_name}    scope=TEST
    ${namespace}=    Get Project Namespace
    AIMModel Should Use Runtime Family From Image    ${resource_name}    ${namespace}    ${expected_image}
    ${spec}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    spec
    ${profiles}=    Get From Dictionary    ${spec}    profiles    default=&{EMPTY}
    ${derived_from}=    Get From Dictionary    ${profiles}    derivedFrom    default=&{EMPTY}
    ${selector}=    Get From Dictionary    ${derived_from}    selector    default=&{EMPTY}
    ${model_ref}=    Get From Dictionary    ${selector}    modelRef    default=&{EMPTY}
    ${model_name}=    Get From Dictionary    ${model_ref}    name    default=${EMPTY}
    ${scope}=    Get From Dictionary    ${model_ref}    scope    default=Namespace
    VAR    ${TEST_SELECTED_BASE_FAMILY}    ${model_name}    scope=TEST
    VAR    ${TEST_SELECTED_BASE_SCOPE}    ${scope}    scope=TEST

The user selects a runtime image other than the cluster default
    [Documentation]    Records a published image that is not the hardware-default onboard image.
    ${catalog_response}=    List aim image families    expected_status=200
    ${catalog}=    Get From Dictionary    ${catalog_response.json()}    data
    ${accel_response}=    List cluster accelerators    expected_status=200
    ${accelerators}=    Get From Dictionary    ${accel_response.json()}    data
    ${image}=    Resolve Alternate Onboard Image From Cluster Discovery
    ...    ${catalog}
    ...    ${accelerators}
    ...    ${CUSTOM_MODELS_ONBOARD_IMAGE}
    VAR    ${TEST_SELECTED_ONBOARD_IMAGE}    ${image}    scope=TEST

Another published tag of the onboarded runtime family is recorded
    [Documentation]    Records a second tag of the family already used by this project's onboard.
    ${catalog_response}=    List aim image families    expected_status=200
    ${catalog}=    Get From Dictionary    ${catalog_response.json()}    data
    ${image}=    Resolve Conflicting Tag Of Onboard Image    ${catalog}    ${CUSTOM_MODELS_ONBOARD_IMAGE}
    VAR    ${TEST_CONFLICTING_ONBOARD_IMAGE}    ${image}    scope=TEST

The project base model should use selected image "${expected_image}"
    [Documentation]    The base model the custom model derives from must run the selected
    ...    image, whether that resource is namespaced or cluster-scoped.
    ${namespace}=    Get Project Namespace
    ${family}=    Get Variable Value    ${TEST_SELECTED_BASE_FAMILY}
    Should Not Be Empty    ${family}
    ...    msg=No selected runtime family recorded; assert the onboarded model first
    ${scope}=    Get Variable Value    ${TEST_SELECTED_BASE_SCOPE}    Namespace
    ${actual_image}=    AIMModel Spec Image    ${family}    ${namespace}    ${scope}
    Should Be Equal    ${actual_image}    ${expected_image}
    ...    msg=Project base model '${family}' should use '${expected_image}', got '${actual_image}'

Custom AIMModel for source "${expected_repo_id}" should carry profile override "${field}" with value "${expected_value}"
    [Documentation]    Asserts that at least one custom AIMModel CR for the source
    ...    has the given field in ``spec.profiles.overrides``. Searches all matching
    ...    models because a namespace may hold both an original and copies; only the
    ...    onboarded original carries the customProfile overrides.
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Models    ${namespace}    expected_status=200
    ${models}=    Get From Dictionary    ${response.json()}    data
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        IF    "${canonical}" != "${expected_repo_id}"    CONTINUE
        ${spec}=    Get From Dictionary    ${model}    spec
        ${profiles}=    Get From Dictionary    ${spec}    profiles    default=&{EMPTY}
        IF    not ${profiles}    CONTINUE
        ${overrides}=    Get From Dictionary    ${profiles}    overrides    default=&{EMPTY}
        IF    not ${overrides}    CONTINUE
        ${has_field}=    Run Keyword And Return Status    Dictionary Should Contain Key    ${overrides}    ${field}
        IF    not ${has_field}    CONTINUE
        Should Be Equal As Strings    ${overrides}[${field}]    ${expected_value}
        ...    msg=Profile override '${field}' has unexpected value '${overrides}[${field}]' (expected '${expected_value}')
        Set Test Variable    ${CUSTOM_MODEL_AIM_CR}    ${model}
        Stamp Custom Model With This Run    ${namespace}    ${model}[metadata][name]
        RETURN
    END
    Fail    No custom AIMModel with canonical-repo-id '${expected_repo_id}' has profile override '${field}' == '${expected_value}' in namespace ${namespace}

The onboarded custom model detail is retrieved for "${source}"
    [Documentation]    Locate the onboarded model by source repo id in the list,
    ...    then fetch its detail by name via GET /projects/{project}/models/{model_name}.
    ${namespace}=    Get Project Namespace
    ${list_response}=    List Custom Models    ${namespace}    expected_status=200
    ${models}=    Get From Dictionary    ${list_response.json()}    data
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        IF    "${canonical}" == "${source}"
            ${name}=    Get From Dictionary    ${model}[metadata]    name
            ${response}=    Get Custom Model    ${namespace}    ${name}    expected_status=200
            Set Test Variable    ${TEST_RESPONSE}    ${response}
            RETURN
        END
    END
    Fail    No onboarded model with canonical-repo-id '${source}' found; cannot fetch detail

Requesting a non-existent custom model returns not-found
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model    ${namespace}    no-such-model-zzz    expected_status=404
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The custom model detail is requested for model "${model_name}"
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model    ${namespace}    ${model_name}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Custom model detail response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

Custom model detail should match the onboarded source "${expected_repo_id}"
    [Documentation]    Verify the detail response describes the expected model:
    ...    correct metadata name, spec, and composed lifecycle phase present,
    ...    with the canonical-repo-id annotation matching the expected source.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    metadata
    Dictionary Should Contain Key    ${json}    spec
    Dictionary Should Contain Key    ${json}    phase
    ${annotations}=    Get From Dictionary    ${json}[metadata]    annotations    default=&{EMPTY}
    ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
    Should Be Equal    ${canonical}    ${expected_repo_id}
    ...    msg=Detail response canonical-repo-id annotation does not match expected repo id

Custom model detail should include onboarding status fields
    [Documentation]    Verify that the composed lifecycle phase is present and structurally
    ...    correct: state, templateReady, artifactPhase, and artifactLastError
    ...    must all be present so the UI can render the onboarding state.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${phase}=    Get From Dictionary    ${json}    phase
    Dictionary Should Contain Key    ${phase}    state
    Dictionary Should Contain Key    ${phase}    templateReady
    Dictionary Should Contain Key    ${phase}    artifactPhase
    Dictionary Should Contain Key    ${phase}    artifactLastError
    ${valid_states}=    Create List    Pending    Ready    Failed
    List Should Contain Value    ${valid_states}    ${phase}[state]
    ...    msg=Onboard phase state '${phase}[state]' is not a recognised value

Listed custom models include onboarding status fields
    [Documentation]    Verify every item in the list response carries the composed lifecycle
    ...    phase: state, templateReady, artifactPhase, and artifactLastError
    ...    must all be present so the UI can render per-model onboarding state without
    ...    issuing a separate detail request.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${models}=    Get From Dictionary    ${json}    data
    Should Not Be Empty    ${models}    msg=No custom models returned in list
    ${valid_states}=    Create List    Pending    Ready    Failed
    FOR    ${model}    IN    @{models}
        ${phase}=    Get From Dictionary    ${model}    phase
        Dictionary Should Contain Key    ${phase}    state
        Dictionary Should Contain Key    ${phase}    templateReady
        Dictionary Should Contain Key    ${phase}    artifactPhase
        Dictionary Should Contain Key    ${phase}    artifactLastError
        List Should Contain Value    ${valid_states}    ${phase}[state]
        ...    msg=Onboard phase state '${phase}[state]' is not a recognised value
    END

Custom model detail should present the Default profile first
    [Documentation]    Once the Default is ready, the detail response carries the profile
    ...    collection the grid renders from: a list whose first row is the Default (isDefault,
    ...    reserved 'default' name), with its real resourceName and effective profile — so a
    ...    consumer never treats an arbitrary profiles[0] as "the" profile. Response parsing and
    ...    the ordering assertion live in AIMModelHelper so this keyword stays declarative.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    Detail Response Should Present Default Profile First    ${TEST_RESPONSE.json()}

Listed custom model from "${expected_repo_id}" should present the Default profile first
    [Documentation]    The list response carries each model's profile collection, Default first,
    ...    so the grid can show a count and the Default summary without a per-model profile query.
    ...    The find-by-source and ordering logic live in AIMModelHelper.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    Listed Model Should Present Default Profile First    ${TEST_RESPONSE.json()}    ${expected_repo_id}

Custom model detail should include the named profile "${display_name}" alongside the Default
    [Documentation]    After a named profile is created, the detail collection lists both rows:
    ...    the Default first (isDefault) and the named row (not default) carrying its display name.
    ...    The collection assertions live in AIMModelHelper.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    Detail Response Should Include Named Profile Alongside Default    ${TEST_RESPONSE.json()}    ${display_name}

A custom model is onboarded in the project
    [Documentation]    Previews and onboards the public test repo, then resolves the
    ...    AIMModel CR name into ${TEST_CUSTOM_MODEL_NAME} for subsequent PATCH and DELETE steps.
    ...    Sends the cluster's accelerator, as the import wizard does, so every derived profile
    ...    can run here.
    ${accelerator}=    The cluster's GPU accelerator model
    Onboard the public custom model with accelerator "${accelerator}"

Onboard the public custom model with accelerator "${accelerator}"
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    IF    "${accelerator}" != ""
        When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}" and runtime profile overrides
        ...    acceleratorModel=${accelerator}
    ELSE
        When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    END
    Then custom model onboard response status should be "204"
    And custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace
    ${metadata}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    metadata
    ${model_name}=    Get From Dictionary    ${metadata}    name
    Set Test Variable    ${TEST_CUSTOM_MODEL_NAME}    ${model_name}
    ${namespace}=    Get Project Namespace
    Track Custom Model For Cleanup    ${namespace}    ${model_name}

The cluster's GPU accelerator model
    [Documentation]    The accelerator model the cluster actually has, or empty on a cluster with
    ...    no GPU. A model onboarded without one derives profiles for every accelerator aim-engine
    ...    knows, most of which can never run here, so the Default can resolve to an unrunnable
    ...    profile; the import wizard avoids this by always sending the cluster's accelerator.
    ${response}=    List cluster accelerators    expected_status=200
    ${accelerator}=    Cluster Gpu Accelerator Model    ${response.json()}[data]    ${CUSTOM_MODELS_ONBOARD_IMAGE}
    RETURN    ${accelerator}

The profiles for the onboarded custom model are retrieved
    [Documentation]    Lists the profiles of the model onboarded by "A custom model is
    ...    onboarded in the project" (resolved into ${TEST_CUSTOM_MODEL_NAME}), waiting
    ...    for aim-engine to emit the effective Default profile.
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Custom model profiles with an effective Default are available

Custom model profiles with an effective Default are available
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Model Profiles    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    expected_status=200
    VAR    ${json}    ${response.json()}
    ${profiles}=    Get From Dictionary    ${json}    data
    Should Not Be Empty    ${profiles}    msg=No profiles returned for the custom model
    ${first}=    Get From List    ${profiles}    0
    Should Not Be Empty    ${first}[profile]    msg=Default profile has not been emitted yet
    Should Be Equal    ${first}[status][state]    Ready    msg=Default profile is not ready yet
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The Default profile for the onboarded custom model is retrieved
    [Documentation]    Fetches the Default via the reserved 'default' alias so clients need
    ...    not carry the engine-generated set name.
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model Profile    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    default    expected_status=200
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

A profile that does not belong to the model is requested
    [Documentation]    A profile identifier not owned by this model must read as not-found
    ...    rather than returning another model's or project's data.
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model Profile
    ...    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    no-such-profile-zzz    expected_status=404
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The profiles for a non-existent custom model are requested
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Model Profiles    ${namespace}    no-such-model-zzz    expected_status=404
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The first tenant's named profile should not appear in the second tenant's profile list
    [Documentation]    The second tenant's profile list for its own copy of the model must not
    ...    contain the named profile the first tenant created — AIMProfileSets are
    ...    namespace-scoped, so a create in one project must never surface in another. Reads the
    ...    list from ${TEST_RESPONSE} (the second tenant's profiles) and the first tenant's
    ...    profile name from ${TEST_CREATED_PROFILE_NAME}.
    ${profiles}=    Get From Dictionary    ${TEST_RESPONSE.json()}    data
    ${names}=    Evaluate    [p.get("displayName") for p in $profiles]
    List Should Not Contain Value    ${names}    ${TEST_CREATED_PROFILE_NAME}
    ...    msg=First tenant's profile '${TEST_CREATED_PROFILE_NAME}' leaked into the second tenant's profile list

Custom model profile list response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

Custom model profile detail response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

The profile list should present the Default first
    [Documentation]    The Default is classified by provenance, flagged isDefault, named by the
    ...    reserved 'default' alias, and returned as the first row with its real resourceName
    ...    and effective derived profile.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${profiles}=    Get From Dictionary    ${json}    data
    Should Not Be Empty    ${profiles}    msg=No profiles returned for the custom model
    ${first}=    Get From List    ${profiles}    0
    Should Be True    ${first}[isDefault]    msg=First profile row is not the Default
    Should Be Equal    ${first}[name]    default    msg=Default row name should be the reserved 'default' alias
    Should Not Be Empty    ${first}[resourceName]    msg=Default row must carry its real resourceName
    Should Not Be Empty    ${first}[status][state]    msg=Default row must carry effective profile status
    Dictionary Should Contain Key    ${first}    selector
    Dictionary Should Contain Key    ${first}    customProfile
    ${owner_refs}=    Get From Dictionary    ${first}[profile][metadata]    ownerReferences
    ${owner_names}=    Evaluate    [ref.get("name") for ref in $owner_refs]
    List Should Contain Value    ${owner_names}    ${first}[resourceName]
    ...    msg=Effective profile is not owned by the Default AIMProfileSet

The retrieved profile should be the Default
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Should Be True    ${json}[isDefault]    msg=Retrieved profile is not flagged as the Default
    Should Be Equal    ${json}[name]    default    msg=Default profile name should be the reserved 'default' alias
    Should Not Be Empty    ${json}[resourceName]    msg=Default profile must carry its real resourceName

The onboarded model's Default profile is ready
    [Documentation]    Behavioral precondition: waits until the model's Default profile has
    ...    reconciled to a ready effective profile, so a new profile can be added against a
    ...    supported hardware point. Records that hardware point internally so the follow-up
    ...    create narrows to exactly one base profile — an implementation detail the scenario
    ...    does not depend on.
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Custom model profiles with an effective Default are available
    ${response}=    Get Custom Model Profile    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    default    expected_status=200
    VAR    ${spec}    ${response.json()}[profile][spec]
    VAR    ${TEST_PROFILE_ACCELERATOR_MODEL}    ${spec}[acceleratorModel]    scope=TEST
    VAR    ${TEST_PROFILE_ACCELERATOR_COUNT}    ${spec}[acceleratorCount]    scope=TEST
    VAR    ${TEST_PROFILE_PRECISION}    ${spec}[precision]    scope=TEST
    VAR    ${TEST_PROFILE_METRIC}    ${spec}[metric]    scope=TEST

The user adds a profile named "${display_name}" to the onboarded custom model
    [Documentation]    Creates a named profile narrowed to the Default's hardware point (so it
    ...    resolves to exactly one base profile), with the onboard image.
    ${namespace}=    Get Project Namespace
    &{body}=    Create Dictionary
    ...    displayName=${display_name}
    ...    acceleratorModel=${TEST_PROFILE_ACCELERATOR_MODEL}
    ...    acceleratorCount=${TEST_PROFILE_ACCELERATOR_COUNT}
    ...    precision=${TEST_PROFILE_PRECISION}
    ...    metric=${TEST_PROFILE_METRIC}
    ...    image=${CUSTOM_MODELS_ONBOARD_IMAGE}
    ${response}=    Create Custom Model Profile    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${body}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    VAR    ${TEST_CREATED_PROFILE_NAME}    ${display_name}    scope=TEST

The user attempts to add a profile named "${display_name}" to the onboarded custom model
    [Documentation]    Sends a create request with placeholder axes; schema validation
    ...    short-circuits an invalid display name before any base-profile resolution.
    ${namespace}=    Get Project Namespace
    &{body}=    Create Dictionary
    ...    displayName=${display_name}
    ...    acceleratorModel=MI300X
    ...    acceleratorCount=${1}
    ...    precision=fp16
    ...    metric=latency
    ...    image=${CUSTOM_MODELS_ONBOARD_IMAGE}
    ${response}=    Create Custom Model Profile    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${body}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The user attempts to add a profile named "${display_name}" to a non-existent custom model
    ${namespace}=    Get Project Namespace
    &{body}=    Create Dictionary
    ...    displayName=${display_name}
    ...    acceleratorModel=MI300X
    ...    acceleratorCount=${1}
    ...    precision=fp16
    ...    metric=latency
    ...    image=${CUSTOM_MODELS_ONBOARD_IMAGE}
    ${response}=    Create Custom Model Profile    ${namespace}    no-such-model-zzz    ${body}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Custom model profile create response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

The created profile should describe a non-default profile
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    201
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Should Not Be True    ${json}[isDefault]    msg=Created profile must not be flagged as the Default
    Should Be Equal    ${json}[displayName]    ${TEST_CREATED_PROFILE_NAME}
    Should Not Be Empty    ${json}[resourceName]    msg=Created profile must carry its AIMProfileSet resourceName

The created profile should appear in the model's profile list
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Model Profiles    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    expected_status=200
    ${profiles}=    Get From Dictionary    ${response.json()}    data
    ${names}=    Evaluate    [p.get("displayName") for p in $profiles]
    List Should Contain Value    ${names}    ${TEST_CREATED_PROFILE_NAME}
    ...    msg=Created profile '${TEST_CREATED_PROFILE_NAME}' not present in the profile list

The created profile should have its own identity distinct from the Default
    [Documentation]    A named profile is stored as its own durable AIMProfileSet, so it must
    ...    carry a stable resourceName that is not the model's engine-owned Default set — the
    ...    naming guarantee that keeps a later edit or delete off the Default. Asserting the
    ...    concrete resource identity here keeps that mechanism out of the scenario wording.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    201
    VAR    ${created}    ${TEST_RESPONSE.json()}
    Should Not Be Empty    ${created}[resourceName]    msg=Created profile must carry its own resourceName
    Should Be Equal    ${created}[resourceName]    ${created}[name]
    ...    msg=A named profile's name should be its real resourceName, not the reserved 'default' alias
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model Profile    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    default    expected_status=200
    VAR    ${default}    ${response.json()}
    Should Not Be Equal    ${created}[resourceName]    ${default}[resourceName]
    ...    msg=Created profile collides with the engine-owned Default resource name

The user renames the created profile to "${new_name}"
    [Documentation]    PATCH the just-created named profile's display name by its resourceName.
    ...    Requires TEST_RESPONSE to hold the create response (its resourceName is the
    ...    immutable AIMProfileSet name a rename must preserve).
    ${namespace}=    Get Project Namespace
    VAR    ${resource_name}    ${TEST_RESPONSE.json()}[resourceName]
    VAR    ${TEST_EDITED_PROFILE_RESOURCE_NAME}    ${resource_name}    scope=TEST
    VAR    ${TEST_EDITED_PROFILE_NEW_NAME}    ${new_name}    scope=TEST
    &{body}=    Create Dictionary    displayName=${new_name}
    ${response}=    Patch Custom Model Profile
    ...    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${resource_name}    ${body}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The profile edit response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}
    ...    msg=Unexpected profile edit status ${TEST_RESPONSE.status_code}: ${TEST_RESPONSE.text}

The renamed profile should keep its identity and show the new name
    [Documentation]    A rename returns the profile with the new display name while the
    ...    resourceName is unchanged (Kubernetes object names are immutable), and the new
    ...    name appears in the model's profile list.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Should Be Equal    ${json}[displayName]    ${TEST_EDITED_PROFILE_NEW_NAME}
    Should Be Equal    ${json}[resourceName]    ${TEST_EDITED_PROFILE_RESOURCE_NAME}
    ...    msg=Rename must not change the immutable AIMProfileSet resource name
    Should Not Be True    ${json}[isDefault]    msg=A renamed named profile must not become the Default
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Model Profiles    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    expected_status=200
    ${profiles}=    Get From Dictionary    ${response.json()}    data
    ${names}=    Evaluate    [p.get("displayName") for p in $profiles]
    List Should Contain Value    ${names}    ${TEST_EDITED_PROFILE_NEW_NAME}
    ...    msg=Renamed profile '${TEST_EDITED_PROFILE_NEW_NAME}' not present in the profile list

The user deletes the created profile
    [Documentation]    Deletes the profile just created by its own AIMProfileSet resourceName
    ...    (read from the create response), recording the display name so a later list check can
    ...    confirm it is gone.
    ...    Requires: the response from adding the profile
    ...    Sets: TEST_RESPONSE, TEST_DELETED_PROFILE_NAME
    ${namespace}=    Get Project Namespace
    VAR    ${resource_name}    ${TEST_RESPONSE.json()}[resourceName]
    Should Not Be Empty    ${resource_name}    msg=Create response carried no resourceName to delete
    VAR    ${TEST_DELETED_PROFILE_NAME}    ${TEST_CREATED_PROFILE_NAME}    scope=TEST
    ${response}=    Delete Custom Model Profile    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${resource_name}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The user attempts to delete the created profile
    [Documentation]    Attempts to delete the created profile by its resourceName. Used by the
    ...    in-use scenario where the delete is expected to be refused. Reuses TEST_SELECTED_PROFILE
    ...    (the created set's identifier, which is its resourceName).
    ${namespace}=    Get Project Namespace
    ${response}=    Delete Custom Model Profile    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${TEST_SELECTED_PROFILE}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The user attempts to delete the model's Default profile
    [Documentation]    Attempts to delete the Default via the reserved literal 'default'; the
    ...    endpoint must refuse it as unprocessable.
    ${namespace}=    Get Project Namespace
    ${response}=    Delete Custom Model Profile    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    default
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The profile delete response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}
    ...    msg=Unexpected profile delete status ${TEST_RESPONSE.status_code}: ${TEST_RESPONSE.text}

The deleted profile should no longer appear in the model's profile list
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Model Profiles    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    expected_status=200
    ${profiles}=    Get From Dictionary    ${response.json()}    data
    ${names}=    Evaluate    [p.get("displayName") for p in $profiles]
    List Should Not Contain Value    ${names}    ${TEST_DELETED_PROFILE_NAME}
    ...    msg=Deleted profile '${TEST_DELETED_PROFILE_NAME}' still present in the profile list

The model's Default profile should still be present
    [Documentation]    A sibling delete must leave the engine-owned Default untouched.
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model Profile    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    default    expected_status=200
    Should Be True    ${response.json()}[isDefault]    msg=Default profile missing after deleting a sibling

A deployment pins the created profile
    [Documentation]    Waits for aim-engine to derive an AIMProfile owned by the just-created
    ...    named set, then applies a minimal AIMService pinning it. The in-use guard keys on
    ...    spec.profile.name, so the service only needs to exist (no GPU / Ready state).
    ...    Requires TEST_RESPONSE to hold the create response.
    ${namespace}=    Get Project Namespace
    VAR    ${set_name}    ${TEST_RESPONSE.json()}[resourceName]
    VAR    ${TEST_EDITED_PROFILE_RESOURCE_NAME}    ${set_name}    scope=TEST
    ${profile_name}=    Wait Until Keyword Succeeds    3 min    10 sec
    ...    Get AIMProfile Name For Profile Set    ${TEST_CUSTOM_MODEL_NAME}    ${set_name}    ${namespace}
    VAR    ${service_name}    pin-svc-${TEST_CUSTOM_MODEL_NAME}
    Apply AIMService Pinning Profile    ${service_name}    ${TEST_CUSTOM_MODEL_NAME}    ${profile_name}    ${namespace}
    VAR    ${TEST_BLOCKING_AIM_SERVICE}    ${service_name}    scope=TEST

The user attempts to rename the pinned profile to "${new_name}"
    ${namespace}=    Get Project Namespace
    &{body}=    Create Dictionary    displayName=${new_name}
    ${response}=    Patch Custom Model Profile
    ...    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${TEST_EDITED_PROFILE_RESOURCE_NAME}    ${body}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The profile edit should be refused as in use by a deployment
    [Documentation]    The edit is refused with a conflict while a deployment pins one of the
    ...    profile's derived AIMProfiles; the response names the blocking deployment.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    409
    ...    msg=Expected a 409 in-use refusal, got ${TEST_RESPONSE.status_code}: ${TEST_RESPONSE.text}
    VAR    ${blocking_services}    ${TEST_RESPONSE.json()}[additionalInfo][blockingServices]
    Should Not Be Empty    ${blocking_services}    msg=Conflict response did not identify the blocking deployment
    Should Be Equal    ${blocking_services}[0][displayName]    ${TEST_BLOCKING_AIM_SERVICE}
    ...    msg=Conflict response named the wrong blocking deployment

The profile delete should be refused as in use by a deployment
    [Documentation]    The delete is refused with a 409 conflict naming the blocking deployment;
    ...    nothing is deleted.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    409
    ...    msg=Expected a 409 in-use refusal, got ${TEST_RESPONSE.status_code}: ${TEST_RESPONSE.text}
    VAR    ${blocking_services}    ${TEST_RESPONSE.json()}[additionalInfo][blockingServices]
    Should Not Be Empty    ${blocking_services}    msg=Conflict response did not identify the blocking deployment
    Should Be Equal    ${blocking_services}[0][displayName]    ${TEST_BLOCKING_AIM_SERVICE}
    ...    msg=Conflict response named the wrong blocking deployment
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model Profile
    ...    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${TEST_SELECTED_PROFILE}    expected_status=200
    Should Be Equal    ${response.json()}[name]    ${TEST_SELECTED_PROFILE}
    ...    msg=Refused delete unexpectedly removed the profile

The user updates the model display name to "${display_name}"
    ${namespace}=    Get Project Namespace
    &{body}=    Create Dictionary    displayName=${display_name}
    ${response}=    Patch Onboarded Model
    ...    ${namespace}
    ...    ${TEST_CUSTOM_MODEL_NAME}
    ...    ${body}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The user updates the model tags to "${tags_csv}"
    ${namespace}=    Get Project Namespace
    ${tags}=    Split String    ${tags_csv}    ,
    ${body}=    Create Dictionary    tags=${tags}
    ${response}=    Patch Onboarded Model
    ...    ${namespace}
    ...    ${TEST_CUSTOM_MODEL_NAME}
    ...    ${body}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The user updates the model display name to "${display_name}" and description to "${description}"
    [Documentation]    PATCH the onboarded model with both displayName and description
    ...    in a single request, mirroring the edit wizard saving the information step.
    ${namespace}=    Get Project Namespace
    &{body}=    Create Dictionary    displayName=${display_name}    description=${description}
    ${response}=    Patch Onboarded Model
    ...    ${namespace}
    ...    ${TEST_CUSTOM_MODEL_NAME}
    ...    ${body}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The user updates the model description to "${description}"
    ${namespace}=    Get Project Namespace
    &{body}=    Create Dictionary    description=${description}
    ${response}=    Patch Onboarded Model
    ...    ${namespace}
    ...    ${TEST_CUSTOM_MODEL_NAME}
    ...    ${body}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The user clears the model description
    [Documentation]    PATCH with ``description: ""`` — the empty string signals a
    ...    deliberate clear rather than an omitted field (which would leave the value
    ...    unchanged).
    ${namespace}=    Get Project Namespace
    &{body}=    Create Dictionary    description=${EMPTY}
    ${response}=    Patch Onboarded Model
    ...    ${namespace}
    ...    ${TEST_CUSTOM_MODEL_NAME}
    ...    ${body}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The user updates the model runtime image to "${image}"
    [Documentation]    PATCH only the model's own runtime image. This edit is scoped to the
    ...    model, so the project's shared runtime family keeps its original image — the
    ...    state a later copy has to reconcile.
    ${namespace}=    Get Project Namespace
    &{body}=    Create Dictionary    image=${image}
    ${response}=    Patch Onboarded Model
    ...    ${namespace}
    ...    ${TEST_CUSTOM_MODEL_NAME}
    ...    ${body}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    ...    msg=Runtime image edit failed: ${TEST_RESPONSE.status_code} ${TEST_RESPONSE.text}

The user edits the model runtime profile with conflicting image references
    [Documentation]    PATCH the onboarded model with a top-level image and a
    ...    customProfile.image that disagree. The request must be rejected at the
    ...    schema boundary (before any AIMProfile lookup), so two image refs never
    ...    reach the emitted profile.
    ${namespace}=    Get Project Namespace
    &{custom_profile}=    Create Dictionary    image=docker.io/other/image:v9
    &{body}=    Create Dictionary
    ...    image=${CUSTOM_MODELS_ONBOARD_IMAGE}
    ...    customProfile=${custom_profile}
    ${response}=    Patch Onboarded Model
    ...    ${namespace}
    ...    ${TEST_CUSTOM_MODEL_NAME}
    ...    ${body}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The runtime profile edit response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

The user edits the model runtime configuration
    [Documentation]    PATCH the onboarded model with the complete runtime configuration recorded
    ...    from its effective Default. These submitted axes are the narrowing target; the response
    ...    is captured without asserting a status so callers can assert success or refusal.
    ${namespace}=    Get Project Namespace
    &{custom_profile}=    Create Dictionary
    ...    acceleratorModel=${TEST_PROFILE_ACCELERATOR_MODEL}
    ...    acceleratorCount=${TEST_PROFILE_ACCELERATOR_COUNT}
    ...    precision=${TEST_PROFILE_PRECISION}
    ...    metric=${TEST_PROFILE_METRIC}
    &{body}=    Create Dictionary    image=${CUSTOM_MODELS_ONBOARD_IMAGE}    customProfile=${custom_profile}
    ${response}=    Patch Onboarded Model    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${body}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The onboarded model's Default derivation should match the submitted runtime configuration
    [Documentation]    After the edit, the engine-owned derivation is pinned to the submitted
    ...    configuration: the selector carries its accelerator count and precision, and the
    ...    overrides count agrees with it, so the pinned count matches the tensor-parallel size.
    ...    Requires TEST_PROFILE_* from "The onboarded model's Default profile is ready".
    Custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace
    ${spec}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    spec
    ${profiles}=    Get From Dictionary    ${spec}    profiles    default=&{EMPTY}
    ${derived_from}=    Get From Dictionary    ${profiles}    derivedFrom    default=&{EMPTY}
    ${selector}=    Get From Dictionary    ${derived_from}    selector    default=&{EMPTY}
    Should Be Equal As Strings    ${selector}[acceleratorModel]    ${TEST_PROFILE_ACCELERATOR_MODEL}
    ...    msg=Default selector does not carry the submitted accelerator model
    Should Be Equal As Strings    ${selector}[acceleratorCount]    ${TEST_PROFILE_ACCELERATOR_COUNT}
    ...    msg=Default selector does not carry the submitted accelerator count
    Should Be Equal As Strings    ${selector}[precision]    ${TEST_PROFILE_PRECISION}
    ...    msg=Default selector does not carry the submitted precision
    Should Be Equal As Strings    ${selector}[metric]    ${TEST_PROFILE_METRIC}
    ...    msg=Default selector does not carry the submitted metric
    ${overrides}=    Get From Dictionary    ${profiles}    overrides    default=&{EMPTY}
    Should Be Equal As Strings    ${overrides}[acceleratorCount]    ${selector}[acceleratorCount]
    ...    msg=Overrides accelerator count disagrees with the narrowed selector (count vs tensor-parallel size)

A deployment pins a Default profile the edit would prune
    [Documentation]    Applies a minimal AIMService pinning a Default-derived profile other than
    ...    the submitted target. Narrowing would prune that profile, so the edit must be refused.
    ...    The service only needs to exist (no GPU / Ready state).
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model Profile    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    default    expected_status=200
    VAR    ${target_profile_name}    ${response.json()}[profile][metadata][name]
    VAR    ${profile_set_name}    ${response.json()}[resourceName]
    Should Not Be Empty    ${target_profile_name}    msg=Default has no effective profile
    ${profile_name}=    Get Different AIMProfile Name For Model
    ...    ${TEST_CUSTOM_MODEL_NAME}    ${target_profile_name}    ${profile_set_name}    ${namespace}
    VAR    ${service_name}    pin-svc-${TEST_CUSTOM_MODEL_NAME}
    Apply AIMService Pinning Profile    ${service_name}    ${TEST_CUSTOM_MODEL_NAME}    ${profile_name}    ${namespace}
    VAR    ${TEST_BLOCKING_AIM_SERVICE}    ${service_name}    scope=TEST

The runtime profile edit should be refused as in use by a deployment
    [Documentation]    The narrowing edit is refused with a conflict when a deployment pins a
    ...    profile the narrowed Default would prune; nothing is written.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    409
    ...    msg=Expected a 409 in-use refusal, got ${TEST_RESPONSE.status_code}: ${TEST_RESPONSE.text}
    VAR    ${blocking_services}    ${TEST_RESPONSE.json()}[additionalInfo][blockingServices]
    Should Not Be Empty    ${blocking_services}    msg=Conflict response did not identify the blocking deployment
    Should Be Equal    ${blocking_services}[0][displayName]    ${TEST_BLOCKING_AIM_SERVICE}
    ...    msg=Conflict response named the wrong blocking deployment
    Custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace
    ${spec}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    spec
    ${profiles}=    Get From Dictionary    ${spec}    profiles
    ${derived_from}=    Get From Dictionary    ${profiles}    derivedFrom
    ${selector}=    Get From Dictionary    ${derived_from}    selector
    Dictionary Should Not Contain Key    ${selector}    acceleratorCount
    ...    msg=Refused edit unexpectedly narrowed the Default selector

The user sets two engine arguments and two environment variables on the model
    [Documentation]    Edit the runtime profile so both the engine-arguments and the
    ...    environment-variable maps carry two key/value pairs, establishing the
    ...    multi-key starting point for the later removal check.
    VAR    ${TEST_KEPT_ARG_KEY}    max-model-len    scope=TEST
    VAR    ${TEST_REMOVED_ARG_KEY}    attention-backend    scope=TEST
    VAR    ${TEST_KEPT_ENV_KEY}    VLLM_ROCM_USE_AITER    scope=TEST
    VAR    ${TEST_REMOVED_ENV_KEY}    VLLM_USE_TRITON_FLASH_ATTN    scope=TEST
    &{engine_args}=    Create Dictionary    ${TEST_KEPT_ARG_KEY}=8192    ${TEST_REMOVED_ARG_KEY}=TRITON_ATTN
    @{engine_env}=    Create List
    ...    ${{ {'name': $TEST_KEPT_ENV_KEY, 'value': '1'} }}
    ...    ${{ {'name': $TEST_REMOVED_ENV_KEY, 'value': '1'} }}
    The user edits the model runtime profile maps    ${engine_args}    ${engine_env}

The user removes one engine argument and one environment variable
    [Documentation]    Re-edit the runtime profile keeping only one pair in each map,
    ...    dropping the other; the dropped keys are simply absent from the new maps.
    &{engine_args}=    Create Dictionary    ${TEST_KEPT_ARG_KEY}=8192
    @{engine_env}=    Create List    ${{ {'name': $TEST_KEPT_ENV_KEY, 'value': '1'} }}
    The user edits the model runtime profile maps    ${engine_args}    ${engine_env}

The user edits the model runtime profile maps
    [Documentation]    PATCH the onboarded model with the given engineArgs map and
    ...    engineEnv name/value entries, mirroring the edit wizard's customProfile body.
    [Arguments]    ${engine_args}    ${engine_env}
    ${namespace}=    Get Project Namespace
    &{custom_profile}=    Create Dictionary    engineArgs=${engine_args}    engineEnv=${engine_env}
    &{body}=    Create Dictionary    customProfile=${custom_profile}
    ${response}=    Patch Onboarded Model    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${body}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    ...    msg=Runtime profile edit failed: ${TEST_RESPONSE.status_code} ${TEST_RESPONSE.text}

The model runtime profile should carry both engine arguments and both environment variables
    ${overrides}=    Get onboarded model overrides
    ${args}=    Get From Dictionary    ${overrides}    engineArgs    default=&{EMPTY}
    Dictionary Should Contain Key    ${args}    ${TEST_KEPT_ARG_KEY}
    Dictionary Should Contain Key    ${args}    ${TEST_REMOVED_ARG_KEY}
    ${env}=    Get From Dictionary    ${overrides}    engineEnv    default=&{EMPTY}
    Dictionary Should Contain Key    ${env}    ${TEST_KEPT_ENV_KEY}
    Dictionary Should Contain Key    ${env}    ${TEST_REMOVED_ENV_KEY}

The model runtime profile should retain only the kept engine argument and environment variable
    [Documentation]    The dropped keys must be gone from the live AIMModel overrides;
    ...    the kept keys must remain. Polled because the edit writes the CR and the
    ...    derived AIMProfile under one lock before the read sees the result.
    Wait Until Keyword Succeeds    30 sec    5 sec
    ...    Onboarded model overrides should drop the removed runtime keys

Onboarded model overrides should drop the removed runtime keys
    ${overrides}=    Get onboarded model overrides
    ${args}=    Get From Dictionary    ${overrides}    engineArgs    default=&{EMPTY}
    Dictionary Should Contain Key    ${args}    ${TEST_KEPT_ARG_KEY}
    Dictionary Should Not Contain Key    ${args}    ${TEST_REMOVED_ARG_KEY}
    ...    msg=Removed engine argument '${TEST_REMOVED_ARG_KEY}' still present after edit
    ${env}=    Get From Dictionary    ${overrides}    engineEnv    default=&{EMPTY}
    Dictionary Should Contain Key    ${env}    ${TEST_KEPT_ENV_KEY}
    Dictionary Should Not Contain Key    ${env}    ${TEST_REMOVED_ENV_KEY}
    ...    msg=Removed environment variable '${TEST_REMOVED_ENV_KEY}' still present after edit

Get onboarded model overrides
    [Documentation]    Resolve the onboarded AIMModel CR fresh from the cluster and
    ...    return its ``spec.profiles.overrides`` block (camelCase keys).
    Custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace
    ${spec}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    spec
    ${profiles}=    Get From Dictionary    ${spec}    profiles    default=&{EMPTY}
    ${overrides}=    Get From Dictionary    ${profiles}    overrides    default=&{EMPTY}
    RETURN    ${overrides}

Get onboarded model annotations
    [Documentation]    Resolve the onboarded AIMModel CR fresh from the cluster and return its
    ...    ``metadata.annotations``. Precision is pruned from spec.profiles.overrides by the
    ...    AIMModel CRD, so the chosen precision is read back from an annotation here.
    Custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace
    ${metadata}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    metadata
    ${annotations}=    Get From Dictionary    ${metadata}    annotations    default=&{EMPTY}
    RETURN    ${annotations}

A custom model is onboarded with a non-default runtime profile
    [Documentation]    Preview and onboard the public test repo with a non-default
    ...    ``customProfile`` (precision plus one engine argument and one engine env var)
    ...    layered on the onboard image, then resolve the AIMModel name for later steps.
    ...    The overrides land on ``AIMModel.spec.profiles.overrides``; aim-engine bakes
    ...    them into the emitted AIMProfile. The chosen values are remembered in
    ...    ``TEST_PROFILE_*`` so the round-trip can assert them on the live pod.
    ...    Sets: TEST_CUSTOM_MODEL_NAME, TEST_PROFILE_*.
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    VAR    ${TEST_PROFILE_PRECISION}    fp16    scope=TEST
    VAR    ${TEST_PROFILE_ENGINE_ARG_KEY}    max-model-len    scope=TEST
    VAR    ${TEST_PROFILE_ENGINE_ARG_VALUE}    8192    scope=TEST
    VAR    ${TEST_PROFILE_ENGINE_ENV_KEY}    VLLM_LOGGING_LEVEL    scope=TEST
    VAR    ${TEST_PROFILE_ENGINE_ENV_VALUE}    DEBUG    scope=TEST
    &{engine_args}=    Create Dictionary    ${TEST_PROFILE_ENGINE_ARG_KEY}=${TEST_PROFILE_ENGINE_ARG_VALUE}
    @{engine_env}=    Create List    ${{ {'name': $TEST_PROFILE_ENGINE_ENV_KEY, 'value': $TEST_PROFILE_ENGINE_ENV_VALUE} }}
    &{custom_profile}=    Create Dictionary
    ...    precision=${TEST_PROFILE_PRECISION}
    ...    engineArgs=${engine_args}
    ...    engineEnv=${engine_env}
    ${accelerator}=    The cluster's GPU accelerator model
    IF    "${accelerator}" != ""
        Set To Dictionary    ${custom_profile}    acceleratorModel=${accelerator}
    END
    ${namespace}=    Get Project Namespace
    ${preview_json}=    Get Variable Value    ${TEST_PREVIEW_JSON}    ${None}
    IF    $preview_json is None
        VAR    ${preview_json}    ${TEST_RESPONSE.json()}
    END
    ${response}=    Onboard Custom Model From Preview
    ...    ${namespace}
    ...    ${preview_json}
    ...    ${CUSTOM_MODELS_ONBOARD_IMAGE}
    ...    custom_profile=${custom_profile}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    204
    ...    msg=Onboard with runtime profile failed: ${TEST_RESPONSE.status_code} ${TEST_RESPONSE.text}
    Custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace
    ${metadata}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    metadata
    ${model_name}=    Get From Dictionary    ${metadata}    name
    Set Test Variable    ${TEST_CUSTOM_MODEL_NAME}    ${model_name}
    ${namespace}=    Get Project Namespace
    Track Custom Model For Cleanup    ${namespace}    ${model_name}

The user revises the model's engine settings
    [Documentation]    Edit the runtime profile after onboard, changing the engine
    ...    argument value and the engine env value, so the round-trip proves the
    ...    *edited* values — not just the onboard values — reach the running pod.
    ...    Requires: TEST_CUSTOM_MODEL_NAME, TEST_PROFILE_* (from onboard).
    VAR    ${TEST_PROFILE_ENGINE_ARG_VALUE}    4096    scope=TEST
    VAR    ${TEST_PROFILE_ENGINE_ENV_VALUE}    INFO    scope=TEST
    &{engine_args}=    Create Dictionary    ${TEST_PROFILE_ENGINE_ARG_KEY}=${TEST_PROFILE_ENGINE_ARG_VALUE}
    @{engine_env}=    Create List    ${{ {'name': $TEST_PROFILE_ENGINE_ENV_KEY, 'value': $TEST_PROFILE_ENGINE_ENV_VALUE} }}
    The user edits the model runtime profile maps    ${engine_args}    ${engine_env}

The model runtime profile should carry the revised engine settings
    [Documentation]    The edited engine argument and env values are visible on the live
    ...    AIMModel overrides. Polled because the edit writes the CR and the derived
    ...    AIMProfile under one lock before the read sees the result.
    Wait Until Keyword Succeeds    30 sec    5 sec
    ...    Onboarded model overrides should carry the revised engine settings

Onboarded model overrides should carry the revised engine settings
    ${overrides}=    Get onboarded model overrides
    ${args}=    Get From Dictionary    ${overrides}    engineArgs    default=&{EMPTY}
    Should Be Equal As Strings    ${args}[${TEST_PROFILE_ENGINE_ARG_KEY}]    ${TEST_PROFILE_ENGINE_ARG_VALUE}
    ...    msg=Edited engine argument not persisted on the model overrides
    ${env}=    Get From Dictionary    ${overrides}    engineEnv    default=&{EMPTY}
    Should Be Equal As Strings    ${env}[${TEST_PROFILE_ENGINE_ENV_KEY}]    ${TEST_PROFILE_ENGINE_ENV_VALUE}
    ...    msg=Edited engine env var not persisted on the model overrides

The running inference pod should reflect the model's runtime profile
    [Documentation]    Assert the live inference pod actually runs the onboarded and edited
    ...    runtime profile: the onboard image, the accelerator product and count the derived
    ...    AIMProfile resolved to, and the edited engine argument. The edited engine env var
    ...    is asserted on the resolved AIMProfile spec because some runtimes consume it from
    ...    profile config rather than exposing it directly in pod env entries; likewise,
    ...    engineArgs may be consumed by the runtime launcher instead of surfacing as pod
    ...    command/args tokens. The accelerator
    ...    expectations are read from the derived AIMProfile rather than hardcoded, so the
    ...    assertion holds on whatever hardware aim-engine selected for the model.
    ...    Requires: TEST_AIM_ID, TEST_CUSTOM_MODEL_NAME, TEST_PROFILE_*.
    ${namespace}=    Get Project Namespace
    ${profile_spec}=    Get AIMProfile Spec For Model    ${TEST_CUSTOM_MODEL_NAME}    ${namespace}
    ${accelerator_count}=    Get From Dictionary    ${profile_spec}    acceleratorCount
    ${accelerator_product}=    Get From Dictionary    ${profile_spec}    acceleratorModel
    The running inference pod should use image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    The running inference pod should request ${accelerator_count} accelerators
    The running inference pod should run on "${accelerator_product}" accelerators
    ${profile_env}=    Get From Dictionary    ${profile_spec}    engineEnv    default=&{EMPTY}
    Should Be Equal As Strings    ${profile_env}[${TEST_PROFILE_ENGINE_ENV_KEY}]    ${TEST_PROFILE_ENGINE_ENV_VALUE}
    ...    msg=Edited engine env var not present on resolved AIMProfile spec
    ${profile_args}=    Get From Dictionary    ${profile_spec}    engineArgs    default=&{EMPTY}
    Should Be Equal As Strings    ${profile_args}[${TEST_PROFILE_ENGINE_ARG_KEY}]    ${TEST_PROFILE_ENGINE_ARG_VALUE}
    ...    msg=Edited engine argument not present on resolved AIMProfile spec

The model should show display name "${display_name}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Should Be Equal    ${json}[displayName]    ${display_name}

The model should show tags "${tags_csv}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${expected_tags}=    Split String    ${tags_csv}    ,
    Should Be Equal    ${json}[tags]    ${expected_tags}

The model should show description "${description}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    Should Be Equal    ${json}[description]    ${description}

Model description should be empty
    [Documentation]    Asserts the PATCH response carries an empty description,
    ...    confirming the empty-string clear semantic worked.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    VAR    ${json}    ${TEST_RESPONSE.json()}
    ${description}=    Get From Dictionary    ${json}    description    default=${EMPTY}
    Should Be Empty    ${description}
    ...    msg=PATCH with empty description must clear the field; got '${description}'

The model patch response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

A copy of the onboarded custom model is created in the project
    [Documentation]    Calls the copy API for the onboarded model then walks the
    ...    namespace model list to resolve the new copy's CR name into
    ...    ${TEST_COPY_MODEL_NAME}. The copy endpoint is synchronous, so the copy
    ...    is immediately visible in the list after a 204 response.
    ${namespace}=    Get Project Namespace
    ${copy_response}=    Copy Custom Model    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    expected_status=204
    ${list_response}=    List Custom Models    ${namespace}    expected_status=200
    ${models}=    Get From Dictionary    ${list_response.json()}    data
    FOR    ${model}    IN    @{models}
        ${name}=    Get From Dictionary    ${model}[metadata]    name
        IF    "${name}" != "${TEST_CUSTOM_MODEL_NAME}"
            VAR    ${TEST_COPY_MODEL_NAME}    ${name}    scope=TEST
        END
    END
    Should Not Be Empty    ${TEST_COPY_MODEL_NAME}
    ...    msg=Copy model CR not found in list after copy (original=${TEST_CUSTOM_MODEL_NAME}, copy_status=${copy_response.status_code})
    Track Custom Model For Cleanup    ${namespace}    ${TEST_COPY_MODEL_NAME}

The copied AIMModel should use runtime family from image "${expected_image}"
    [Documentation]    The copy must keep the source model's selected runtime family
    ...    and container image, not fall back to hardware-default discovery.
    ${namespace}=    Get Project Namespace
    Should Not Be Empty    ${TEST_COPY_MODEL_NAME}
    ...    msg=No copied model name recorded; create the copy first
    AIMModel Should Use Runtime Family From Image    ${TEST_COPY_MODEL_NAME}    ${namespace}    ${expected_image}

The user attempts to rename the copy to "${display_name}"
    [Documentation]    PATCH the copied model's display name. Used to trigger a
    ...    conflict when the target name is already held by the original.
    ${namespace}=    Get Project Namespace
    &{body}=    Create Dictionary    displayName=${display_name}
    ${response}=    Patch Onboarded Model
    ...    ${namespace}
    ...    ${TEST_COPY_MODEL_NAME}
    ...    ${body}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

An AIMService referencing the onboarded model exists
    [Documentation]    Apply a minimal AIMService CR pointing at the onboarded model so
    ...    the delete guard has an active deployment to block on.
    ${namespace}=    Get Project Namespace
    VAR    ${service_name}    blocking-svc-${TEST_CUSTOM_MODEL_NAME}
    Apply AIMService Referencing Model    ${service_name}    ${TEST_CUSTOM_MODEL_NAME}    ${namespace}
    Set Test Variable    ${TEST_BLOCKING_AIM_SERVICE}    ${service_name}

Remove blocking AIMService if present
    [Documentation]    Teardown helper for the delete-conflict test: removes the AIMService CR
    ...    that pins the model behind the 409 delete guard. Without it the model cannot be
    ...    cleaned up and stays in the namespace, polluting every subsequent test. Tolerant of
    ...    a test that failed before the service was created.
    ${service}=    Get Variable Value    ${TEST_BLOCKING_AIM_SERVICE}    ${None}
    IF    $service is None
        RETURN
    END
    ${namespace}=    Get Project Namespace
    Delete AIMService CR    ${service}    ${namespace}

An AIMProfile for the onboarded model exists
    [Documentation]    Wait for aim-engine to derive an AIMProfile from the onboarded
    ...    AIMModel, so the cascade-cleanup assertion after delete is meaningful.
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    3 min    10 sec
    ...    AIMProfile For Model Should Exist    ${TEST_CUSTOM_MODEL_NAME}    ${namespace}

The user deletes the onboarded model
    ${namespace}=    Get Project Namespace
    ${response}=    Delete Custom Model    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Track Custom Model For Cleanup
    [Documentation]    Records a custom model for explicit cleanup at suite teardown.
    ...    Uses lazy initialisation — the tracking list is created on first call.
    ...    The entry format is ``namespace:::name`` so both pieces travel together.
    [Arguments]    ${namespace}    ${model_name}
    ${list}=    Get Variable Value    ${CREATED_CUSTOM_MODELS}    ${None}
    IF    $list is None
        @{list}=    Create List
        Set Suite Variable    @{CREATED_CUSTOM_MODELS}    @{list}
    END
    Append To List    ${CREATED_CUSTOM_MODELS}    ${namespace}:::${model_name}
    Stamp Custom Model With This Run    ${namespace}    ${model_name}

Stamp Custom Model With This Run
    [Documentation]    Labels a custom model with this invocation's run id so a later run's
    ...    suite setup can tell it from a live run's. Applied wherever the suite resolves the
    ...    model it just onboarded, so every successful-onboard path is covered, not only the
    ...    ones that track the model for teardown. Idempotent.
    [Arguments]    ${namespace}    ${model_name}
    ${run_id}=    Get Variable Value    ${CUSTOM_MODELS_RUN_ID}    ${EMPTY}
    IF    "${run_id}" != ""
        Stamp AIMModel With Run Id    ${model_name}    ${namespace}    ${run_id}
    END

Clean Up All Created Custom Models
    [Documentation]    Deletes every custom model tracked during the suite.
    ...    Call this before ``Clean Up All Created Projects`` so models are removed
    ...    explicitly rather than relying solely on namespace cascade — the cascade
    ...    still acts as a final safety net.
    ...    Tolerant of already-deleted or never-created models.
    ${list}=    Get Variable Value    ${CREATED_CUSTOM_MODELS}    ${None}
    IF    $list is None
        Log    No custom models tracked for cleanup    DEBUG
        RETURN
    END
    ${count}=    Get Length    ${list}
    IF    ${count} == 0
        Log    No custom models tracked for cleanup    DEBUG
        RETURN
    END
    Log    Cleaning up ${count} custom model(s)    INFO
    FOR    ${entry}    IN    @{list}
        ${parts}=    Split String    ${entry}    :::
        ${namespace}=    Set Variable    ${parts}[0]
        ${model_name}=    Set Variable    ${parts}[1]
        TRY
            Delete Custom Model    ${namespace}    ${model_name}    expected_status=any
            Log    Requested delete of custom model ${model_name} from ${namespace}    DEBUG
        EXCEPT    AS    ${err}
            Log    Could not delete custom model ${model_name} (${namespace}): ${err}    WARN
        END
    END
    # AIMModel deletion is asynchronous: the API returns immediately but a finalizer
    # holds the CR in Terminating while object storage is cleaned. As a per-test
    # teardown this keyword must leave the namespace empty for the next test, so wait
    # for each CR to actually disappear rather than only requesting the delete.
    FOR    ${entry}    IN    @{list}
        ${parts}=    Split String    ${entry}    :::
        ${namespace}=    Set Variable    ${parts}[0]
        ${model_name}=    Set Variable    ${parts}[1]
        TRY
            Wait Until Keyword Succeeds    90 sec    5 sec
            ...    AIMModel CR Should Be Absent    ${model_name}    ${namespace}
        EXCEPT    AS    ${err}
            Log    Custom model ${model_name} (${namespace}) still present after delete: ${err}    WARN
        END
    END
    @{empty}=    Create List
    Set Suite Variable    ${CREATED_CUSTOM_MODELS}    ${empty}
    Log    Custom model cleanup complete    INFO

Leftover custom models in the shared test project are swept or reported
    [Documentation]    Suite-setup handling of state a previous run left behind. A run that ends
    ...    before its teardown (a group killed at its time budget) leaves a deployment pinning a
    ...    custom model, which then cannot be deleted; every later teardown spends its full wait
    ...    on it and the suite overruns.
    ...
    ...    The project is shared and nothing about a model's age or contents tells an abandoned one
    ...    from one in use, so deletion rests on an explicit stamp. Every model this suite creates
    ...    is labeled with this invocation's run id (``Track Custom Model For Cleanup``). Dispatched
    ...    CI runs are serialized per runner, so a model stamped by a DIFFERENT CI run (swept from a
    ...    CI run; local invocations are never swept nor swept for) belongs to a run that has finished: it and the deployments pinning it are removed through the API
    ...    (undeploy, wait, then delete), as a user would. A model with no stamp - created by an
    ...    older suite version, or created but never labeled because the run died in between - proves
    ...    nothing, so it is only reported, never deleted. Models and deployments are left alone
    ...    unless their model carries another run's stamp.
    ${ci_run_id}=    Get Variable Value    ${E2E_CI_RUN_ID}    ${EMPTY}
    ${run_id}=    New E2E Run Id    ${ci_run_id}
    VAR    ${CUSTOM_MODELS_RUN_ID}    ${run_id}    scope=SUITE
    ${namespace}=    Test Name    testing
    TRY
        ${models_response}=    List Custom Models    ${namespace}    expected_status=any
        IF    ${models_response.status_code} != 200    RETURN
        VAR    ${models}    ${models_response.json()}[data]
        IF    not ${models}
            # The list endpoint answers 200 with an empty list when its own Kubernetes read fails,
            # so confirm emptiness against Kubernetes; a disagreement lands in the WARN below.
            No Custom AIMModel CRs Should Remain    ${namespace}
            RETURN
        END
        ${deployments}=    All inference deployments in the project    ${namespace}
        ${unstamped}=    Models Without A Run Stamp    ${models}
        IF    ${unstamped}
            ${names}=    Evaluate    [m["metadata"]["name"] for m in $unstamped]
            Log    ${namespace} holds ${{len($names)}} custom model(s) no run claimed, so they are left alone: ${names}. If one is pinned by a deployment its cleanup will wait out its full timeout.    WARN
        END
        ${unswept}=    Models Stamped By An Unswept Run    ${models}    ${run_id}
        IF    ${unswept}
            ${names}=    Evaluate    [m["metadata"]["name"] for m in $unswept]
            Log    ${namespace} holds ${{len($names)}} custom model(s) from a run that may still be live (local invocations are not serialized with CI), so they are left alone: ${names}.    WARN
        END
        ${stale}=    Models Stamped By Another Run    ${models}    ${run_id}
        IF    not ${stale}    RETURN
        ${service_ids}=    Deployment Ids Pinning Custom Models    ${deployments}    ${stale}
        FOR    ${service_id}    IN    @{service_ids}
            Log    Removing deployment ${service_id} left by a finished run from ${namespace}    WARN
            Undeploy AIM    ${service_id}    ${namespace}    expected_status=any
        END
        FOR    ${service_id}    IN    @{service_ids}
            Wait Until Keyword Succeeds    5 min    5 sec
            ...    AIM service should be gone    ${service_id}    ${namespace}
        END
        FOR    ${model}    IN    @{stale}
            Log    Removing custom model ${model}[metadata][name] left by a finished run from ${namespace}    WARN
            Delete Custom Model    ${namespace}    ${model}[metadata][name]    expected_status=any
        END
        FOR    ${model}    IN    @{stale}
            Wait Until Keyword Succeeds    5 min    5 sec
            ...    AIMModel CR Should Be Absent    ${model}[metadata][name]    ${namespace}
        END
    EXCEPT    AS    ${err}
        Log    Could not finish handling leftover custom models in ${namespace}: ${err}    WARN
    END

AIM service should be gone
    [Arguments]    ${service_id}    ${namespace}
    ${response}=    Get AIM Service    ${service_id}    ${namespace}    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    404
    ...    msg=Deployment ${service_id} still exists in ${namespace}

All inference deployments in the project
    [Documentation]    Every page of the project's deployments. Fails, rather than returning a
    ...    partial list, when the pages run out before the reported total is reached.
    [Arguments]    ${namespace}
    @{deployments}=    Create List
    VAR    ${complete}    ${False}
    FOR    ${page}    IN RANGE    1    201
        ${response}=    List AIM Services    ${namespace}    page=${page}    page_size=100    expected_status=any
        Should Be Equal As Integers    ${response.status_code}    200
        ...    msg=Could not list deployments in ${namespace}: ${response.status_code} ${response.text}
        VAR    ${body}    ${response.json()}
        VAR    ${page_items}    ${body}[data]
        VAR    ${total}    ${body}[pagination][total]
        Append To List    ${deployments}    @{page_items}
        IF    len($deployments) >= $total
            VAR    ${complete}    ${True}
            BREAK
        END
        IF    not $page_items    BREAK
    END
    Should Be True    ${complete}
    ...    msg=Read ${{len($deployments)}} of ${total} deployments in ${namespace}
    RETURN    ${deployments}

Reset Custom Models In Test Project
    [Documentation]    Per-test teardown that leaves the project namespace free of custom
    ...    models so the next test starts from a clean slate, keeping the suite order
    ...    independent. The tracking-based cleanup covers models a test created in a
    ...    secondary project; the namespace sweep covers models onboarded through the raw
    ...    preview→onboard flow, which the tracking list does not capture. Tolerant of a
    ...    test that never established a project.
    ...
    ...    ``strict`` turns every tolerated condition into a failure, for callers that go on
    ...    to reuse the project inside the same test: a model still terminating when the
    ...    window closes, or a namespace that cannot be listed, means the next onboard would
    ...    land on state this keyword was meant to have removed. Teardown callers keep the
    ...    tolerant default so cleanup never masks the test's own failure.
    [Arguments]    ${strict}=${False}
    Clean Up All Created Custom Models
    TRY
        ${namespace}=    Get Project Namespace
    EXCEPT    AS    ${err}
        IF    ${strict}
            Fail    No project namespace to sweep for custom models: ${err}
        END
        Log    No project namespace to sweep for custom models: ${err}    DEBUG
        RETURN
    END
    ${response}=    List Custom Models    ${namespace}    expected_status=any
    IF    ${response.status_code} != 200
        IF    ${strict}
            Fail    Listing custom models in ${namespace} returned ${response.status_code}; cannot confirm the project is clean
        END
        RETURN
    END
    ${models}=    Get From Dictionary    ${response.json()}    data
    @{names}=    Create List
    FOR    ${model}    IN    @{models}
        ${name}=    Get From Dictionary    ${model}[metadata]    name
        Delete Custom Model    ${namespace}    ${name}    expected_status=any
        Append To List    ${names}    ${name}
    END
    FOR    ${name}    IN    @{names}
        TRY
            Wait Until Keyword Succeeds    90 sec    5 sec
            ...    AIMModel CR Should Be Absent    ${name}    ${namespace}
        EXCEPT    AS    ${err}
            IF    ${strict}
                Fail    Custom model ${name} (${namespace}) still present after delete: ${err}
            END
            Log    Custom model ${name} (${namespace}) still present after delete: ${err}    WARN
        END
    END
    IF    ${strict}
        # The list endpoint answers 200 with an empty data list when its Kubernetes read fails,
        # so an empty response above cannot on its own prove the project is clean. Confirm
        # against Kubernetes before a caller reuses the project inside the same test.
        Wait Until Keyword Succeeds    90 sec    5 sec
        ...    No Custom AIMModel CRs Should Remain    ${namespace}
    END

The user attempts to delete custom model "${model_name}"
    ${namespace}=    Get Project Namespace
    ${response}=    Delete Custom Model    ${namespace}    ${model_name}
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Custom model delete response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

The onboarded AIMModel should no longer exist in the namespace
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    60 sec    5 sec
    ...    AIMModel CR Should Be Absent    ${TEST_CUSTOM_MODEL_NAME}    ${namespace}

The onboarded model should no longer appear in the project model list
    [Documentation]    The list endpoint is the API-level observable that both the CR and
    ...    its S3 manifest mirror are gone; a deleted model must not be listed.
    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Models    ${namespace}    expected_status=200
    ${models}=    Get From Dictionary    ${response.json()}    data
    FOR    ${model}    IN    @{models}
        ${name}=    Get From Dictionary    ${model}[metadata]    name
        Should Not Be Equal    ${name}    ${TEST_CUSTOM_MODEL_NAME}
        ...    msg=Deleted model ${TEST_CUSTOM_MODEL_NAME} still appears in the project model list
    END

The derived AIMProfile should no longer exist in the namespace
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    AIMProfile For Model Should Be Absent    ${TEST_CUSTOM_MODEL_NAME}    ${namespace}

The delete conflict response should name the blocking AIMService
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    409
    ${detail}=    Get From Dictionary    ${TEST_RESPONSE.json()}    detail
    Should Contain    ${detail}    ${TEST_BLOCKING_AIM_SERVICE}
    ...    msg=409 conflict detail should name the blocking AIMService

The onboarded AIMModel should still exist in the namespace
    Custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace

Custom model onboarding status should be "${target_status}"
    [Documentation]    Polls custom model detail until phase.state reaches the target.
    ...    Requires: TEST_CUSTOM_MODEL_NAME.
    Should Not Be Empty    ${TEST_CUSTOM_MODEL_NAME}
    ...    msg=No custom model name set — call "A custom model is onboarded in the project" first
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    10 min    10 sec
    ...    Custom model status should be    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${target_status}

Custom model status should be
    [Documentation]    Single-poll helper for onboarding status checks.
    [Arguments]    ${namespace}    ${model_name}    ${target_status}
    ${response}=    Get Custom Model    ${namespace}    ${model_name}    expected_status=200
    ${phase}=    Get From Dictionary    ${response.json()}    phase
    ${state}=    Get From Dictionary    ${phase}    state
    Should Be Equal    ${state}    ${target_status}
    ...    msg=Custom model onboarding state is ${state} (waiting for ${target_status})

Custom model is deployed as an AIM service
    [Documentation]    Deploys the onboarded custom model through the shared inference endpoint.
    ...    Sends only non-profile deploy fields (e.g. replicas). Runtime settings were
    ...    written to the namespace AIMProfile via model settings at onboard/edit time.
    ...    Requires: TEST_CUSTOM_MODEL_NAME
    ...    Sets: TEST_AIM_ID
    Should Not Be Empty    ${TEST_CUSTOM_MODEL_NAME}
    ...    msg=No custom model name set — call "A custom model is onboarded in the project" first
    ${namespace}=    Get Project Namespace
    ${existing}=    Find Existing Custom AIM Service    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}
    IF    $existing != $None
        ${service_id}=    Get From Dictionary    ${existing}    id
        VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST
        RETURN
    END
    ${deploy_data}=    Create Dictionary    replicas=${1}
    ${response}=    Deploy AIM    ${TEST_CUSTOM_MODEL_NAME}    ${deploy_data}    ${namespace}    expected_status=202
    VAR    ${json}    ${response.json()}
    ${service_id}=    Get From Dictionary    ${json}    id
    VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST

Custom model is deployed as an AIM service with display name
    [Documentation]    Deploys the onboarded custom model with a user-entered display name.
    ...    Requires: TEST_CUSTOM_MODEL_NAME
    ...    Sets: TEST_AIM_ID, TEST_AIM_DISPLAY_NAME
    [Arguments]    ${display_name}
    Should Not Be Empty    ${TEST_CUSTOM_MODEL_NAME}
    ...    msg=No custom model name set — call "A custom model is onboarded in the project" first
    ${namespace}=    Get Project Namespace
    ${deploy_data}=    Create Dictionary    replicas=${1}    displayName=${display_name}
    ${response}=    Deploy AIM    ${TEST_CUSTOM_MODEL_NAME}    ${deploy_data}    ${namespace}    expected_status=202
    VAR    ${json}    ${response.json()}
    ${service_id}=    Get From Dictionary    ${json}    id
    VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST
    VAR    ${TEST_AIM_DISPLAY_NAME}    ${display_name}    scope=TEST

Custom model is deployed with the profile the user selected
    [Documentation]    Deploys the onboarded custom model asking for the profile the user
    ...    added, sending the identifier the profile list reports rather than an
    ...    engine-generated profile name.
    ...    Requires: TEST_CUSTOM_MODEL_NAME, TEST_SELECTED_PROFILE
    ...    Sets: TEST_AIM_ID
    ${namespace}=    Get Project Namespace
    ${deploy_data}=    Create Dictionary    replicas=${1}    profileName=${TEST_SELECTED_PROFILE}
    ${response}=    Deploy AIM    ${TEST_CUSTOM_MODEL_NAME}    ${deploy_data}    ${namespace}    expected_status=202
    ${service_id}=    Get From Dictionary    ${response.json()}    id
    VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST

Custom model is deployed and running on profile "${profile}"
    [Documentation]    Deploys the onboarded custom model on the given profile identifier and waits
    ...    until that deployment is Running, so several deployments of one model — each on its own
    ...    profile — can be stood up in turn. Retargets TEST_AIM_ID at the new deployment before
    ...    waiting, so the running check follows the deployment this call created.
    ...    Requires: TEST_CUSTOM_MODEL_NAME
    ...    Sets: TEST_AIM_ID
    ${namespace}=    Get Project Namespace
    ${deploy_data}=    Create Dictionary    replicas=${1}    profileName=${profile}
    ${response}=    Deploy AIM    ${TEST_CUSTOM_MODEL_NAME}    ${deploy_data}    ${namespace}    expected_status=202
    ${service_id}=    Get From Dictionary    ${response.json()}    id
    VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST
    Deployed AIM reaches Running state

The deployment should serve the profile the user chose
    [Documentation]    The AIMService must pin the profile derived from the set the user
    ...    selected, so the deployment serves the configuration that was asked for.
    The deployment should serve the profile identified by    ${TEST_SELECTED_PROFILE}

The user deploys the custom model asking for a profile that does not exist
    [Documentation]    Records the service id if the refusal ever regresses into a deploy, so
    ...    teardown can undeploy it. A leaked AIMService blocks deleting the model it
    ...    references, which would strand both resources for every later test.
    ...    Sets: TEST_RESPONSE, and TEST_AIM_ID only on an unexpected deploy
    ${namespace}=    Get Project Namespace
    ${deploy_data}=    Create Dictionary    replicas=${1}    profileName=no-such-profile
    ${response}=    Deploy AIM    ${TEST_CUSTOM_MODEL_NAME}    ${deploy_data}    ${namespace}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    IF    ${response.status_code} == 202
        VAR    ${TEST_AIM_ID}    ${response.json()}[id]    scope=TEST
    END

The deploy should be refused as an unknown profile
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    400
    Should Contain    ${TEST_RESPONSE.json()}[detail]    no-such-profile
    ...    msg=Refusal should name the profile that could not be found

The base template offers at least one precision
    [Documentation]    Records every precision the project's base template emits in
    ...    ${TEST_OFFERED_PRECISIONS}, so the deploy precision-selection path can be exercised
    ...    against all of them. A single-precision template is a valid (and expected)
    ...    configuration - the deployed profile must still pin the onboarded precision - so the
    ...    test runs with one or more precisions and only skips when the template emits none at
    ...    all. The endpoint is fail-open - it reports no precisions when its own base-profile
    ...    read fails - so an empty answer is cross-checked against Kubernetes before skipping,
    ...    rather than letting a read outage quietly retire the coverage this test exists for.
    ...    The cross-check asks whether any base profile declares a precision, not whether any
    ...    base profile exists: precision is optional, so a template can emit profiles and
    ...    still genuinely offer no precision target.
    ...
    ...    An empty answer also means "the base model has not emitted its profiles yet", which
    ...    the endpoint documents and which a project created moments ago will hit, so the
    ...    options are polled until they settle rather than skipping on the first empty read.
    ${namespace}=    Get Project Namespace
    TRY
        ${precisions}=    Wait Until Keyword Succeeds    2 min    5 sec
        ...    The base template's offered precisions    ${namespace}
    EXCEPT    AS    ${error}
        Log    Base template still offers no precision after waiting: ${error}    INFO
        No Base Role AIMProfile Should Declare A Precision    ${namespace}
        Skip    Base template offers no precision; cannot exercise deploy precision selection
    END
    VAR    @{TEST_OFFERED_PRECISIONS}    @{precisions}    scope=TEST
    ${required_gpus}=    Largest Accelerator Count For Precisions    ${precisions}    ${namespace}
    VAR    ${TEST_REQUIRED_GPU_COUNT}    ${required_gpus}    scope=TEST

Project quota covers every offered precision
    [Documentation]    Sizes the project's GPU quota to the largest accelerator count any offered
    ...    precision is emitted at. Precisions are not interchangeable across counts - a base
    ...    template can emit fp16 at one accelerator and fp8 only at eight - so a fixed quota
    ...    would starve that round and fail the test instead of covering the precision. Rounds
    ...    deploy one at a time behind the strict teardown barrier, so the largest single round
    ...    is the whole requirement.
    ...
    ...    The size comes from the base-role AIMProfiles themselves, not the options endpoint:
    ...    that endpoint is fail-open and its combinations omit tuples that do not resolve to a
    ...    single base profile, either of which would quietly under-size the quota.
    ...    Requires: TEST_REQUIRED_GPU_COUNT
    Project quota is set to    gpu_count=${TEST_REQUIRED_GPU_COUNT}

The base template's offered precisions
    [Documentation]    Single-poll helper: returns the precisions the base template emits, once
    ...    it emits any. Fails while the list is still empty so a caller can wait out the
    ...    base model's profile emission instead of reading "not ready yet" as "offers none".
    [Arguments]    ${namespace}
    ${response}=    Get Runtime Profile Options    ${namespace}    expected_status=200
    ${precisions}=    Get From Dictionary    ${response.json()}    precisions    default=@{EMPTY}
    Should Not Be Empty    ${precisions}
    ...    msg=The base model has not emitted a precision-bearing profile yet
    RETURN    ${precisions}

The custom model is onboarded and deployed at each offered precision
    [Documentation]    Runs one onboard-deploy round per offered precision and records the
    ...    profile each round's deployment pinned, so the assertion can be made for every
    ...    precision rather than a single sampled one. Every round onboards the same source,
    ...    which the API folds into one AIMModel rather than a second CR, so each round must
    ...    start from a project the previous round has actually finished tearing down -
    ...    hence the strict reset barrier, which fails rather than letting a round race its
    ...    onboard against the previous model's deletion. Tearing down between rounds also
    ...    keeps only one deployment holding project GPU quota at a time.
    ...    Requires: TEST_OFFERED_PRECISIONS
    ...    Sets: TEST_PINNED_PROFILE_BY_PRECISION
    ${namespace}=    Get Project Namespace
    ${pinned}=    Create Dictionary
    ${rounds}=    Get Length    ${TEST_OFFERED_PRECISIONS}
    FOR    ${index}    ${precision}    IN ENUMERATE    @{TEST_OFFERED_PRECISIONS}
        TRY
            VAR    ${TEST_TARGET_PRECISION}    ${precision}    scope=TEST
            A custom model is onboarded at the target precision
            Custom model onboarding status should be "Ready"
            Custom model is deployed as an AIM service
            # Capture the Kubernetes name before anything that can fail: without it, the
            # failure path's cleanup cannot verify the predictor is gone and skips the check.
            Wait Until Keyword Succeeds    30 sec    3 sec
            ...    The deployed custom model's Kubernetes name is captured
            ${profile_name}=    Wait Until Keyword Succeeds    30 sec    3 sec
            ...    Deployed AIM service pinned profile name    ${namespace}    ${TEST_AIM_ID}
            ${declared}=    AIMProfile Precision    ${profile_name}    ${namespace}
            ${round}=    Create Dictionary    profile=${profile_name}    precision=${declared}
            Set To Dictionary    ${pinned}    ${precision}    ${round}
        EXCEPT    AS    ${error}
            # Cleanup here is best-effort in full: a failure inside it would otherwise escape
            # and replace the round failure that actually got us here.
            TRY
                The precision round is torn down    strict=${False}
            EXCEPT    AS    ${cleanup_error}
                Log    Cleanup after the failed round did not complete: ${cleanup_error}    WARN
            END
            Fail    Round for precision '${precision}' failed: ${error}
        END
        IF    ${index} + 1 < ${rounds}
            The precision round is torn down
        END
    END
    VAR    &{TEST_PINNED_PROFILE_BY_PRECISION}    &{pinned}    scope=TEST

The precision round is torn down
    [Documentation]    Removes the round's deployment and its custom model so the next round
    ...    starts from an empty project. Strict by default: anything still present when the
    ...    deletion window closes fails the test, because the next round re-onboards the same
    ...    source and would otherwise land on the object still being deleted. A round that
    ...    already failed passes ``strict=${False}``, so cleanup reports what it could not
    ...    remove without masking the failure that got the test here. The final round is left
    ...    to the test's own tolerant teardown - there is no next round for it to corrupt.
    ...
    ...    The deployment handles are cleared only once the removal actually succeeded. A
    ...    tolerated failure leaves them set, so the test's own teardown still has something
    ...    to retry against - clearing them would turn that retry into an immediate return
    ...    and leave the AIMService holding project GPU quota until the suite teardown, since
    ...    ``Reset Custom Models In Test Project`` sweeps AIMModels and never the service.
    ...
    ...    Strict teardown also waits out the model's derived AIMProfiles, which Kubernetes
    ...    garbage-collects asynchronously after the model goes. The next round re-onboards the
    ...    same source, so a profile still lingering from the previous precision is one the
    ...    deploy resolver could pick.
    [Arguments]    ${strict}=${True}
    IF    ${strict}
        Remove custom model deployment if present
        No AIM service should remain for the custom model
        VAR    ${TEST_AIM_ID}    ${None}    scope=TEST
        VAR    ${TEST_AIM_SERVICE_NAME}    ${None}    scope=TEST
    ELSE
        TRY
            Remove custom model deployment if present
            No AIM service should remain for the custom model
            VAR    ${TEST_AIM_ID}    ${None}    scope=TEST
            VAR    ${TEST_AIM_SERVICE_NAME}    ${None}    scope=TEST
        EXCEPT    AS    ${error}
            Log    Deployment cleanup after a failed round did not complete: ${error}    WARN
        END
    END
    ${model_name}=    Get Variable Value    ${TEST_CUSTOM_MODEL_NAME}    ${None}
    Reset Custom Models In Test Project    strict=${strict}
    IF    ${strict} and $model_name is not None
        ${namespace}=    Get Project Namespace
        Wait Until Keyword Succeeds    90 sec    5 sec
        ...    AIMProfile For Model Should Be Absent    ${model_name}    ${namespace}
    END

No AIM service should remain for the custom model
    [Documentation]    Waits until the API stops listing an AIMService for the round's model.
    ...    Waiting on the predictor Deployment alone is not enough between rounds: the deploy
    ...    keyword reuses any AIMService the list still reports for the model and returns
    ...    without deploying, so a lingering service would let the next precision record the
    ...    previous round's profile as its own coverage.
    ${namespace}=    Get Project Namespace
    ${model_name}=    Get Variable Value    ${TEST_CUSTOM_MODEL_NAME}    ${None}
    IF    $model_name is None
        RETURN
    END
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    The custom model has no listed AIM service    ${namespace}    ${model_name}

The custom model has no listed AIM service
    [Documentation]    Single-poll assertion that no AIMService references the model, read from
    ...    Kubernetes rather than the services list endpoint - that endpoint answers 200 with an
    ...    empty list when its own Kubernetes read fails, so a read outage would look like a
    ...    torn-down service and let the next round reuse the previous one.
    [Arguments]    ${namespace}    ${model_name}
    No AIMService CRs Should Remain For Model    ${model_name}    ${namespace}

Every offered precision should have been served by a profile pinning it
    [Documentation]    Every precision the base template offers must have been deployed, and
    ...    each of those deployments must have pinned an AIMProfile that declares its own
    ...    precision - proving the deploy resolver honours the onboarded precision instead of
    ...    picking an arbitrary profile. Each round records the pinned profile's own
    ...    ``spec.precision`` while that profile still exists, rather than parsing the profile
    ...    name, which aim-engine owns and may change - and rather than reading it back here,
    ...    where every round but the last has already been torn down.
    ...    Requires: TEST_OFFERED_PRECISIONS, TEST_PINNED_PROFILE_BY_PRECISION
    Should Not Be Empty    ${TEST_OFFERED_PRECISIONS}
    ...    msg=No precision was offered, so this assertion would hold vacuously
    ${covered}=    Get Dictionary Keys    ${TEST_PINNED_PROFILE_BY_PRECISION}
    Lists Should Be Equal    ${covered}    ${TEST_OFFERED_PRECISIONS}    ignore_order=True
    ...    msg=Not every offered precision was deployed
    FOR    ${precision}    ${round}    IN    &{TEST_PINNED_PROFILE_BY_PRECISION}
        Should Be Equal    ${round}[precision]    ${precision}
        ...    msg=Deploy resolver picked the wrong profile: onboarded at precision '${precision}' (expected), but pinned profile '${round}[profile]' declares precision '${round}[precision]' (actual)
    END

Deployed AIM service pinned profile name
    [Documentation]    Single-poll helper: returns the AIMService's pinned profile name once it
    ...    reports one, for callers that need the name rather than an assertion about it.
    [Arguments]    ${namespace}    ${service_id}
    ${name}=    Get deployed AIM service profile name    ${namespace}    ${service_id}
    Should Not Be Empty    ${name}
    ...    msg=AIMService ${service_id} has not reported a pinned profile yet
    RETURN    ${name}

A custom model is onboarded at the target precision
    [Documentation]    Previews and onboards the public fixture with ``customProfile.precision``
    ...    set to ${TEST_TARGET_PRECISION}, so the onboarded model records that precision on its
    ...    annotation. Resolves the AIMModel CR name into ${TEST_CUSTOM_MODEL_NAME} and tracks it
    ...    for cleanup.
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    ${accelerator}=    The cluster's GPU accelerator model
    IF    "${accelerator}" != ""
        When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}" and runtime profile overrides
        ...    precision=${TEST_TARGET_PRECISION}
        ...    acceleratorModel=${accelerator}
    ELSE
        When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}" and runtime profile overrides
        ...    precision=${TEST_TARGET_PRECISION}
    END
    Then custom model onboard response status should be "204"
    And custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace
    ${metadata}=    Get From Dictionary    ${CUSTOM_MODEL_AIM_CR}    metadata
    ${model_name}=    Get From Dictionary    ${metadata}    name
    Set Test Variable    ${TEST_CUSTOM_MODEL_NAME}    ${model_name}
    ${namespace}=    Get Project Namespace
    Track Custom Model For Cleanup    ${namespace}    ${model_name}

The profile the user added is ready to serve
    [Documentation]    Behavioral precondition: waits until the profile the user just added has
    ...    reconciled to a servable profile, so it is a real alternative to the Default rather
    ...    than an empty set the resolver could not have picked anyway. Also records the
    ...    identifier clients select the profile by.
    ...    Requires: the response from adding the profile
    ...    Sets: TEST_SELECTED_PROFILE
    VAR    ${TEST_SELECTED_PROFILE}    ${TEST_RESPONSE.json()}[name]    scope=TEST
    Wait Until Keyword Succeeds    3 min    5 sec
    ...    Custom model profile should report a ready profile    ${TEST_SELECTED_PROFILE}

Custom model profile should report a ready profile
    [Documentation]    Single-poll helper: the profile the identifier names must have derived a
    ...    profile, and it must have reconciled to Ready.
    [Arguments]    ${identifier}
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model Profile
    ...    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${identifier}    expected_status=200
    VAR    ${profile}    ${response.json()}[profile]
    Should Not Be Empty    ${profile}    msg=Profile '${identifier}' has no derived profile yet
    Should Be Equal    ${profile}[status][status]    Ready    msg=Profile '${identifier}' is not Ready yet

The added profile should present its accelerator, precision, and metric
    [Documentation]    The symptom of a set whose name overflowed the derived-profile label limit
    ...    was a row with no derived profile, so the UI showed blank accelerator/precision/metric
    ...    cells. A servable profile must surface all three, so the row is never blank.
    ...    Requires: TEST_SELECTED_PROFILE, set by "the profile the user added is ready to serve".
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model Profile
    ...    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${TEST_SELECTED_PROFILE}    expected_status=200
    VAR    ${spec}    ${response.json()}[profile][spec]
    Should Not Be Empty    ${spec}[acceleratorModel]    msg=Added profile is missing its accelerator model
    Should Not Be Empty    ${spec}[precision]    msg=Added profile is missing its precision
    Should Not Be Empty    ${spec}[metric]    msg=Added profile is missing its metric

The deployment should serve the model's Default profile
    [Documentation]    A deploy that named no profile must serve the Default, even though the
    ...    model also has an authored profile that could have been picked up.
    The deployment should serve the profile identified by    default

The deployment should serve the profile identified by
    [Documentation]    Reads the profile the given identifier derives and asserts the AIMService
    ...    pins it — the technical form of "the deployment serves this profile".
    [Arguments]    ${identifier}
    ${namespace}=    Get Project Namespace
    ${response}=    Get Custom Model Profile
    ...    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    ${identifier}    expected_status=200
    VAR    ${expected}    ${response.json()}[profile][metadata][name]
    Wait Until Keyword Succeeds    30 sec    3 sec
    ...    Deployed AIM service profile name should be    ${namespace}    ${TEST_AIM_ID}    ${expected}

Deployed AIM service profile name should be
    [Documentation]    Single-poll helper: the AIMService must pin exactly ``expected``. Exact,
    ...    because the caller knows the profile the deploy had to resolve to, and a sibling
    ...    whose name merely contains it is the wrong profile.
    [Arguments]    ${namespace}    ${service_id}    ${expected}
    ${name}=    Get deployed AIM service profile name    ${namespace}    ${service_id}
    Should Be Equal    ${name}    ${expected}
    ...    msg=Deployed AIMService pinned profile '${name}', expected '${expected}'

Get deployed AIM service profile name
    [Documentation]    Reads ``spec.profile.name`` for the AIMService with the given id.
    [Arguments]    ${namespace}    ${service_id}
    ${response}=    List AIM Services    ${namespace}    expected_status=200
    ${services}=    Get From Dictionary    ${response.json()}    data    default=@{EMPTY}
    FOR    ${svc}    IN    @{services}
        ${sid}=    Get From Dictionary    ${svc}    id    default=${EMPTY}
        IF    "${sid}" == "${service_id}"
            ${spec}=    Get From Dictionary    ${svc}    spec    default=&{EMPTY}
            ${profile}=    Get From Dictionary    ${spec}    profile    default=&{EMPTY}
            ${name}=    Get From Dictionary    ${profile}    name    default=${EMPTY}
            RETURN    ${name}
        END
    END
    Fail    AIMService ${service_id} not found in namespace ${namespace}

Undeploy the custom model AIM service if present
    [Documentation]    Backward-compatible name for deterministic custom-model deployment cleanup.
    Remove custom model deployment if present

The user attempts to deploy custom model with name "${model_name}"
    [Documentation]    Sends a deploy request using an explicit model CR name, allowing
    ...    negative tests to supply names that do not correspond to existing CRs.
    ...    Sets: TEST_RESPONSE.
    ${namespace}=    Get Project Namespace
    ${deploy_data}=    Create Dictionary    replicas=${1}
    ${response}=    Deploy AIM    ${model_name}    ${deploy_data}    ${namespace}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The custom model deploy response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    ${expected_status}

Deployed AIMService should show the deploy display name
    [Documentation]    Verifies the deploy-time display name is persisted on the AIMService
    ...    display-name annotation. Requires: TEST_AIM_ID, TEST_AIM_DISPLAY_NAME.
    Should Not Be Empty    ${TEST_AIM_ID}    msg=No AIM service ID set
    Should Not Be Empty    ${TEST_AIM_DISPLAY_NAME}    msg=No deploy display name set
    ${namespace}=    Get Project Namespace
    ${response}=    Get AIM Service    ${TEST_AIM_ID}    ${namespace}    expected_status=200
    VAR    ${json}    ${response.json()}
    ${metadata}=    Get From Dictionary    ${json}    metadata
    ${annotations}=    Get From Dictionary    ${metadata}    annotations    default=&{EMPTY}
    ${shown_name}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/display-name    default=${EMPTY}
    Should Be Equal    ${shown_name}    ${TEST_AIM_DISPLAY_NAME}
    ...    msg=AIMService display-name annotation is '${shown_name}' (expected '${TEST_AIM_DISPLAY_NAME}')

Find Existing Custom AIM Service
    [Documentation]    Returns an existing AIMService for the custom model, if present.
    [Arguments]    ${namespace}    ${model_name}
    ${services_response}=    List AIM Services    ${namespace}    expected_status=200
    ${services}=    Get From Dictionary    ${services_response.json()}    data
    FOR    ${service}    IN    @{services}
        ${resolved}=    Get From Dictionary    ${service}[spec]    model
        ${resolved_name}=    Get From Dictionary    ${resolved}    name
        IF    "${resolved_name}" == "${model_name}"
            RETURN    ${service}
        END
    END
    RETURN    ${None}

Deployed AIMService should reference the custom model
    [Documentation]    Verifies service spec.model.name points at TEST_CUSTOM_MODEL_NAME.
    Should Not Be Empty    ${TEST_AIM_ID}    msg=No AIM service ID set
    ${namespace}=    Get Project Namespace
    ${response}=    Get AIM Service    ${TEST_AIM_ID}    ${namespace}    expected_status=200
    VAR    ${json}    ${response.json()}
    ${spec}=    Get From Dictionary    ${json}    spec
    ${model}=    Get From Dictionary    ${spec}    model
    ${model_name}=    Get From Dictionary    ${model}    name
    Should Be Equal    ${model_name}    ${TEST_CUSTOM_MODEL_NAME}

Deployed custom model should be accessible for inference
    [Documentation]    Verifies the deployment appears in the chat-capable inference list.
    Should Not Be Empty    ${TEST_AIM_ID}    msg=No AIM service ID set
    ${namespace}=    Get Project Namespace
    ${response}=    List AIM Services    ${namespace}    expected_status=200    capability=chat
    ${services}=    Get From Dictionary    ${response.json()}    data
    FOR    ${service}    IN    @{services}
        ${service_id}=    Get From Dictionary    ${service}    id
        IF    "${service_id}" == "${TEST_AIM_ID}"
            RETURN
        END
    END
    Fail    Custom model AIMService ${TEST_AIM_ID} not found in chat-capable deployments

Chat completion against deployed custom model should succeed
    [Documentation]    Sends a real chat completion request to the deployment's external endpoint.
    ...    Uses an API key assigned to the AIM service for authenticated access.
    Should Not Be Empty    ${TEST_AIM_ID}    msg=No AIM service ID set
    An API key exists and is assigned to AIM
    ${namespace}=    Get Project Namespace
    ${response}=    Get AIM Service    ${TEST_AIM_ID}    ${namespace}    expected_status=200
    ${endpoints}=    Get From Dictionary    ${response.json()}    endpoints
    ${external_host}=    Get From Dictionary    ${endpoints}    external
    Should Not Be Empty    ${external_host}    msg=AIMService should expose an external endpoint
    Api key binding should take effect    host=${external_host}
    ${models}=    List models from external endpoint    ${external_host}    ${TEST_AIM_ID}    ${TEST_API_KEY_VALUE}
    Should Not Be Empty    ${models}    msg=External endpoint should expose at least one model
    ${first_model}=    Get From List    ${models}    0
    ${model_id}=    Get From Dictionary    ${first_model}    id
    ${chat_response}=    Send chat completion request to external endpoint
    ...    ${external_host}
    ...    ${model_id}
    ...    ${TEST_API_KEY_VALUE}
    ...    expected_status=200
    ${choices}=    Get From Dictionary    ${chat_response.json()}    choices
    Should Not Be Empty    ${choices}
    ${message}=    Get From Dictionary    ${choices}[0]    message
    ${content}=    Get From Dictionary    ${message}    content
    Should Not Be Empty    ${content}

Custom model deployment is removed
    [Documentation]    Undeploys the custom model AIMService.
    Should Not Be Empty    ${TEST_AIM_ID}    msg=No AIM service ID set
    ${namespace}=    Get Project Namespace
    ${service}=    Get AIM Service    ${TEST_AIM_ID}    ${namespace}    expected_status=200
    ${metadata}=    Get From Dictionary    ${service.json()}    metadata
    ${service_name}=    Get From Dictionary    ${metadata}    name
    VAR    ${TEST_AIM_SERVICE_NAME}    ${service_name}    scope=TEST
    Undeploy AIM    ${TEST_AIM_ID}    ${namespace}    expected_status=204

Custom model deployment should be removed
    [Documentation]    Verifies the custom model AIMService is gone.
    Should Not Be Empty    ${TEST_AIM_ID}    msg=No AIM service ID set
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    10 sec
    ...    Get AIM Service    ${TEST_AIM_ID}    ${namespace}    expected_status=404

Remove custom model deployment if present
    [Documentation]    Idempotent teardown: undeploy the custom model AIMService when one was
    ...    created in this test, then wait until it is deleted before the next GPU test.
    ...    Tolerates a failure that happened before deploy (no TEST_AIM_ID) and a service
    ...    that is already gone, so teardown never masks the test's own failure. The
    ...    project-deletion suite teardown removes remaining AIMModel and AIMProfile data.
    ${aim_id}=    Get Variable Value    ${TEST_AIM_ID}    ${None}
    IF    $aim_id is None
        RETURN
    END
    ${namespace}=    Get Project Namespace
    ${service_name}=    Get Variable Value    ${TEST_AIM_SERVICE_NAME}    ${None}
    ${service}=    Get AIM Service    ${aim_id}    ${namespace}    expected_status=any
    IF    ${service.status_code} == 404
        # Already gone from the API, so its Kubernetes name can no longer be read back and is
        # only known if an earlier step captured it. Without a name there is nothing to check
        # against — Verify AIM deployment gone would match on a "None-" prefix and pass
        # vacuously — and failing here would mask the test's own failure, which is exactly the
        # tolerance this keyword documents.
        IF    $service_name is None
            Log    Custom model AIM service ${aim_id} was already gone and its Kubernetes name was never captured; skipping predictor verification    WARN
            RETURN
        END
    ELSE
        Should Be Equal As Integers    ${service.status_code}    200
        ...    msg=Unexpected status ${service.status_code} while reading custom model AIM service ${aim_id}
        ${metadata}=    Get From Dictionary    ${service.json()}    metadata
        ${service_name}=    Get From Dictionary    ${metadata}    name
        ${response}=    Undeploy AIM    ${aim_id}    ${namespace}    expected_status=any
        Should Be True    ${response.status_code} in [204, 404, 409]
        ...    msg=Unexpected status ${response.status_code} while undeploying custom model AIM service ${aim_id}
        VAR    ${TEST_AIM_ID}    ${aim_id}    scope=TEST
        Wait for AIM workload to reach state    Deleted    timeout=120    interval=5
    END
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify AIM deployment gone    ${service_name}    ${namespace}

The deployed custom model's Kubernetes name is captured
    [Documentation]    Records the AIMService's Kubernetes resource name (metadata.name) in
    ...    ${TEST_AIM_SERVICE_NAME} without undeploying, so a later direct cleanup call or
    ...    Kubernetes-presence assertion can use the same name "Custom model deployment is
    ...    removed" captures — independent of that keyword's capture-then-undeploy coupling.
    Should Not Be Empty    ${TEST_AIM_ID}    msg=No AIM service ID set
    ${namespace}=    Get Project Namespace
    ${service}=    Get AIM Service    ${TEST_AIM_ID}    ${namespace}    expected_status=200
    ${metadata}=    Get From Dictionary    ${service.json()}    metadata
    ${service_name}=    Get From Dictionary    ${metadata}    name
    VAR    ${TEST_AIM_SERVICE_NAME}    ${service_name}    scope=TEST

The predictor Deployment for the deployed custom model should no longer exist in kubernetes
    [Documentation]    Confirms the predictor Deployment backing the captured Kubernetes name
    ...    has actually disappeared from the cluster. Unlike the generic "AIM deployment
    ...    should not exist in kubernetes" keyword — which trusts a 404 from the API alone and
    ...    skips the kubectl check once the AIMService record is gone — this uses the name
    ...    captured before deletion, so it still verifies real Kubernetes-level absence even
    ...    when the API record has already disappeared.
    Should Not Be Empty    ${TEST_AIM_SERVICE_NAME}
    ...    msg=No captured Kubernetes service name — capture it before calling this keyword
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify AIM deployment gone    ${TEST_AIM_SERVICE_NAME}    ${namespace}

Predictor absence verification should fail while the predictor exists
    [Documentation]    Negative check proving the Kubernetes-level absence assertion has teeth:
    ...    called while the captured custom model's predictor Deployment is still genuinely
    ...    running, it must raise the specific "still exists" error the polling wraps — not
    ...    merely any failure — otherwise an unrelated error (auth, API outage) could satisfy
    ...    this check without ever proving the leak-detection logic itself works. Requires "The
    ...    deployed custom model's Kubernetes name is captured" to have run first.
    Run Keyword And Expect Error
    ...    *The last error was: Deployment matching ${TEST_AIM_SERVICE_NAME}-*-predictor still exists in namespace *
    ...    The predictor Deployment for the deployed custom model should no longer exist in kubernetes

A second ready project with user access exists
    [Documentation]    Creates a second project for namespace isolation checks, preserving
    ...    the first project's namespace in ${TEST_FIRST_PROJECT_NAMESPACE} before
    ...    A ready project with user access exists overwrites ${TEST_PROJECT}.
    ...    Uses a distinct project name so the second namespace is genuinely separate —
    ...    the default name resolves to the shared "testing" project (same namespace),
    ...    which would defeat the isolation check.
    VAR    ${TEST_FIRST_PROJECT_NAMESPACE}    ${TEST_PROJECT}[name]    scope=TEST
    ${second_project_name}=    Test Name    testing-isolation
    A ready project with user access exists    project_name=${second_project_name}

The custom model from the first project should not appear in the second project model list
    [Documentation]    Verifies ${TEST_RESPONSE} (the second project's list) does not
    ...    contain any model whose canonical-repo-id matches the model imported into the
    ...    first project — AIMModel CRs are namespace-scoped so one project cannot see
    ...    another's imports.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    ${models}=    Get From Dictionary    ${TEST_RESPONSE.json()}    data
    FOR    ${model}    IN    @{models}
        ${annotations}=    Get From Dictionary    ${model}[metadata]    annotations    default=&{EMPTY}
        ${canonical}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/canonical-repo-id    default=${EMPTY}
        Should Not Be Equal    ${canonical}    ${CUSTOM_MODELS_PUBLIC_REPO}
        ...    msg=Custom model imported into ${TEST_FIRST_PROJECT_NAMESPACE} should not be visible in the second project
    END
