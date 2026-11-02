# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       E2E coverage for custom-model preview, onboard, list, and detail endpoints.
# Suite Setup discovers a base-image family from the cluster catalog, so every test here dies in
# setup on a cluster that publishes none. Tagging every test is what lets RF prune the suite at
# build time -- before Suite Setup runs -- instead of reporting the whole suite as failures.
Test Tags           needs-aim-images
Suite Setup         Run Keywords    Initialize AIWB Storage Tracking    AND    Leftover custom models in the shared test project are swept or reported    AND    Use discovered cluster onboarding image for custom model tests
Test Teardown       Reset Custom Models In Test Project
Suite Teardown      Run Keywords    Clean Up Prepared S3 Sources For Custom Model Preview    AND    Clean Up All Created AIWB Storages    AND    Clean Up All Created Custom Models    AND    Clean Up All Created Projects With Wait
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource
Resource            resources/aiwb_storages.resource
Resource            resources/aiwb_custom_models.resource
Resource            resources/aiwb_models.resource


*** Test Cases ***
Preview a public custom model by bare repo id
    [Tags]    custom-models    preview    smoke
    Given a ready project with user access exists
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    And custom model preview response should describe model "${CUSTOM_MODELS_PUBLIC_REPO}"

Preview a public custom model via huggingface.co URL with a revision
    [Tags]    custom-models    preview    smoke
    Given a ready project with user access exists
    When a custom model preview is requested for "https://huggingface.co/${CUSTOM_MODELS_PUBLIC_REPO}/tree/main"
    Then custom model preview response status should be "200"
    And custom model preview response should describe model "${CUSTOM_MODELS_PUBLIC_REPO}"
    And custom model preview response revision should be "main"

Preview rejects a malformed custom-model source
    [Tags]    custom-models    preview    smoke    negative
    Given a ready project with user access exists
    When a custom model preview is requested for "not-a-valid-source"
    Then custom model preview response status should be "400"

Preview returns 404 for a nonexistent custom-model repo
    [Tags]    custom-models    preview    smoke    negative
    Given a ready project with user access exists
    When a custom model preview is requested for "${CUSTOM_MODELS_MISSING_REPO}"
    Then custom model preview response status should be "404"

Preview returns 403 for a gated custom-model without a token
    [Tags]    custom-models    preview    smoke    negative    auth
    Given a ready project with user access exists
    When a custom model preview is requested for "${CUSTOM_MODELS_GATED_REPO}"
    Then custom model preview response status should be "403"

Preview accepts hfTokenSecretName for custom-model preview
    [Tags]    custom-models    preview    smoke    auth
    [Teardown]    Custom model preview secret cleanup is performed
    Given a ready project with user access exists
    And a Hugging Face token secret "hf-token-preview" exists for custom model preview
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}" with secret "${CUSTOM_MODELS_HF_SECRET_NAME}"
    Then custom model preview response status should be "200"
    And custom model preview response should describe model "${CUSTOM_MODELS_PUBLIC_REPO}"

Preview with hfTokenSecretName handles invalid token for private custom-model
    [Documentation]    A private repo gates its metadata behind auth, so an invalid token
    ...    yields a 401 from the Hub that the API surfaces as 403. A gated (license-only)
    ...    repo exposes metadata publicly, so it cannot exercise this credential path.
    [Tags]    custom-models    preview    smoke    negative    auth
    [Teardown]    Custom model preview secret cleanup is performed
    Given a ready project with user access exists
    And a Hugging Face token secret "hf-token-invalid" exists for custom model preview
    When a custom model preview is requested for "${CUSTOM_MODELS_PRIVATE_REPO}" with secret "${CUSTOM_MODELS_HF_SECRET_NAME}"
    Then custom model preview response status should be "403"

Preview with invalid token reports a user-facing credential error in the response body
    [Documentation]    A 403 from the hub when credentials are wrong must surface a non-empty
    ...    detail message to the caller so the UI can direct the user to verify their token.
    ...    Status alone (403) is not enough — the body must explain why the request failed.
    ...    Uses a private repo because its metadata is gated behind auth, unlike a
    ...    license-gated repo whose metadata the Hub serves publicly.
    [Tags]    custom-models    preview    smoke    negative    auth
    [Teardown]    Custom model preview secret cleanup is performed
    Given a ready project with user access exists
    And a Hugging Face token secret "hf-token-invalid" exists for custom model preview
    When a custom model preview is requested for "${CUSTOM_MODELS_PRIVATE_REPO}" with secret "${CUSTOM_MODELS_HF_SECRET_NAME}"
    Then custom model preview response status should be "403"
    And custom model preview response should explain the credential failure

Preview response signals that a public model does not require a token
    [Documentation]    The preview response for a fully public model must carry
    ...    ``hfTokenRecommended: false`` so the UI can suppress the token picker
    ...    for models that do not need authentication — prompting unnecessarily
    ...    for credentials on public models degrades the import experience.
    [Tags]    custom-models    preview    smoke
    Given a ready project with user access exists
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    And custom model preview response should signal no authentication is required

Preview returns 400 when an S3 source folder does not exist
    [Tags]    custom-models    preview    smoke    negative
    Given a ready project with user access exists
    And Minio credentials and project S3 storage are ready for custom model tests
    And a missing S3 source is prepared for custom model preview
    When a prepared custom model S3 preview is requested
    Then custom model preview response status should be "400"
    And custom model preview response detail should contain "does not exist"

Preview returns 400 when an S3 source folder is empty
    [Tags]    custom-models    preview    smoke    negative
    Given a ready project with user access exists
    And Minio credentials and project S3 storage are ready for custom model tests
    And an empty S3 source is prepared for custom model preview
    When a prepared custom model S3 preview is requested
    Then custom model preview response status should be "400"
    And custom model preview response detail should contain "is empty"

Preview returns 200 with warnings for S3 source missing required layout files
    [Tags]    custom-models    preview    smoke
    Given a ready project with user access exists
    And Minio credentials and project S3 storage are ready for custom model tests
    And a config-only S3 source is prepared for custom model preview
    When a prepared custom model S3 preview is requested
    Then custom model preview response status should be "200"
    And custom model preview response should include warning containing "tokenizer.json or tokenizer_config.json"
    And custom model preview response should include warning containing "*.safetensors"

