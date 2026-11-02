# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Business-logic keywords for serving a deployment together with LoRA adapters.
...                 Owns all TEST_* state; tests never touch the API layer directly.
Resource            api/artifacts.resource
Resource            resources/airm_projects.resource
Resource            aiwb_adapters.resource
Resource            aiwb_aims.resource
Library             AIMModelHelper
Library             AutoscalingPayload
Library             Collections
Library             String


*** Keywords ***
An adapter-capable AIM exists in system
    [Documentation]    Selects a model whose serving profile can carry adapters and pins that
    ...    profile for later deploys, the way a caller who actually intends to serve an adapter
    ...    must. Kept apart from `An AIM exists in system`: every other scenario in this suite
    ...    deliberately avoids resolving a real adapter-capable profile so it never schedules a
    ...    workload, and reusing that keyword here would mean either changing its behavior or
    ...    letting the two selections collide on the same TEST_AIM_NAME.
    ${resource_name}    ${profile_name}    ${gpu_count}=
    ...    Smallest adapter-capable AIM resource name, profile and GPU count
    ${response}=    Get AIM    ${resource_name}    expected_status=200
    VAR    ${TEST_AIM_NAME}    ${resource_name}    scope=TEST
    VAR    ${TEST_AIM}    ${response.json()}    scope=TEST
    ${display_name}=    Evaluate
    ...    $response.json().get('status', {}).get('imageMetadata', {}).get('model', {}).get('title') or $resource_name
    VAR    ${TEST_AIM_DISPLAY_NAME}    ${display_name}    scope=TEST
    VAR    ${TEST_AIM_GPU_COUNT}    ${gpu_count}    scope=TEST
    VAR    ${TEST_ADAPTER_CAPABLE_PROFILE_NAME}    ${profile_name}    scope=TEST

The project has adapter-serving quota available
    [Documentation]    Selects the adapter-capable AIM/profile before applying its matching quota.
    An adapter-capable AIM exists in system
    Set project quota for model GPU count    ${TEST_AIM_GPU_COUNT}

An AIM whose serving hardware cannot carry adapters exists in system
    [Documentation]    Selects a model together with one of its serving profiles that does not
    ...    declare adapter support, and pins that profile for the deploy, the way a user who chose
    ...    that hardware would. Kept apart from `An AIM exists in system` for the same reason its
    ...    adapter-capable sibling is: both resolve a profile of their own, and sharing the keyword
    ...    would let the two selections collide on the same TEST_AIM_NAME.
    ${resource_name}    ${profile_name}=    Smallest AIM resource name and profile that cannot serve adapters
    ${response}=    Get AIM    ${resource_name}    expected_status=200
    VAR    ${TEST_AIM_NAME}    ${resource_name}    scope=TEST
    VAR    ${TEST_AIM}    ${response.json()}    scope=TEST
    VAR    ${TEST_ADAPTER_INCAPABLE_PROFILE_NAME}    ${profile_name}    scope=TEST

An adapter the model can serve exists in the project
    [Documentation]    Seeds an adapter declaring the selected model's own canonical id, the way a
    ...    fine-tuning run against that model leaves one behind, with weight files already sitting
    ...    at the storage location the artifact declares -- without them there is nothing for the
    ...    engine to download, and an adapter it can never download is not one it can serve. The id
    ...    is read off the model at test time rather than written down here, because an adapter is
    ...    only attachable when the two agree on exactly the same identifier.
    ${namespace}=    Get Project Namespace
    ${aim_id}=    Resolve Cluster Model aimId    ${TEST_AIM_NAME}
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-serves-${suffix}
    VAR    ${display_name}    E2E LoRA adapter
    ${uri}=    Write Adapter Weights To Project Storage    ${namespace}    ${name}
    Track Adapter Weights For Cleanup    ${namespace}    ${uri}
    Apply AIMArtifact CR
    ...    ${name}
    ...    ${namespace}
    ...    compatible_with=${aim_id}
    ...    display_name=${display_name}
    ...    rank=${ADAPTER_RANK}
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_SERVABLE_ADAPTER_NAME}    ${name}    scope=TEST
    VAR    ${TEST_SERVABLE_ADAPTER_DISPLAY_NAME}    ${display_name}    scope=TEST
    VAR    ${TEST_SERVABLE_ADAPTER_RANK}    ${ADAPTER_RANK}    scope=TEST