Preview of an object-storage model with no discoverable tags returns an empty suggestion with selectable weights
    [Documentation]    Object storage carries no catalog metadata of its own, so a model
    ...    uploaded without a card and without recognisable architecture settings has
    ...    nothing to suggest tags from. Preview must still return the model's selectable
    ...    weights alongside an empty tag list the user can fill in.
    [Tags]    custom-models    preview    tags    smoke
    Given a ready project with user access exists
    And Minio credentials and project S3 storage are ready for custom model tests
    And an object-storage model with no discoverable tags is prepared for custom model preview
    When a prepared custom model S3 preview is requested
    Then custom model preview response status should be "200"
    And custom model preview should offer no tags
    And custom model preview should still offer selectable weight files

Preview of an object-storage model suggests the tags its author wrote on the model card
    [Tags]    custom-models    preview    tags    smoke
    Given a ready project with user access exists
    And Minio credentials and project S3 storage are ready for custom model tests
    And an object-storage model with author-written tags is prepared for custom model preview
    When a prepared custom model S3 preview is requested
    Then custom model preview response status should be "200"
    And custom model preview should suggest the tag "summarization"

Preview of an object-storage model derived from a known model suggests that model's catalog tags
    [Documentation]    A fine-tune whose card names the model it came from can borrow that
    ...    model's published catalog tags, which describe the model far better than anything
    ...    recoverable from the uploaded files alone.
    [Tags]    custom-models    preview    tags    smoke
    Given a ready project with user access exists
    And Minio credentials and project S3 storage are ready for custom model tests
    And an object-storage model derived from "${CUSTOM_MODELS_PUBLIC_REPO}" is prepared for custom model preview
    When a prepared custom model S3 preview is requested
    Then custom model preview response status should be "200"
    And custom model preview should offer tags

Preview returns 403 when an S3 preview request uses a non-S3 secret
    [Tags]    custom-models    preview    smoke    negative    auth
    [Teardown]    Custom model preview secret cleanup is performed
    Given a ready project with user access exists
    And a Hugging Face token secret "hf-token-s3-preview-mismatch" exists for custom model preview
    And an S3 storage configuration references the Hugging Face preview secret for mismatch testing
    When a custom S3 model preview is requested for "s3://default-bucket/workbench/no-such-prefix" with project S3 storage
    Then custom model preview response status should be "403"
    And custom model preview response detail should contain "cannot be used for S3 preview"

Onboard accepts an S3 source with a valid S3 secret
    [Tags]    custom-models    onboard    smoke
    Given a ready project with user access exists
    And Minio credentials and project S3 storage are ready for custom model tests
    And a valid S3 source is prepared for custom model preview
    When a prepared custom model S3 preview is requested
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded from S3 with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    And custom AIMModel for source "${TEST_S3_PREVIEW_SOURCE}" should wire S3 secret "minio-credentials"
    And custom AIMModel for source "${TEST_S3_PREVIEW_SOURCE}" should use image "${CUSTOM_MODELS_ONBOARD_IMAGE}"

Onboard rejects an S3 source when hard validation fails
    [Tags]    custom-models    onboard    smoke    negative
    Given a ready project with user access exists
    And Minio credentials and project S3 storage are ready for custom model tests
    And a missing S3 source is prepared for custom model preview
    When an S3 custom model onboard request is sent for source "${TEST_S3_PREVIEW_SOURCE}" with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "400"
    And custom model onboard response detail should contain "does not exist"

Onboard ignores S3 preview warnings and proceeds
    [Tags]    custom-models    onboard    smoke
    Given a ready project with user access exists
    And Minio credentials and project S3 storage are ready for custom model tests
    And a config-only S3 source is prepared for custom model preview
    When a prepared custom model S3 preview is requested
    Then custom model preview response status should be "200"
    And custom model preview response should include warning containing "tokenizer.json or tokenizer_config.json"
    When the previewed custom model is onboarded from S3 with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    And custom AIMModel for source "${TEST_S3_PREVIEW_SOURCE}" should exist in the namespace
    And custom AIMModel for source "${TEST_S3_PREVIEW_SOURCE}" should wire S3 secret "minio-credentials"

Onboard persists the previewed custom model into the namespace
    [Documentation]    After preview, onboard creates a namespace-scoped AIMModel CR
    ...    for the previewed source so it shows up in the project's model list.
    [Tags]    custom-models    onboard    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    And custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace
    And custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should use image "${CUSTOM_MODELS_ONBOARD_IMAGE}"

Onboard uses the selected runtime image family
    [Documentation]    The runtime image selected by the user determines the profile family,
    ...    even when hardware discovery would otherwise prefer another installed family.
    ...    Runs in a fresh project so a same-family alternate tag cannot 409 against
    ...    the shared testing project's already-provisioned base model.
    [Tags]    custom-models    onboard    profile    smoke    kubectl
    Given a fresh project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And the user selects a runtime image other than the cluster default
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${TEST_SELECTED_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    And the onboarded custom model from "${CUSTOM_MODELS_PUBLIC_REPO}" should use runtime family from image "${TEST_SELECTED_ONBOARD_IMAGE}"
    And the project base model should use selected image "${TEST_SELECTED_ONBOARD_IMAGE}"
    When a copy of the onboarded custom model is created in the project
    Then the copied AIMModel should use runtime family from image "${TEST_SELECTED_ONBOARD_IMAGE}"

Onboard refuses another tag of the same runtime family
    [Documentation]    A second selected tag of a family already provisioned in the project
    ...    must be refused rather than silently re-pointing the shared base model.
    [Tags]    custom-models    onboard    negative    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And another published tag of the onboarded runtime family is recorded
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${TEST_CONFLICTING_ONBOARD_IMAGE}" overriding display name to "Second Custom Import"
    Then custom model onboard response status should be "409"

Onboard rejects an invalid selected runtime image without creating a model
    [Documentation]    A selected image without a tag or digest cannot identify a runtime
    ...    family. The request must fail validation without persisting the custom model.
    [Tags]    custom-models    onboard    negative    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "registry.example.com/custom-base"
    Then custom model onboard response status should be "400"
    And no custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace

Onboard is idempotent when called twice with the same source
    [Documentation]    Re-submitting the same onboard payload must not create duplicate
    ...    AIMModel CRs and must not raise — exactly one CR remains.
    [Tags]    custom-models    onboard    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    And exactly one custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace

Onboard accepts a user-customized display name and stores it on the model
    [Documentation]    The import wizard lets users rename the model from the HuggingFace
    ...    default before submitting. The custom display name must survive the onboard call
    ...    and appear on the model card, not be silently overwritten by the preview default.
    [Tags]    custom-models    onboard    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}" overriding display name to "My Custom TinyLlama"
    Then custom model onboard response status should be "204"
    When the project custom model list is retrieved
    Then listed custom model from "${CUSTOM_MODELS_PUBLIC_REPO}" should show display name "My Custom TinyLlama"

Custom model imported into one project is not visible in another project
    [Documentation]    After onboarding a model in project A, the model must be absent from
    ...    project B's custom-model list — AIMModel CRs are namespace-scoped so a second
    ...    project cannot see or deploy an import that belongs to a different namespace.
    [Tags]    custom-models    onboard    namespace    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And aiwb_custom_models.A second ready project with user access exists
    When the project custom model list is retrieved
    Then the custom model from the first project should not appear in the second project model list

Copy creates another custom model from the same source
    [Documentation]    Copying an onboarded custom model should create another model
    ...    entry for the same canonical source in the project model list, derived
    ...    from the source model's runtime family rather than the hardware default.
    [Tags]    custom-models    copy    smoke    kubectl
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    And the onboarded custom model from "${CUSTOM_MODELS_PUBLIC_REPO}" should use runtime family from image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    When the project custom model list is retrieved
    And record listed custom model count for source "${CUSTOM_MODELS_PUBLIC_REPO}"
    When a copy of the onboarded custom model is created in the project
    When the project custom model list is retrieved
    Then listed custom model count for source "${CUSTOM_MODELS_PUBLIC_REPO}" should increase
    And the copied AIMModel should use runtime family from image "${CUSTOM_MODELS_ONBOARD_IMAGE}"

Copy returns not-found for a missing source model
    [Documentation]    Copying a model name that does not exist in the project must
    ...    return a not-found response.
    [Tags]    custom-models    copy    negative    smoke
    Given a ready project with user access exists
    When copy request is sent for custom model "no-such-model-zzz"
    Then custom model copy response status should be "404"

Copy is refused when the source runtime image conflicts with the project family
    [Documentation]    A copy carries the source model's runtime image. When that image is a
    ...    different tag of a runtime family the project already provisioned, the copy must be
    ...    refused rather than silently re-pointing the shared family for every model using it.
    [Tags]    custom-models    copy    negative    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    And another published tag of the onboarded runtime family is recorded
    And the user updates the model runtime image to "${TEST_CONFLICTING_ONBOARD_IMAGE}"
    When the onboarded custom model is copied for source "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model copy response status should be "409"

Copy rejects a non-custom source model
    [Documentation]    Copying a model that is not a custom import must return
    ...    not-found to enforce custom-model eligibility.
    [Tags]    custom-models    copy    negative    smoke
    Given a ready project with user access exists
    And a non-custom AIMModel exists in the namespace
    When copy request is sent for custom model "${TEST_MODEL_NAME}"
    Then custom model copy response status should be "404"

Onboard wires HF_TOKEN env when a secret is supplied
    [Documentation]    When the user supplies a token secret on onboard, the resulting
    ...    AIMModel CR must reference it from spec.profiles.overrides.modelSources[0].env
    ...    so the engine can authenticate
    ...    to Hub for gated/private weights. The token only matters on onboard, so the
    ...    preview here intentionally runs without a secret to isolate the dimension.
    [Tags]    custom-models    onboard    auth    smoke
    [Teardown]    Run Keywords    Custom model preview secret cleanup is performed
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a Hugging Face token secret "hf-token-onboard" exists for custom model preview
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}" and secret "${CUSTOM_MODELS_HF_SECRET_NAME}"
    Then custom model onboard response status should be "204"
    And custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should wire HF token secret "${CUSTOM_MODELS_HF_SECRET_NAME}"

Onboard stores Hugging Face source URI directly on the custom model
    [Documentation]    Onboarding should persist the Hugging Face source directly
    ...    as ``hf://owner/model`` on the custom AIMModel model source, without
    ...    staging weights through a workbench import pipeline.
    [Tags]    custom-models    onboard    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    And custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should keep Hugging Face source URI

Re-onboarding an existing custom model remains idempotent
    [Documentation]    Re-submitting the same source should still succeed idempotently
    ...    and keep exactly one model record for that source.
    [Tags]    custom-models    onboard    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    And exactly one custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should exist in the namespace

A project with no imports returns an empty custom model list
    [Documentation]    The list endpoint must return an empty data array for a fresh
    ...    project before any custom model has been onboarded — this is the baseline
    ...    contract that all subsequent list assertions build on.
    [Tags]    custom-models    list    smoke
    Given a ready project with user access exists
    When the project custom model list is retrieved
    Then the custom model list should be empty

Onboarded custom model appears in the project model list with metadata
    [Documentation]    After onboard, the project model list endpoint must return
    ...    the custom model with its display name and tags so the UI can present it.
    [Tags]    custom-models    list    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    When the project custom model list is retrieved
    Then custom model list should contain a model from "${CUSTOM_MODELS_PUBLIC_REPO}"
    And listed custom model from "${CUSTOM_MODELS_PUBLIC_REPO}" should include display name and tags

Listed custom models include onboarding status fields
    [Documentation]    Every model in the list carries the composed onboard status
    ...    (phase, templateReady, artifactPhase, etc.) so the UI can render
    ...    per-model state without issuing a separate detail request.
    [Tags]    custom-models    list    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    When the project custom model list is retrieved
    Then listed custom models include onboarding status fields