Another adapter the model can serve exists in the project
    [Documentation]    Seeds a second compatible adapter so a user can replace the deployment's
    ...    current selection without changing the model or supported rank.
    ${namespace}=    Get Project Namespace
    ${aim_id}=    Resolve Cluster Model aimId    ${TEST_AIM_NAME}
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-replacement-${suffix}
    VAR    ${display_name}    Replacement LoRA adapter
    VAR    ${rank}    ${32}
    ${uri}=    Write Adapter Weights To Project Storage    ${namespace}    ${name}
    Track Adapter Weights For Cleanup    ${namespace}    ${uri}
    Apply AIMArtifact CR    ${name}    ${namespace}    compatible_with=${aim_id}
    ...    display_name=${display_name}    rank=${rank}
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_REPLACEMENT_ADAPTER_NAME}    ${name}    scope=TEST
    VAR    ${TEST_REPLACEMENT_ADAPTER_DISPLAY_NAME}    ${display_name}    scope=TEST
    VAR    ${TEST_REPLACEMENT_ADAPTER_RANK}    ${rank}    scope=TEST

An adapter the model cannot serve exists in the project
    [Documentation]    Seeds an adapter declaring a base model this cluster does not hold, so the
    ...    only reason it cannot be attached is the declaration itself.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-mismatch-${suffix}
    Apply AIMArtifact CR    ${name}    ${namespace}    compatible_with=${ADAPTER_BASE_MODEL_ID}
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_UNSERVABLE_ADAPTER_NAME}    ${name}    scope=TEST

An adapter whose upload has not finished exists in the project
    [Documentation]    Registers an adapter through the upload flow and never sends the weights,
    ...    which is what a user who walked away mid-upload leaves behind. It declares the selected
    ...    model, so the unfinished upload is the only thing standing between it and a deployment.
    ${namespace}=    Get Project Namespace
    ${aim_id}=    Resolve Cluster Model aimId    ${TEST_AIM_NAME}
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${compatible_with}=    Create List    ${aim_id}
    ${response}=    Create Artifact For Upload
    ...    ${namespace}
    ...    example-org/e2e-pending-${suffix}
    ...    ${compatible_with}
    ...    expected_status=201
    VAR    ${name}    ${response.json()}[artifact][metadata][name]
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_PENDING_UPLOAD_ADAPTER_NAME}    ${name}    scope=TEST

The model is deployed without adapters
    ${deploy_data}=    Create Dictionary    replicas=${1}
    Deploy The Selected Model With    ${deploy_data}    expected_status=202

The model is deployed without adapters and cannot change them
    [Documentation]    Creates a running deployment that may serve the model but cannot accept
    ...    adapters after creation, so attachment choices can explain why it is unavailable.
    The model is deployed without adapters
    Wait for AIM workload to reach state    Running

The model is deployed with the adapter it can serve and adapters left free to change
    ${adapters}=    Create List    ${TEST_SERVABLE_ADAPTER_NAME}
    ${deploy_data}=    Create Dictionary    replicas=${1}    adapters=${adapters}    adapterMode=dynamic
    Deploy The Selected Model With    ${deploy_data}    expected_status=202

The model is deployed with a compatible adapter attached
    [Documentation]    Pins the adapter-capable profile resolved earlier, so the deployment actually
    ...    lands on hardware that can serve the adapter it is asked to carry.
    ${adapters}=    Create List    ${TEST_SERVABLE_ADAPTER_NAME}
    ${deploy_data}=    Create Dictionary    replicas=${1}    adapters=${adapters}    adapterMode=dynamic
    ...    profileName=${TEST_ADAPTER_CAPABLE_PROFILE_NAME}
    Deploy The Selected Model With    ${deploy_data}    expected_status=202

The model is deployed with a compatible adapter and a maximum LoRA rank
    [Documentation]    Deploys an adapter-capable AIM with one attached adapter and an explicit
    ...    maximum rank so the deployment details UI can present both values.
    VAR    ${max_rank}    ${64}
    ${adapters}=    Create List    ${TEST_SERVABLE_ADAPTER_NAME}
    ${deploy_data}=    Create Dictionary
    ...    replicas=${1}
    ...    adapters=${adapters}
    ...    adapterMode=dynamic
    ...    profileName=${TEST_ADAPTER_CAPABLE_PROFILE_NAME}
    ...    maxLoraRank=${max_rank}
    Deploy The Selected Model With    ${deploy_data}    expected_status=202
    Wait for AIM workload to reach state    Running
    VAR    ${TEST_MAX_LORA_RANK}    ${max_rank}    scope=TEST

The model is deployed onto that hardware with no adapters but free to change them
    [Documentation]    Pins the adapter-capable profile resolved earlier and asks only that adapters
    ...    stay free to change, naming none. The counterpart of the request the incapable hardware
    ...    turns away, so the two differ in nothing but the hardware they point at.
    ${deploy_data}=    Create Dictionary    replicas=${1}    adapterMode=dynamic
    ...    profileName=${TEST_ADAPTER_CAPABLE_PROFILE_NAME}
    Deploy The Selected Model With    ${deploy_data}

The user attempts to deploy the model with the adapter it cannot serve
    ${adapters}=    Create List    ${TEST_UNSERVABLE_ADAPTER_NAME}
    ${deploy_data}=    Create Dictionary    replicas=${1}    adapters=${adapters}
    Deploy The Selected Model With    ${deploy_data}

The user attempts to deploy the model onto that hardware with a compatible adapter
    [Documentation]    The adapter is one the model can serve and its weights are in place, so the
    ...    hardware the request points at is the only thing left that can stand in the way.
    ${adapters}=    Create List    ${TEST_SERVABLE_ADAPTER_NAME}
    ${deploy_data}=    Create Dictionary    replicas=${1}    adapters=${adapters}
    ...    profileName=${TEST_ADAPTER_INCAPABLE_PROFILE_NAME}
    Deploy The Selected Model With    ${deploy_data}

The user attempts to deploy the model onto that hardware with no adapters but free to change them
    [Documentation]    Names nothing to start with, so the request rests entirely on the freedom to
    ...    change adapters later -- which is settled at this moment and can never be granted
    ...    afterwards, and so has to be answered now rather than once the deployment is running.
    ${deploy_data}=    Create Dictionary    replicas=${1}    adapterMode=dynamic
    ...    profileName=${TEST_ADAPTER_INCAPABLE_PROFILE_NAME}
    Deploy The Selected Model With    ${deploy_data}

The user attempts to deploy the model with the adapter whose upload has not finished
    ${adapters}=    Create List    ${TEST_PENDING_UPLOAD_ADAPTER_NAME}
    ${deploy_data}=    Create Dictionary    replicas=${1}    adapters=${adapters}
    Deploy The Selected Model With    ${deploy_data}

The user attempts to deploy the model with both adapters
    ${adapters}=    Create List    ${TEST_SERVABLE_ADAPTER_NAME}    ${TEST_UNSERVABLE_ADAPTER_NAME}
    ${deploy_data}=    Create Dictionary    replicas=${1}    adapters=${adapters}
    Deploy The Selected Model With    ${deploy_data}

The deployment should report no adapters
    [Documentation]    Nobody attached anything, so the deployment has nothing to report about
    ...    adapters. Whether that is reported as absent or as an empty collection is the engine's
    ...    to decide -- what matters is that the platform never invents an entry of its own.
    ${response}=    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=200
    ${status}=    Get From Dictionary    ${response.json()}    status
    ${adapters}=    Get From Dictionary    ${status}    adapters    default=${None}
    IF    $adapters is not None
        Should Be Empty    ${adapters}
        ...    msg=A deployment with no adapters should report none, got: ${adapters}
    END

The deployment should record the adapter it was asked to serve
    [Documentation]    Read off the deployment's own manifest rather than the API's echo of the
    ...    request, so the adapter is proven to reach the resource the engine reconciles -- named,
    ...    and typed as the artifact the engine resolves it against.
    ${namespace}=    Get Project Namespace
    AIMService CR Should Record Adapter    ${TEST_DEPLOYED_SERVICE_NAME}    ${namespace}
    ...    ${TEST_SERVABLE_ADAPTER_NAME}