GET list reflects the updated display name after a PATCH
    [Documentation]    After patching a model's display name, the list endpoint must
    ...    return the updated value immediately — annotation writes in K8s are
    ...    synchronous from the API server's perspective, so there is no replication
    ...    delay to account for between the PATCH and the subsequent list read.
    [Tags]    custom-models    list    patch    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the user updates the model display name to "Read-After-Write Name"
    And the project custom model list is retrieved
    Then listed custom model from "${CUSTOM_MODELS_PUBLIC_REPO}" should show display name "Read-After-Write Name"

Onboarded custom model is retrievable by name
    [Documentation]    After onboard, the model detail endpoint returns the full model
    ...    representation for the onboarded source, including all top-level fields.
    [Tags]    custom-models    detail    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    When the onboarded custom model detail is retrieved for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model detail response status should be "200"
    And custom model detail should match the onboarded source "${CUSTOM_MODELS_PUBLIC_REPO}"

Onboarded custom model detail includes onboarding status
    [Documentation]    The detail endpoint exposes the composed onboarding state so the
    ...    UI can poll a single endpoint to track model readiness and deployment eligibility.
    [Tags]    custom-models    detail    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}"
    Then custom model onboard response status should be "204"
    When the onboarded custom model detail is retrieved for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model detail should include onboarding status fields

Retrieving a non-existent custom model returns not-found
    [Documentation]    A detail request for a model name that does not exist in the
    ...    project must be rejected with a not-found response.
    [Tags]    custom-models    detail    negative    smoke
    Given a ready project with user access exists
    When requesting a non-existent custom model returns not-found
    Then custom model detail response status should be "404"

Onboarded custom model lists its Default profile first
    [Documentation]    Every custom model has an engine-created Default profile set from
    ...    day one, so the profiles list must return it — classified by provenance, flagged
    ...    isDefault, and ordered first — with no narrowing or backfill step.
    [Tags]    custom-models    profiles    list    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the profiles for the onboarded custom model are retrieved
    Then custom model profile list response status should be "200"
    And the profile list should present the Default first

Onboarded custom model detail carries the profile collection Default first
    [Documentation]    The detail endpoint embeds the same profile collection as the dedicated
    ...    profiles endpoint, so a client polling detail sees the Default (isDefault, ordered
    ...    first) without a separate profiles request.
    [Tags]    custom-models    profiles    detail    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    When the onboarded custom model detail is retrieved for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model detail response status should be "200"
    And custom model detail should present the Default profile first

Listed custom models carry the profile collection Default first
    [Documentation]    The list endpoint embeds each model's profile collection so the grid can
    ...    show a count and the Default summary without issuing a per-model profiles request.
    [Tags]    custom-models    profiles    list    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    When the project custom model list is retrieved
    Then listed custom model from "${CUSTOM_MODELS_PUBLIC_REPO}" should present the Default profile first

Custom model detail includes a newly added named profile alongside the Default
    [Documentation]    After a named profile is created, the model detail collection lists both
    ...    the Default (first) and the named row, so the grid reflects the new profile without a
    ...    dedicated profiles request.
    [Tags]    custom-models    profiles    detail    kubectl
    [Teardown]    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    And the user adds a profile named "Extra config" to the onboarded custom model
    And the profile the user added is ready to serve
    When the onboarded custom model detail is retrieved for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model detail response status should be "200"
    And custom model detail should include the named profile "Extra config" alongside the Default

Default profile is retrievable by the reserved alias
    [Documentation]    The reserved literal 'default' resolves to the model's engine-created
    ...    set, so clients need not carry the generated hash; the response still carries the
    ...    real resourceName.
    [Tags]    custom-models    profiles    detail    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the Default profile for the onboarded custom model is retrieved
    Then custom model profile detail response status should be "200"
    And the retrieved profile should be the Default

Requesting a profile that does not belong to the model returns not-found
    [Documentation]    A profile identifier not owned by the model must read as not-found
    ...    rather than returning another model's or project's data.
    [Tags]    custom-models    profiles    detail    negative    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When a profile that does not belong to the model is requested
    Then custom model profile detail response status should be "404"

Listing profiles for a non-existent custom model returns not-found
    [Documentation]    The profiles list is scoped to a model, so a request for a model that
    ...    does not exist in the project must be rejected with not-found.
    [Tags]    custom-models    profiles    list    negative    smoke
    Given a ready project with user access exists
    When the profiles for a non-existent custom model are requested
    Then custom model profile list response status should be "404"

Adding a profile to an imported custom model returns it and lists it
    [Documentation]    A user adds a second profile to a model they already imported, without
    ...    re-importing. The new profile is returned in the same shape as the read endpoints
    ...    and appears in the model's profile list alongside the Default.
    [Tags]    custom-models    profiles    create    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    When the user adds a profile named "High speed fun" to the onboarded custom model
    Then custom model profile create response status should be "201"
    And the created profile should describe a non-default profile
    And the created profile should appear in the model's profile list

Editing a saved profile's name keeps its identity and shows the new name
    [Documentation]    A user corrects a saved profile's name instead of creating a near-duplicate.
    ...    The rename returns the profile with the new display name, preserves its immutable
    ...    resource identity, and the new name appears in the model's profile list.
    [Tags]    custom-models    profiles    patch    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    When the user adds a profile named "High speed fun" to the onboarded custom model
    Then custom model profile create response status should be "201"
    When the user renames the created profile to "High speed fun v2"
    Then the profile edit response status should be "200"
    And the renamed profile should keep its identity and show the new name

Editing a saved profile is refused while a deployment pins it
    [Documentation]    Blocking any modification while a workload references the profile is the
    ...    agreed simplification: the edit is refused with a conflict that names the blocking
    ...    deployment and nothing is written, so a running deployment cannot be silently altered.
    [Tags]    custom-models    profiles    patch    negative    kubectl
    [Teardown]    Run Keywords    Remove blocking AIMService if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    When the user adds a profile named "High speed fun" to the onboarded custom model
    Then custom model profile create response status should be "201"
    And a deployment pins the created profile
    When the user attempts to rename the pinned profile to "High speed fun v2"
    Then the profile edit should be refused as in use by a deployment