The deployment should record that its adapters may change while it runs
    [Documentation]    Read off the deployment's own manifest, for the same reason the adapter
    ...    itself is: the choice is fixed at creation and cannot be corrected later, so the API's
    ...    echo of the request is not evidence the deployment actually carries it.
    ${namespace}=    Get Project Namespace
    AIMService CR Should Allow Adapters To Change    ${TEST_DEPLOYED_SERVICE_NAME}    ${namespace}

The deployment should become ready and serve the adapter
    [Documentation]    Proves the path actually works end to end: the deployment comes up on the
    ...    pinned adapter-capable profile, and the engine reports the attached adapter downloaded
    ...    rather than rejected. Manifest-only checks elsewhere in this suite cannot catch a serving
    ...    path that is broken in practice; this is the one scenario that puts a real profile on a
    ...    GPU to confirm it.
    Wait for AIM workload to reach state    Running
    Wait Until Keyword Succeeds    20 min    10 sec
    ...    The adapter should be reported as downloaded

The adapter should be reported as downloaded
    ${response}=    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=200
    ${status}=    Get From Dictionary    ${response.json()}    status
    ${adapters}=    Get From Dictionary    ${status}    adapters    default=${None}
    ${entries}=    Evaluate
    ...    [a for a in ($adapters or []) if a.get("name") == "${TEST_SERVABLE_ADAPTER_NAME}"]
    Should Not Be Empty    ${entries}
    ...    msg=Deployment should report the attached adapter, got: ${adapters}
    ${state}=    Get From Dictionary    ${entries}[0]    state    default=${None}
    Should Not Be Equal As Strings    ${state}    LoadRejected
    ...    msg=The engine rejected the adapter it was asked to serve: ${entries}[0]
    Should Be Equal As Strings    ${state}    Downloaded
    ...    msg=Adapter should be reported as downloaded and available to serve, got state: ${state}

The deployment should be refused
    Should Be Equal As Integers    ${TEST_ADAPTER_DEPLOY_RESPONSE.status_code}    400
    ...    msg=Expected the deploy to be refused, got ${TEST_ADAPTER_DEPLOY_RESPONSE.status_code}

The deployment should be accepted
    [Documentation]    The counterpart of `The deployment should be refused`, so a scenario proving
    ...    a request still goes through reads the response the same way the refusals do.
    Should Be Equal As Integers    ${TEST_ADAPTER_DEPLOY_RESPONSE.status_code}    202
    ...    msg=Expected the deploy to be accepted, got ${TEST_ADAPTER_DEPLOY_RESPONSE.status_code}

The refusal should say the adapter cannot serve this model
    ${detail}=    The Adapter Deploy Refusal Detail
    Should Contain    ${detail}    ${TEST_UNSERVABLE_ADAPTER_NAME}
    ...    msg=Refusal should name the adapter at fault, got: ${detail}
    Should Contain    ${detail}    among the models it can serve
    ...    msg=Refusal should explain the adapter does not serve this model, got: ${detail}

The refusal should say the adapter has no uploaded weights
    ${detail}=    The Adapter Deploy Refusal Detail
    Should Contain    ${detail}    ${TEST_PENDING_UPLOAD_ADAPTER_NAME}
    ...    msg=Refusal should name the adapter at fault, got: ${detail}
    Should Contain    ${detail}    no uploaded weights yet
    ...    msg=Refusal should explain the weights never arrived, got: ${detail}

The refusal should say the chosen hardware cannot serve adapters
    [Documentation]    Points at the serving hardware the user picked, and names it, so they know
    ...    which of their choices to change. A refusal that only said adapters were unavailable
    ...    would leave them guessing between the model, the adapter and the hardware -- and the
    ...    hardware is the one they can swap without giving up the adapter.
    ${detail}=    The Adapter Deploy Refusal Detail
    Should Contain    ${detail}    ${TEST_ADAPTER_INCAPABLE_PROFILE_NAME}
    ...    msg=Refusal should name the serving hardware at fault, got: ${detail}
    Should Contain    ${detail}    cannot serve adapters
    ...    msg=Refusal should explain the hardware cannot carry adapters, got: ${detail}

The refusal should name only the adapter that cannot be served
    [Documentation]    A refusal that names every adapter in the request tells the user nothing
    ...    about which one to replace.
    ${detail}=    The Adapter Deploy Refusal Detail
    Should Contain    ${detail}    ${TEST_UNSERVABLE_ADAPTER_NAME}
    ...    msg=Refusal should name the adapter at fault, got: ${detail}
    Should Not Contain    ${detail}    ${TEST_SERVABLE_ADAPTER_NAME}
    ...    msg=Refusal should not blame the adapter that can be served, got: ${detail}

No deployment should have been created
    [Documentation]    A refused deploy leaves nothing behind, so the user can correct the request
    ...    and try again rather than clean up a half-made deployment first.
    ${after}=    Deployment Count For The Selected Model
    Should Be Equal As Integers    ${after}    ${TEST_DEPLOYMENT_COUNT_BEFORE}
    ...    msg=A refused deploy must leave the project's deployments untouched

The deployment using the adapter is removed
    [Documentation]    Takes the deployment away so nothing is serving the adapter any more.
    ${namespace}=    Get Project Namespace
    Delete AIMService CR    ${TEST_BLOCKING_SERVICE_NAME}    ${namespace}

The adapter artifact removal should be accepted
    The adapter artifact delete response status should be "202"

Deploy The Selected Model With
    [Documentation]    Sends the deploy request and records what it is asked about later: the
    ...    response itself, and -- when the deploy was accepted -- the deployment's own resource
    ...    name, which is the only handle a manifest-level assertion or a teardown can use.
    [Arguments]    ${deploy_data}    ${expected_status}=any
    ${namespace}=    Get Project Namespace
    ${before}=    Deployment Count For The Selected Model
    VAR    ${TEST_DEPLOYMENT_COUNT_BEFORE}    ${before}    scope=TEST
    ${response}=    Deploy AIM    ${TEST_AIM_NAME}    ${deploy_data}    ${namespace}
    ...    expected_status=${expected_status}
    VAR    ${TEST_ADAPTER_DEPLOY_RESPONSE}    ${response}    scope=TEST
    IF    ${response.status_code} != 202
        RETURN
    END
    VAR    ${service_id}    ${response.json()}[id]
    VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST
    ${detail}=    Get AIM Service By ID    ${service_id}    expected_status=200
    VAR    ${TEST_DEPLOYED_SERVICE_NAME}    ${detail.json()}[metadata][name]    scope=TEST

Deployment Count For The Selected Model
    [Documentation]    How many deployments of the selected model the project currently holds.
    ...    Counted before and after rather than asserted absent, because the project is shared with
    ...    other suites that may legitimately be running a deployment of the same model.
    ${namespace}=    Get Project Namespace
    ${response}=    List AIM Services    ${namespace}    expected_status=200
    ${services}=    Get From Dictionary    ${response.json()}    data
    ${matching}=    Create List
    FOR    ${service}    IN    @{services}
        ${model}=    Get From Dictionary    ${service}[spec]    model
        ${name}=    Get From Dictionary    ${model}    name    default=${EMPTY}
        IF    "${name}" == "${TEST_AIM_NAME}"
            Append To List    ${matching}    ${name}
        END
    END
    ${count}=    Get Length    ${matching}
    RETURN    ${count}

The deployment created through the wizard is tracked
    [Documentation]    Finds the deployment the UI just created so shared teardown can remove
    ...    only this test's resource after the user journey finishes.
    Wait Until Keyword Succeeds    30 sec    2 sec
    ...    Track the selected model's deployment