A created profile has its own identity separate from the Default
    [Documentation]    A named profile is stored as its own resource, so it can later be edited
    ...    or removed without disturbing the model's Default profile.
    [Tags]    custom-models    profiles    create    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    When the user adds a profile named "High speed fun" to the onboarded custom model
    Then custom model profile create response status should be "201"
    And the created profile should have its own identity distinct from the Default

Adding a profile with a long display name still derives a servable profile
    [Documentation]    A profile's resource identity is composed from the model name, the display
    ...    name, and a uniqueness suffix. A long-but-realistic display name must still derive a
    ...    servable profile that surfaces its accelerator, precision, and metric — not a set that
    ...    never reconciles and leaves the profile row blank in the UI.
    [Tags]    custom-models    profiles    create    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    When the user adds a profile named "High throughput configuration for extended context serving" to the onboarded custom model
    Then custom model profile create response status should be "201"
    And the profile the user added is ready to serve
    And the added profile should present its accelerator, precision, and metric

Adding a profile with a duplicate name is rejected as a conflict
    [Documentation]    Two profiles on the same model cannot share a display name, so a second
    ...    create with the same name is rejected with a conflict.
    [Tags]    custom-models    profiles    create    negative
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    When the user adds a profile named "Second config" to the onboarded custom model
    Then custom model profile create response status should be "201"
    When the user adds a profile named "Second config" to the onboarded custom model
    Then custom model profile create response status should be "409"

Adding a profile whose name differs only by casing is rejected as a conflict
    [Documentation]    A profile name is unique regardless of casing, so a second create whose
    ...    name matches an existing one in any casing is rejected with a conflict.
    [Tags]    custom-models    profiles    create    negative
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    When the user adds a profile named "High speed fun" to the onboarded custom model
    Then custom model profile create response status should be "201"
    When the user adds a profile named "HIGH SPEED FUN" to the onboarded custom model
    Then custom model profile create response status should be "409"

Adding a profile named Default is rejected as invalid
    [Documentation]    'Default' is reserved for the engine-owned profile set, so the API
    ...    rejects it at the schema boundary before touching the cluster.
    [Tags]    custom-models    profiles    create    negative    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the user attempts to add a profile named "Default" to the onboarded custom model
    Then custom model profile create response status should be "422"

Adding a profile to a non-existent custom model returns not-found
    [Documentation]    The create endpoint is scoped to a model, so a request for a model that
    ...    does not exist in the project must be rejected with not-found.
    [Tags]    custom-models    profiles    create    negative    smoke
    Given a ready project with user access exists
    When the user attempts to add a profile named "Orphan profile" to a non-existent custom model
    Then custom model profile create response status should be "404"

A profile created in one tenant is not visible in another tenant
    [Documentation]    A profile a user saves against their model must stay private to their
    ...    project. With the same model onboarded in a second tenant, that tenant lists only its
    ...    own engine-created Default — the first tenant's named profile never crosses the
    ...    namespace boundary. This is the profile counterpart to the model-level isolation
    ...    guarantee in a dual-tenant install.
    [Tags]    custom-models    profiles    namespace    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    And the user adds a profile named "Tenant A only" to the onboarded custom model
    And custom model profile create response status should be "201"
    And aiwb_custom_models.A second ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the profiles for the onboarded custom model are retrieved
    Then custom model profile list response status should be "200"
    And the first tenant's named profile should not appear in the second tenant's profile list

Deleting a saved profile removes it and leaves the Default intact
    [Documentation]    A user removes a named profile they no longer need. It disappears from the
    ...    model's profile list while the engine-owned Default is left untouched.
    [Tags]    custom-models    profiles    delete    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    And the user adds a profile named "Deletable config" to the onboarded custom model
    And custom model profile create response status should be "201"
    When the user deletes the created profile
    Then the profile delete response status should be "204"
    And the deleted profile should no longer appear in the model's profile list
    And the model's Default profile should still be present

Deleting the Default profile is refused
    [Documentation]    The Default is engine-reconciled from the model and can only go away when
    ...    the model is deleted, so the profile endpoint refuses to delete it as unprocessable.
    [Tags]    custom-models    profiles    delete    negative    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the user attempts to delete the model's Default profile
    Then the profile delete response status should be "422"

Deleting a saved profile is refused while a deployment pins it
    [Documentation]    A profile still pinned by a live deployment cannot be deleted; the request
    ...    is refused with a conflict naming the blocking deployment so a running workload cannot
    ...    lose the profile it deployed, and nothing is removed.
    [Tags]    custom-models    profiles    delete    negative    kubectl
    [Teardown]    Run Keywords    Remove blocking AIMService if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    And the user adds a profile named "Pinned config" to the onboarded custom model
    And the profile the user added is ready to serve
    And a deployment pins the created profile
    When the user attempts to delete the created profile
    Then the profile delete should be refused as in use by a deployment

Editing the Default narrows it to the submitted runtime configuration
    [Documentation]    Editing an already-imported model's Default is the moment it is narrowed:
    ...    the engine-owned derivation is pinned to the single profile a deploy resolves to, so the
    ...    Default stops fanning out and its accelerator count agrees with the profile's
    ...    tensor-parallel size. Narrowing is invisible to the list, which still shows the Default
    ...    as one row.
    [Tags]    custom-models    profiles    patch    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    When the user edits the model runtime configuration
    Then the runtime profile edit response status should be "200"
    And the onboarded model's Default derivation should match the submitted runtime configuration
    When the profiles for the onboarded custom model are retrieved
    Then the profile list should present the Default first

Editing the Default is refused while a deployment pins one of its profiles
    [Documentation]    Narrowing the Default re-derives its profiles and prunes the ones the
    ...    narrowed set no longer selects. If a live deployment pins one of those profiles the edit
    ...    is refused with a conflict, so a running workload cannot be silently broken and nothing
    ...    is written.
    [Tags]    custom-models    profiles    patch    negative    kubectl
    [Teardown]    Run Keywords    Remove blocking AIMService if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And the onboarded model's Default profile is ready
    And a deployment pins a Default profile the edit would prune
    When the user edits the model runtime configuration
    Then the runtime profile edit should be refused as in use by a deployment

Retrieving a non-custom AIMModel via the custom model endpoint returns not-found
    [Documentation]    The detail endpoint must not expose fine-tuned or base
    ...    AIMModels through the custom-model path — only CRs stamped with the
    ...    custom-import revision annotation are valid targets. This prevents
    ...    leaking other model types and keeps the endpoint purpose-specific.
    [Tags]    custom-models    detail    negative    smoke    kubectl
    Given a ready project with user access exists
    And a non-custom AIMModel exists in the namespace
    When the custom model detail is requested for model "${TEST_MODEL_NAME}"
    Then custom model detail response status should be "404"

Runtime profile options expose the base-template runtime matrix
    [Documentation]    A custom model inherits the runtime choices its base supports, so the
    ...    onboard wizard is offered the accelerator, count, precision and metric options —
    ...    and which of those go together — for a project the user can access. A project
    ...    whose base has emitted nothing yet offers no choices rather than failing.
    [Tags]    custom-models    profile    smoke
    Given a ready project with user access exists
    When the runtime profile options for the project are retrieved
    Then runtime profile options response status should be "200"
    And runtime profile options response should expose the runtime matrix fields

Base-image runtime profile options expose discovered per-image runtime matrix fields
    [Documentation]    The runtime choices for one concrete base image are offered for the
    ...    selected image, including which accelerator, count, precision and metric choices go
    ...    together, so the onboard wizard only lets a user pick a combination that image
    ...    actually supports.
    [Tags]    custom-models    profile    smoke
    Given a ready project with user access exists
    When the base-image runtime profile options for a discovered image are retrieved
    Then runtime profile options response status should be "200"
    And base-image runtime profile options response should expose the per-image runtime matrix fields

Onboard persists runtime profile overrides on the AIMModel
    [Documentation]    When the user supplies ``customProfile`` on onboard, the
    ...    overrides land on ``AIMModel.spec.profiles.overrides``. aim-engine
    ...    consumes the block at admission and bakes the values into each
    ...    emitted AIMProfile, so the durable cross-cluster contract is the
    ...    AIMModel itself. Asserts ``acceleratorModel`` because the AIMModel CRD's
    ...    ``overrides`` schema enumerates it as a persisted field; free-form keys
    ...    such as ``precision`` are not in the schema and are pruned on write.
    [Tags]    custom-models    onboard    profile    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}" and runtime profile overrides
    ...    acceleratorModel=MI300X
    Then custom model onboard response status should be "204"
    And custom AIMModel for source "${CUSTOM_MODELS_PUBLIC_REPO}" should carry profile override "acceleratorModel" with value "MI300X"

Deploying a custom model pins the profile matching the onboarded precision
    [Documentation]    A custom model onboarded at a given precision must be served at that
    ...    precision, not an arbitrary one. Every precision the base template offers is
    ...    exercised, so no offered precision is left unproven and a single-precision
    ...    template - a valid configuration - is covered by one round rather than skipped.
    [Tags]    custom-models    deploy    profile    gpu
    [Teardown]    Run Keywords
    ...    Undeploy the custom model AIM service if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And the base template offers at least one precision
    And project quota covers every offered precision
    When the custom model is onboarded and deployed at each offered precision
    Then every offered precision should have been served by a profile pinning it

Deploying a custom model serves its Default when the model has other profiles
    [Documentation]    Resolving a deploy through the profile that owns it must not change which
    ...    profile an unqualified deploy gets: a model that also has an authored profile must
    ...    still serve its Default, never the authored one merely because it exists.
    [Tags]    custom-models    deploy    profile    gpu
    [Teardown]    Run Keywords
    ...    Undeploy the custom model AIM service if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And project quota is set to    gpu_count=2
    And a custom model is onboarded in the project
    And custom model onboarding status should be "Ready"
    And the onboarded model's Default profile is ready
    And the user adds a profile named "High speed fun" to the onboarded custom model
    And the profile the user added is ready to serve
    When custom model is deployed as an AIM service
    Then the deployment should serve the model's Default profile

Deploying a custom model with a chosen profile serves that profile
    [Documentation]    A user who authored a second profile can choose it when submitting the
    ...    deployment, and the deployment must then serve that profile rather than the model's
    ...    Default. The choice is expressed with the identifier the profile list reports, so
    ...    users never handle engine-generated profile names.
    [Tags]    custom-models    deploy    profile    gpu
    [Teardown]    Run Keywords
    ...    Undeploy the custom model AIM service if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And project quota is set to    gpu_count=2
    And a custom model is onboarded in the project
    And custom model onboarding status should be "Ready"
    And the onboarded model's Default profile is ready
    And the user adds a profile named "High speed fun" to the onboarded custom model
    And the profile the user added is ready to serve
    When custom model is deployed with the profile the user selected
    Then the deployment should serve the profile the user chose

Deploying a custom model with a profile it does not have is refused
    [Documentation]    An unknown profile must be refused rather than quietly falling back to
    ...    the Default, so a user is never handed a deployment serving a configuration they
    ...    did not ask for.
    [Tags]    custom-models    deploy    profile    negative    smoke
    [Teardown]    Run Keywords
    ...    Undeploy the custom model AIM service if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And custom model onboarding status should be "Ready"
    When the user deploys the custom model asking for a profile that does not exist
    Then the deploy should be refused as an unknown profile