Track the selected model's deployment
    [Documentation]    Performs one lookup for the deployment created from the selected model.
    ${namespace}=    Get Project Namespace
    ${response}=    List AIM Services    ${namespace}    expected_status=200
    ${services}=    Get From Dictionary    ${response.json()}    data
    ${matching}=    Create List
    FOR    ${service}    IN    @{services}
        ${model}=    Get From Dictionary    ${service}[spec]    model
        ${name}=    Get From Dictionary    ${model}    name    default=${EMPTY}
        IF    "${name}" == "${TEST_AIM_NAME}"
            Append To List    ${matching}    ${service}
        END
    END
    ${count}=    Get Length    ${matching}
    Should Be Equal As Integers    ${count}    1
    ...    msg=Expected exactly one deployment of ${TEST_AIM_NAME}, got: ${matching}
    VAR    ${service}    ${matching}[0]
    VAR    ${TEST_AIM_ID}    ${service}[id]    scope=TEST
    VAR    ${TEST_DEPLOYED_SERVICE_NAME}    ${service}[metadata][name]    scope=TEST

The Adapter Deploy Refusal Detail
    [Documentation]    The explanation the refusal carried, so each assertion reads it the same way.
    VAR    ${body}    ${TEST_ADAPTER_DEPLOY_RESPONSE.json()}
    ${detail}=    Get From Dictionary    ${body}    detail
    RETURN    ${detail}

Remove the deployment created by this test
    [Documentation]    Teardown for the scenarios that deploy. Undeploys through the API and then
    ...    confirms removal directly, because suite cleanup cannot delete an adapter while a
    ...    deployment still references it and an undeploy the cluster has not finished would leave
    ...    the adapter pinned.
    Remove AIM deployment if present
    ${service}=    Get Variable Value    ${TEST_DEPLOYED_SERVICE_NAME}    ${None}
    IF    $service is None
        RETURN
    END
    ${namespace}=    Get Project Namespace
    Delete AIMService CR    ${service}    ${namespace}

Seed Deployment With Adapter Mode
    [Documentation]    Puts in place the deployment a change scenario acts on and records the
    ...    handles that the change, the manifest assertions, and the teardown all need.
    ...
    ...    The deployment is created directly rather than deployed: a change reads and rewrites the
    ...    adapter set the deployment records, so nothing here needs a model actually running.
    ...    Pinning a real adapter-capable profile would schedule the workload for real, holding an
    ...    accelerator this suite never needs -- the CR pins an unresolvable profile name instead,
    ...    which keeps it from scheduling at all.
    [Arguments]    ${adapter_mode}    ${adapter_name}=${EMPTY}
    ${namespace}=    Get Project Namespace
    ${workload_id}=    Evaluate    str(uuid.uuid4())    modules=uuid
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-change-${suffix}
    Apply AIMService With Adapter Mode    ${name}    ${TEST_AIM_NAME}    ${namespace}    ${workload_id}
    ...    adapter_mode=${adapter_mode}    adapter_name=${adapter_name}
    VAR    ${TEST_AIM_ID}    ${workload_id}    scope=TEST
    VAR    ${TEST_DEPLOYED_SERVICE_NAME}    ${name}    scope=TEST

A deployment whose adapters may change while it runs exists
    [Documentation]    A deployment free to gain and lose adapters, serving none so far.
    Seed Deployment With Adapter Mode    dynamic

A deployment whose adapters may change while it runs is serving that adapter
    [Documentation]    The same deployment, already serving the adapter the project holds, so a
    ...    scenario can take an adapter away rather than only add one.
    Seed Deployment With Adapter Mode    dynamic    ${TEST_SERVABLE_ADAPTER_NAME}

A deployment whose adapters were fixed when it was created exists
    [Documentation]    A deployment created without the freedom to change its adapters, which is
    ...    the default and cannot be granted afterwards.
    Seed Deployment With Adapter Mode    static

A deployment whose adapters were fixed when it was created is serving that adapter
    [Documentation]    The same deployment, already serving the adapter the project holds, so a
    ...    scenario that changes something other than the adapters starts from a set there is
    ...    something to lose.
    Seed Deployment With Adapter Mode    static    ${TEST_SERVABLE_ADAPTER_NAME}

The user changes the adapters the deployment should serve
    ${adapters}=    Create List    ${TEST_SERVABLE_ADAPTER_NAME}
    Change The Adapters Of Deployment    ${TEST_AIM_ID}    ${adapters}