Onboard rejects a customProfile whose image disagrees with the top-level image
    [Documentation]    Two disagreeing image refs in the same payload would
    ...    silently pick one for deployment, so the API rejects the request at
    ...    the Pydantic schema boundary with a 422 instead of accepting an
    ...    ambiguous deployment image.
    [Tags]    custom-models    onboard    profile    negative    smoke
    Given a ready project with user access exists
    When a custom model preview is requested for "${CUSTOM_MODELS_PUBLIC_REPO}"
    Then custom model preview response status should be "200"
    When the previewed custom model is onboarded with image "${CUSTOM_MODELS_ONBOARD_IMAGE}" and a conflicting profile image "docker.io/other/image:v9"
    Then custom model onboard response status should be "422"

Delete an onboarded custom model with no active deployments
    [Documentation]    With nothing deploying it, deleting an onboarded model removes
    ...    its AIMModel CR so it disappears from the project entirely.
    [Tags]    custom-models    delete    smoke    kubectl
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the user deletes the onboarded model
    Then custom model delete response status should be "204"
    And the onboarded AIMModel should no longer exist in the namespace
    And the onboarded model should no longer appear in the project model list

Deleting an onboarded model cascade-cleans its derived AIMProfile
    [Documentation]    The AIMProfile aim-engine derives from the model is owner-referenced
    ...    by the AIMModel, so deleting the model must cascade-clean the profile via
    ...    Kubernetes owner references — the workbench never deletes it directly.
    [Tags]    custom-models    delete    kubectl
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And an AIMProfile for the onboarded model exists
    When the user deletes the onboarded model
    Then custom model delete response status should be "204"
    And the derived AIMProfile should no longer exist in the namespace

Deleting a custom model with an active deployment is rejected with a conflict
    [Documentation]    A model still referenced by an AIMService must not be deletable;
    ...    the request is rejected with a conflict that names the blocking deployment so
    ...    the user knows what to tear down first, and the model is left untouched.
    [Tags]    custom-models    delete    negative    kubectl
    [Teardown]    Run Keywords    Remove blocking AIMService if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And an AIMService referencing the onboarded model exists
    When the user attempts to delete custom model "${TEST_CUSTOM_MODEL_NAME}"
    Then custom model delete response status should be "409"
    And the delete conflict response should name the blocking AIMService
    And the onboarded AIMModel should still exist in the namespace

Deleting a custom model that does not exist returns not-found
    [Documentation]    A delete request for a model name that does not exist in the
    ...    project must be rejected with a not-found response.
    [Tags]    custom-models    delete    negative    smoke
    Given a ready project with user access exists
    When the user attempts to delete custom model "no-such-model-zzz"
    Then custom model delete response status should be "404"

# Conflict-on-different-source is exercised in pytest (tests/custom_models/test_onboard.py)
# rather than Robot: triggering it requires two Hugging Face repos whose
# server-derived display names sanitize to the same Kubernetes label value, which
# isn't a contract we can rely on for E2E setup.

Update custom model display name after onboard
    [Documentation]    After onboard, the user can PATCH the model display name and
    ...    see the updated value in the API response.
    [Tags]    custom-models    patch    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the user updates the model display name to "Renamed TinyLlama"
    Then the model should show display name "Renamed TinyLlama"

Update custom model tags after onboard
    [Documentation]    After onboard, the user can PATCH model tags and see the
    ...    updated list in the API response.
    [Tags]    custom-models    patch    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the user updates the model tags to "llama,chat"
    Then the model should show tags "llama,chat"

Editing the runtime profile with conflicting image references is rejected
    [Documentation]    A runtime-profile edit whose customProfile.image disagrees
    ...    with the top-level image would leave the deployment image ambiguous, so
    ...    the API rejects it at the schema boundary with a 422 before touching the
    ...    model or its profile.
    [Tags]    custom-models    patch    profile    negative    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the user edits the model runtime profile with conflicting image references
    Then the runtime profile edit response status should be "422"

Editing a runtime profile map to remove one of several pairs persists the removal
    [Documentation]    A user who has several engine arguments and environment
    ...    variables on a model and removes one of them, keeping the rest, should see
    ...    only the kept settings after saving — the removed one must not reappear.
    [Tags]    custom-models    patch    profile    kubectl
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    And an AIMProfile for the onboarded model exists
    When the user sets two engine arguments and two environment variables on the model
    Then the model runtime profile should carry both engine arguments and both environment variables
    When the user removes one engine argument and one environment variable
    Then the model runtime profile should retain only the kept engine argument and environment variable

PATCH updates display name and description in a single combined request
    [Documentation]    A single PATCH carrying both displayName and description must
    ...    persist both fields atomically — the edit wizard sends one request for
    ...    the entire information step, not two separate ones.
    [Tags]    custom-models    patch    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the user updates the model display name to "Combined Edit Name" and description to "A combined edit description"
    Then the model should show display name "Combined Edit Name"
    And the model should show description "A combined edit description"

PATCH clears the description when an empty string is provided
    [Documentation]    The description field uses an empty string as a deliberate
    ...    clear signal — sending ``description: ""`` must wipe the existing value.
    ...    An empty string is not the same as omitting the field (no change), so the
    ...    API must treat it as an explicit reset and return an empty description.
    [Tags]    custom-models    patch    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the user updates the model description to "Initial description"
    Then the model should show description "Initial description"
    When the user clears the model description
    Then model description should be empty

PATCH display name is rejected when it conflicts with another model in the project
    [Documentation]    Two models in the same project cannot share a display name —
    ...    the conflict guard rejects the rename with a 409 so the edit wizard can
    ...    surface a meaningful error rather than silently overwriting or leaving the
    ...    user confused about why nothing changed.
    [Tags]    custom-models    patch    negative    smoke
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is onboarded in the project
    When the user updates the model display name to "Taken Name"
    Then the model should show display name "Taken Name"
    Given a copy of the onboarded custom model is created in the project
    When the user attempts to rename the copy to "Taken Name"
    Then the model patch response status should be "409"

# The not-ready 409 runtime-profile edit is exercised in pytest
# (tests/custom_models/test_patch_display_metadata.py) rather than Robot: it depends
# on editing before aim-engine has emitted an AIMProfile for the freshly onboarded
# model, a race that is not a deterministic E2E precondition.

Custom onboarded model can run deploy to chat lifecycle
    [Documentation]    Validates the custom-model inference lifecycle end-to-end:
    ...    onboard → deploy → running/chat-capable → chat completion → undeploy.
    ...    This deploy asks for no particular profile, so it must serve the model's Default
    ...    with the runtime settings from model settings, and no deploy-time override fields.
    [Tags]    custom-models    deploy    chat    undeploy    gpu
    [Teardown]    Run Keywords    Remove custom model deployment if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And project quota is set to    gpu_count=2
    And a custom model is onboarded in the project
    And custom model onboarding status should be "Ready"
    When custom model is deployed as an AIM service
    Then deployed AIMService should reference the custom model
    And AIMService CR should pin model-settings AIMProfile for custom model in kubernetes
    And Deployed AIM reaches Running state
    And deployed custom model should be accessible for inference
    And chat completion against deployed custom model should succeed
    When custom model deployment is removed
    Then custom model deployment should be removed

Custom model cleanup confirms both API deletion and Kubernetes predictor removal
    [Documentation]    Static AST parsing of the cleanup keywords can only prove call order and
    ...    literal arguments are right — it cannot prove the predictor Deployment actually
    ...    disappears. This test drives the production idempotent cleanup keyword directly and
    ...    observes a real kubectl round-trip: the predictor exists before cleanup runs, and is
    ...    gone from Kubernetes — not just from the API — after it.
    [Tags]    custom-models    deploy    undeploy    cleanup    gpu    kubectl
    [Teardown]    Run Keywords    Remove custom model deployment if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And project quota is set to    gpu_count=2
    And a custom model is onboarded in the project
    And custom model onboarding status should be "Ready"
    When custom model is deployed as an AIM service
    And Deployed AIM reaches Running state
    Then AIM deployment should exist in kubernetes
    And the deployed custom model's Kubernetes name is captured
    When Remove custom model deployment if present
    Then custom model deployment should be removed
    And the predictor Deployment for the deployed custom model should no longer exist in kubernetes

Custom model cleanup still removes the Kubernetes predictor when the API record is already gone
    [Documentation]    Exercises the idempotent cleanup keyword's already-404 branch — the same
    ...    branch the AIM catalog suite teardown takes whenever a model's AIMService is deleted
    ...    by the time cleanup runs. Undeploys via the API first so the service already reads
    ...    404, then drives cleanup directly and confirms it still verifies the predictor
    ...    Deployment is gone from Kubernetes instead of trusting the API's 404 alone.
    [Tags]    custom-models    deploy    undeploy    cleanup    gpu    kubectl
    [Teardown]    Run Keywords    Remove custom model deployment if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And project quota is set to    gpu_count=2
    And a custom model is onboarded in the project
    And custom model onboarding status should be "Ready"
    When custom model is deployed as an AIM service
    And Deployed AIM reaches Running state
    When custom model deployment is removed
    Then custom model deployment should be removed
    When Remove custom model deployment if present
    Then the predictor Deployment for the deployed custom model should no longer exist in kubernetes

Verifying predictor absence fails while the predictor Deployment is still present
    [Documentation]    Negative regression proving the Kubernetes-level cleanup assertion has
    ...    teeth: called while the predictor Deployment is still genuinely running, it must
    ...    raise rather than pass, so a real leak in the production cleanup keyword would be
    ...    caught by this suite instead of silently passing every other assertion.
    [Tags]    custom-models    undeploy    cleanup    gpu    kubectl    negative
    [Teardown]    Run Keywords    Remove custom model deployment if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And project quota is set to    gpu_count=2
    And a custom model is onboarded in the project
    And custom model onboarding status should be "Ready"
    When custom model is deployed as an AIM service
    And Deployed AIM reaches Running state
    And the deployed custom model's Kubernetes name is captured
    Then Predictor absence verification should fail while the predictor exists

Custom model runtime profile round-trips from onboard through the inference pod
    [Documentation]    The full customProfile round-trip on a real cluster: onboard a public
    ...    model with a non-default runtime profile, edit the profile, deploy, and confirm the
    ...    running inference pod reflects the edited profile — image, accelerator product and
    ...    count, and the edited engine argument and env var. The deploy asks for no particular
    ...    profile and sends no override fields, so the runtime settings can only have come from
    ...    model settings. Teardown removes the deployment so a mid-test failure cannot leave
    ...    an AIMService behind.
    [Tags]    custom-models    onboard    patch    profile    deploy    undeploy    gpu    kubectl
    [Teardown]    Run Keywords    Remove custom model deployment if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And project quota is set to    gpu_count=2
    And a custom model is onboarded with a non-default runtime profile
    And custom model onboarding status should be "Ready"
    And an AIMProfile for the onboarded model exists
    When the user revises the model's engine settings
    Then the model runtime profile should carry the revised engine settings
    And custom model onboarding status should be "Ready"
    When custom model is deployed as an AIM service
    And Deployed AIM reaches Running state
    Then the running inference pod should reflect the model's runtime profile

Deploying a custom model that does not exist returns not-found
    [Documentation]    The deploy endpoint must reject a request for a model name that
    ...    does not exist in the project namespace — it cannot create an AIMService that
    ...    references a missing AIMModel CR, and the caller needs a 404 to distinguish
    ...    this from a validation failure (400) or quota issue.
    [Tags]    custom-models    deploy    negative    smoke
    Given a ready project with user access exists
    When the user attempts to deploy custom model with name "no-such-model-zzz"
    Then the custom model deploy response status should be "404"

Custom model deployed with a display name shows that name
    [Documentation]    Validates that the display name entered at deploy time is persisted
    ...    on the deployment, so users can give meaningful names to deployed custom models.
    [Tags]    custom-models    deploy    gpu
    [Teardown]    Run Keywords    Remove custom model deployment if present
    ...    AND    Reset Custom Models In Test Project
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And project quota is set to    gpu_count=2
    And a custom model is onboarded in the project
    And custom model onboarding status should be "Ready"
    When custom model is deployed as an AIM service with display name    My TinyLlama
    Then deployed AIMService should show the deploy display name
    When custom model deployment is removed
    Then custom model deployment should be removed