The user removes every adapter from the deployment
    ${adapters}=    Create List
    Change The Adapters Of Deployment    ${TEST_AIM_ID}    ${adapters}

The user changes the adapters and how the deployment scales at once
    [Documentation]    Both changes travel in one request, which is the point of the scenario:
    ...    they either both take effect or neither does.
    ${adapters}=    Create List    ${TEST_SERVABLE_ADAPTER_NAME}
    ${scaling}=    The scaling a change asks for
    Change The Adapters Of Deployment    ${TEST_AIM_ID}    ${adapters}    scaling=${scaling}

The user changes only how the deployment scales
    [Documentation]    Asks for a new scaling policy without naming any adapters, to prove that
    ...    whether adapters may change gates adapter changes only, not the request as a whole.
    ${namespace}=    Get Project Namespace
    ${scaling}=    The scaling a change asks for
    ${response}=    Update AIM Service Scaling Policy    ${TEST_AIM_ID}    ${scaling}    ${namespace}
    VAR    ${TEST_ADAPTER_CHANGE_RESPONSE}    ${response}    scope=TEST

The scaling a change asks for
    [Documentation]    The one scaling policy every change scenario asks for, kept as the single
    ...    thing the assertion checks the deployment against so the two cannot drift apart. The
    ...    metrics come from the shared builder because the engine only reconciles the CRD-native
    ...    shape, and Robot's ``key=value`` arguments are plain strings -- a nested structure
    ...    written that way would reach the cluster as text.
    ${autoscaling}=    Create KEDA Policy Config
    ${scaling}=    Create Dictionary    minReplicas=${1}    maxReplicas=${3}    autoScaling=${autoscaling}
    VAR    ${TEST_REQUESTED_SCALING}    ${scaling}    scope=TEST
    RETURN    ${scaling}

The user attempts to change the deployment to an adapter the model cannot serve
    ${adapters}=    Create List    ${TEST_UNSERVABLE_ADAPTER_NAME}
    Change The Adapters Of Deployment    ${TEST_AIM_ID}    ${adapters}

The user attempts to change the adapters of a deployment that does not exist
    [Documentation]    Names a deployment the project never had. What is asked for does not
    ...    matter -- there is nothing to change it on.
    ${missing}=    Evaluate    str(uuid.uuid4())    modules=uuid
    ${adapters}=    Create List
    Change The Adapters Of Deployment    ${missing}    ${adapters}

The change should be accepted
    Should Be Equal As Integers    ${TEST_ADAPTER_CHANGE_RESPONSE.status_code}    200
    ...    msg=Expected the adapter change to be accepted, got ${TEST_ADAPTER_CHANGE_RESPONSE.status_code}

The change should be refused
    Should Be Equal As Integers    ${TEST_ADAPTER_CHANGE_RESPONSE.status_code}    400
    ...    msg=Expected the adapter change to be refused, got ${TEST_ADAPTER_CHANGE_RESPONSE.status_code}

The deployment should not be found
    Should Be Equal As Integers    ${TEST_ADAPTER_CHANGE_RESPONSE.status_code}    404
    ...    msg=A missing deployment should be reported as not found, got ${TEST_ADAPTER_CHANGE_RESPONSE.status_code}

The deployment should record the scaling it was asked for
    [Documentation]    Read off the deployment's own manifest alongside the adapters, because the
    ...    claim under test is that one request carried both: adapters recorded without the
    ...    scaling would be exactly the half-applied outcome a single update rules out.
    ${namespace}=    Get Project Namespace
    AIMService CR Should Record Scaling
    ...    ${TEST_DEPLOYED_SERVICE_NAME}    ${namespace}    ${TEST_REQUESTED_SCALING}

The deployment should record the adapters it was asked to serve
    [Documentation]    Read off the deployment's own manifest rather than the API's echo of the
    ...    request, and as a whole set, because a change replaces the set outright: an adapter the
    ...    change was meant to drop has to be gone, not merely unmentioned.
    ${namespace}=    Get Project Namespace
    ${expected}=    Create List    ${TEST_SERVABLE_ADAPTER_NAME}
    AIMService CR Should Record Adapters    ${TEST_DEPLOYED_SERVICE_NAME}    ${namespace}    ${expected}

The deployment should still record the adapter it was already serving
    [Documentation]    A change that never mentions adapters has to leave the set exactly as it
    ...    found it. Checked against a deployment that starts out serving something, because on
    ...    one serving nothing an omission that silently detached everything would look identical
    ...    to one that preserved it.
    ${namespace}=    Get Project Namespace
    ${expected}=    Create List    ${TEST_SERVABLE_ADAPTER_NAME}
    AIMService CR Should Record Adapters    ${TEST_DEPLOYED_SERVICE_NAME}    ${namespace}    ${expected}

The deployment should record no adapters
    [Documentation]    Serves both the scenario that takes every adapter away and the ones whose
    ...    change was refused, where the deployment must be exactly as it was left.
    ${namespace}=    Get Project Namespace
    ${expected}=    Create List
    AIMService CR Should Record Adapters    ${TEST_DEPLOYED_SERVICE_NAME}    ${namespace}    ${expected}

The deployment should not yet report the new adapters as available for inference
    [Documentation]    Accepting a change records what was asked for; it does not make an adapter
    ...    servable. What each adapter is doing is the engine's to report and the platform passes
    ...    it through untouched, so nothing here may say an adapter is ready to serve before the
    ...    engine has said so.
    ${response}=    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=200
    ${status}=    Get From Dictionary    ${response.json()}    status
    ${adapters}=    Get From Dictionary    ${status}    adapters    default=${None}
    ${states}=    Evaluate    {entry.get("state") for entry in ($adapters or [])}
    ${unexpected}=    Evaluate    ${states} - {"Pending", "Downloading", "Downloaded", "Deleting", "LoadRejected"}
    Should Be Empty    ${unexpected}
    ...    msg=An adapter must not be reported as available for inference before the engine says so, got: ${adapters}

The refusal should say the deployment cannot change its adapters
    ${detail}=    The Adapter Change Refusal Detail
    Should Contain    ${detail}    does not admit adapter changes
    ...    msg=Refusal should explain the deployment was fixed when it was created, got: ${detail}

The refusal should say the requested adapter cannot serve this model
    ${detail}=    The Adapter Change Refusal Detail
    Should Contain    ${detail}    ${TEST_UNSERVABLE_ADAPTER_NAME}
    ...    msg=Refusal should name the adapter at fault, got: ${detail}
    Should Contain    ${detail}    among the models it can serve
    ...    msg=Refusal should explain the adapter does not serve this model, got: ${detail}

The released adapter is deleted
    ${namespace}=    Get Project Namespace
    ${response}=    Delete Artifact    ${namespace}    ${TEST_SERVABLE_ADAPTER_NAME}
    VAR    ${TEST_ADAPTER_DELETE_RESPONSE}    ${response}    scope=TEST

The released adapter removal should be accepted
    The adapter artifact delete response status should be "202"

The released adapter should no longer appear in the project list
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    60 sec    5 sec
    ...    AIMArtifact CR Should Be Absent    ${TEST_SERVABLE_ADAPTER_NAME}    ${namespace}
    The project adapter artifact list is retrieved
    ${names}=    Adapter Names In List
    Should Not Contain    ${names}    ${TEST_SERVABLE_ADAPTER_NAME}

Change The Adapters Of Deployment
    [Documentation]    Asks for a new adapter set and keeps the response, which is what every
    ...    outcome in these scenarios is read from.
    [Arguments]    ${deployment_id}    ${adapters}    ${scaling}=${None}
    ${namespace}=    Get Project Namespace
    ${response}=    Update AIM Service Adapters    ${deployment_id}    ${adapters}    ${namespace}
    ...    scaling=${scaling}
    VAR    ${TEST_ADAPTER_CHANGE_RESPONSE}    ${response}    scope=TEST

The Adapter Change Refusal Detail
    [Documentation]    The explanation the refusal carried, so each assertion reads it the same way.
    VAR    ${body}    ${TEST_ADAPTER_CHANGE_RESPONSE.json()}
    ${detail}=    Get From Dictionary    ${body}    detail
    RETURN    ${detail}
