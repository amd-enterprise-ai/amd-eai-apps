# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Business-logic keywords for project adapter artifact scenarios.
...                 Owns all TEST_* state; tests never touch the API layer directly.
Resource            api/artifacts.resource
Resource            resources/airm_projects.resource
Resource            aiwb_common.resource
Library             AIMModelHelper
Library             Collections
Library             String


*** Variables ***
# A base model nothing in the test cluster holds, so scenarios prove an adapter is registered and
# ready on the strength of its declaration alone rather than on something resolving it.
${ADAPTER_BASE_MODEL_ID}        example-org/e2e-base-model
# A second, distinct base model used by scenarios that must tell two adapters apart by the
# model each declares, such as filtering the LoRA list down to one of them.
${ADAPTER_OTHER_BASE_MODEL_ID}    example-org/e2e-other-base-model
${ADAPTER_DESCRIPTION}          Adapter registered by the AIWB E2E suite.
${ADAPTER_RANK}                 ${16}
${ADAPTER_SUBMITTER}            e2e-finetuning@example.com
# An adapter may carry more than the PEFT files at the root of its storage. This is the extra file
# scenarios register in a subdirectory of the adapter's own.
${ADAPTER_NESTED_FILE}          extra/notes.md


*** Keywords ***
A fine-tuning adapter artifact exists in the project
    [Documentation]    Creates an adapter artifact attributed to the fine-tuning engine,
    ...    the way a completed fine-tuning run leaves one behind. Declares its rank the way a
    ...    real run does, so scenarios that read the rank back have data to find.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-adapter-${suffix}
    Apply AIMArtifact CR    ${name}    ${namespace}
    ...    description=${ADAPTER_DESCRIPTION}    rank=${ADAPTER_RANK}    submitter=${ADAPTER_SUBMITTER}
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_ADAPTER_NAME}    ${name}    scope=TEST

Registered LoRA adapters exist with different base models
    [Documentation]    Creates two adapters attached to different base models, so a filter on
    ...    one model excludes the other.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-adapter-${suffix}
    Apply AIMArtifact CR    ${name}    ${namespace}    description=${ADAPTER_DESCRIPTION}
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_ADAPTER_NAME}    ${name}    scope=TEST

    ${other_suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${other_name}    e2e-adapter-${other_suffix}
    Apply AIMArtifact CR    ${other_name}    ${namespace}
    ...    description=${ADAPTER_DESCRIPTION}    compatible_with=${ADAPTER_OTHER_BASE_MODEL_ID}
    Track Adapter Artifact For Cleanup    ${namespace}    ${other_name}
    VAR    ${TEST_OTHER_ADAPTER_NAME}    ${other_name}    scope=TEST

An adapter artifact created outside the platform exists in the project
    [Documentation]    Creates an adapter artifact attributed to a foreign operator.
    ...    The platform must neither expose nor delete it -- so it is deliberately not
    ...    tracked for API cleanup; project teardown removes it with the namespace.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-foreign-adapter-${suffix}
    Apply AIMArtifact CR    ${name}    ${namespace}    managed_by=some-other-operator
    VAR    ${TEST_FOREIGN_ADAPTER_NAME}    ${name}    scope=TEST

Multiple adapter artifacts exist in the project
    [Documentation]    Creates enough adapter artifacts that a single page cannot hold them all.
    [Arguments]    ${count}=2

    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${names}=    Apply Multiple AIMArtifact CRs    ${namespace}    ${count}    name_prefix=e2e-page-adapter-${suffix}
    FOR    ${name}    IN    @{names}
        Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    END
    ${created_count}=    Get Length    ${names}
    VAR    ${TEST_ADAPTER_COUNT}    ${created_count}    scope=TEST

Adapter weights that no artifact claims exist in the project storage
    [Documentation]    Writes a complete set of LoRA weight files into the project's adapter
    ...    storage without registering anything -- what a deleted artifact or a training job that
    ...    never registered its output leaves behind.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-unclaimed-${suffix}
    ${uri}=    Write Adapter Weights To Project Storage    ${namespace}    ${name}
    Track Adapter Weights For Cleanup    ${namespace}    ${uri}
    VAR    ${TEST_UNCLAIMED_ADAPTER_URI}    ${uri}    scope=TEST

An adapter whose weights were uploaded through the workbench
    [Documentation]    Registers an adapter for upload and writes its weight files to the locations
    ...    the workbench hands back. The platform chose where those files live, which is what makes
    ...    the storage its own to reclaim later.
    ${files}=    Create List    adapter_config.json    adapter_model.safetensors
    Upload An Adapter Declaring Files    ${files}

An adapter uploaded with an extra file in a subdirectory
    [Documentation]    Registers an adapter that carries something beyond the weight files sitting at
    ...    the root of its storage -- notes kept with them, in a subdirectory of the adapter's own.
    ...    The project accepts that file as part of the adapter when it is registered, which is what
    ...    makes it the adapter's to hand back later.
    ${files}=    Create List    adapter_config.json    adapter_model.safetensors    ${ADAPTER_NESTED_FILE}
    Upload An Adapter Declaring Files    ${files}

Upload An Adapter Declaring Files
    [Documentation]    Registers an adapter for the named files and writes one to each location the
    ...    workbench hands back, whatever layout those names describe.
    [Arguments]    ${files}
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${compatible_with}=    Create List    ${ADAPTER_BASE_MODEL_ID}
    ${response}=    Create Artifact With Upload
    ...    ${namespace}
    ...    example-org/e2e-uploaded-adapter-${suffix}
    ...    ${compatible_with}
    ...    ${files}
    ...    description=${ADAPTER_DESCRIPTION}
    ...    expected_status=201
    VAR    ${body}    ${response.json()}
    Track Adapter Artifact For Cleanup    ${namespace}    ${body}[artifact][metadata][name]
    Track Adapter Weights For Cleanup    ${namespace}    ${body}[storage][uri]
    Upload Adapter Weights To Provided Locations    ${body}[uploads]
    VAR    ${TEST_ADAPTER_NAME}    ${body}[artifact][metadata][name]    scope=TEST
    VAR    ${TEST_ADAPTER_STORAGE_URI}    ${body}[storage][uri]    scope=TEST
    ${stored}=    Objects Stored At Adapter Location    ${namespace}    ${TEST_ADAPTER_STORAGE_URI}
    Should Not Be Empty    ${stored}    The weights never reached storage, so nothing is there to reclaim

An adapter onboarded from storage the user already owned
    [Documentation]    The weights are put into the project's storage first and the adapter is
    ...    registered against where they already sit, so those files were never the platform's to
    ...    reclaim. What the location holds afterwards is recorded, because "untouched" is a
    ...    comparison against that and not merely a check that something survived.
    Adapter weights that no artifact claims exist in the project storage
    The user registers the unclaimed adapter weights from where they are stored
    ${namespace}=    Get Project Namespace
    VAR    ${TEST_ADAPTER_STORAGE_URI}    ${TEST_UNCLAIMED_ADAPTER_URI}    scope=TEST
    ${stored}=    Objects Stored At Adapter Location    ${namespace}    ${TEST_ADAPTER_STORAGE_URI}
    Should Not Be Empty    ${stored}    The user's files are missing before the delete even runs
    VAR    ${TEST_ADAPTER_STORAGE_CONTENTS}    ${stored}    scope=TEST

Adapter weights already in the project whose stored details record no rank
    [Documentation]    Weights the workbench itself took in are left with stored details that say
    ...    nothing about rank, because nothing on that path asks for one -- the same silence weights
    ...    arriving from a fine-tuning run can carry.
    An adapter whose weights were uploaded through the workbench

A fine-tuning run has left an adapter in project storage
    [Documentation]    Stands in for a completed LoRA fine-tuning run: the run's output is written to
    ...    the folder the workbench named for it, and the adapter the run produces records where its
    ...    weights landed inside that folder. The workbench chose where the whole run lives, which is
    ...    what makes all of it the platform's to reclaim once the adapter is discarded.
    ${namespace}=    Get Project Namespace
    ${run_uri}=    Write Fine-Tuning Run Output To Project Storage    ${namespace}    ${ADAPTER_BASE_MODEL_ID}
    Track Adapter Weights For Cleanup    ${namespace}    ${run_uri}
    ${adapter_uri}=    Fine-Tuned Adapter Location In Run    ${run_uri}
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-finetuned-adapter-${suffix}
    Apply AIMArtifact CR    ${name}    ${namespace}    source_uri=${adapter_uri}
    ...    description=${ADAPTER_DESCRIPTION}    rank=${ADAPTER_RANK}    submitter=${ADAPTER_SUBMITTER}
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_ADAPTER_NAME}    ${name}    scope=TEST
    VAR    ${TEST_RUN_STORAGE_URI}    ${run_uri}    scope=TEST
    ${stored}=    Objects Stored At Adapter Location    ${namespace}    ${run_uri}
    Should Not Be Empty    ${stored}    The run's output never reached storage, so nothing is there to reclaim

Another fine-tuning run of the same base model has stored its output
    [Documentation]    Runs of one base model sit side by side in the project's storage. What this one
    ...    holds is recorded, because "untouched" is a comparison against that and not merely a check
    ...    that something survived.
    ${namespace}=    Get Project Namespace
    ${run_uri}=    Write Fine-Tuning Run Output To Project Storage    ${namespace}    ${ADAPTER_BASE_MODEL_ID}
    Track Adapter Weights For Cleanup    ${namespace}    ${run_uri}
    ${stored}=    Objects Stored At Adapter Location    ${namespace}    ${run_uri}
    Should Not Be Empty    ${stored}    The other run's output never reached storage
    VAR    ${TEST_OTHER_RUN_STORAGE_URI}    ${run_uri}    scope=TEST
    VAR    ${TEST_OTHER_RUN_STORAGE_CONTENTS}    ${stored}    scope=TEST

A second adapter registered against the same stored weights
    [Documentation]    Registers another adapter against the location the first adapter's weights
    ...    already occupy, so one set of files is claimed twice over.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${compatible_with}=    Create List    ${ADAPTER_BASE_MODEL_ID}
    ${response}=    Create Artifact From S3 Source
    ...    ${namespace}
    ...    ${TEST_ADAPTER_STORAGE_URI}
    ...    example-org/e2e-second-adapter-${suffix}
    ...    ${compatible_with}
    ...    expected_status=201
    VAR    ${name}    ${response.json()}[artifact][metadata][name]
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_SECOND_ADAPTER_NAME}    ${name}    scope=TEST

The user registers the stored adapter weights and states their rank
    [Documentation]    Onboards the weights already sitting in the project, declaring the rank as
    ...    part of the registration.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${compatible_with}=    Create List    ${ADAPTER_BASE_MODEL_ID}
    ${response}=    Create Artifact From S3 Source
    ...    ${namespace}
    ...    ${TEST_ADAPTER_STORAGE_URI}
    ...    example-org/e2e-ranked-adapter-${suffix}
    ...    ${compatible_with}
    ...    rank=${ADAPTER_RANK}
    ...    expected_status=201
    VAR    ${adapter}    ${response.json()}[artifact][metadata][name]
    Track Adapter Artifact For Cleanup    ${namespace}    ${adapter}
    VAR    ${TEST_ADAPTER_NAME}    ${adapter}    scope=TEST

The project adapter artifact list is retrieved
    ${namespace}=    Get Project Namespace
    ${response}=    List Artifacts    ${namespace}    expected_status=200
    VAR    ${TEST_ADAPTER_LIST}    ${response.json()}    scope=TEST

The project adapter artifact list is retrieved for adapters only
    ${namespace}=    Get Project Namespace
    ${response}=    List Artifacts    ${namespace}    expected_status=200    type=adapter
    VAR    ${TEST_ADAPTER_LIST}    ${response.json()}    scope=TEST

The project adapter artifact list of ready adapters is retrieved
    ${namespace}=    Get Project Namespace
    ${response}=    List Artifacts    ${namespace}    expected_status=200    readiness=Ready
    VAR    ${TEST_ADAPTER_LIST}    ${response.json()}    scope=TEST

The user registers the unclaimed adapter weights from where they are stored
    [Documentation]    Adopting weights the project already holds is the same onboarding the API
    ...    offers for any existing storage location -- there is no separate claim operation.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${compatible_with}=    Create List    ${ADAPTER_BASE_MODEL_ID}
    ${response}=    Create Artifact From S3 Source
    ...    ${namespace}
    ...    ${TEST_UNCLAIMED_ADAPTER_URI}
    ...    example-org/e2e-adopted-adapter-${suffix}
    ...    ${compatible_with}
    ...    description=${ADAPTER_DESCRIPTION}
    ...    expected_status=201
    VAR    ${body}    ${response.json()}
    VAR    ${adapter}    ${body}[artifact][metadata][name]
    Track Adapter Artifact For Cleanup    ${namespace}    ${adapter}
    VAR    ${TEST_ADAPTER_NAME}    ${adapter}    scope=TEST
    VAR    ${TEST_ADAPTER_REGISTRATION_RESULT}    ${body}    scope=TEST

Registering an adapter that declares the file path should be refused
    [Documentation]    Registers an adapter for upload declaring the given path beside the weight
    ...    files every adapter needs, and asserts the project turned the registration down over that
    ...    path.
    ...
    ...    The refusal has to say that the declared paths are what it objects to, and quote the
    ...    offending one back: a registration is turned down the same way when the weight files
    ...    themselves are missing, so a check that only saw "refused" would be satisfied by the wrong
    ...    refusal. The quoting follows Python's own rendering of the value, which is why a backslash
    ...    in the path comes back doubled.
    [Arguments]    ${file_path}
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${compatible_with}=    Create List    ${ADAPTER_BASE_MODEL_ID}
    ${files}=    Create List    adapter_config.json    adapter_model.safetensors    ${file_path}
    ${response}=    Create Artifact With Upload
    ...    ${namespace}
    ...    example-org/e2e-refused-adapter-${suffix}
    ...    ${compatible_with}
    ...    ${files}
    ...    expected_status=422
    VAR    ${reason}    ${response.json()}[detail][0][msg]
    Should Contain    ${reason}    file paths must be relative
    ${quoted}=    Evaluate    repr($file_path)
    Should Contain    ${reason}    ${quoted}

The project adapter artifact list is retrieved with page size ${page_size}
    ${namespace}=    Get Project Namespace
    ${response}=    List Artifacts    ${namespace}    expected_status=200    page_size=${page_size}
    VAR    ${TEST_ADAPTER_LIST}    ${response.json()}    scope=TEST

The adapter artifact list should be empty
    ${data}=    Get From Dictionary    ${TEST_ADAPTER_LIST}    data
    Should Be Empty    ${data}

The adapter artifact list should contain the fine-tuning adapter
    ${names}=    Adapter Names In List
    Should Contain    ${names}    ${TEST_ADAPTER_NAME}

The adapter artifact list should not contain the fine-tuning adapter
    ${names}=    Adapter Names In List
    Should Not Contain    ${names}    ${TEST_ADAPTER_NAME}

The adapter artifact list should not contain the externally created adapter
    ${names}=    Adapter Names In List
    Should Not Contain    ${names}    ${TEST_FOREIGN_ADAPTER_NAME}

The returned adapter page should hold a single artifact
    ${data}=    Get From Dictionary    ${TEST_ADAPTER_LIST}    data
    Length Should Be    ${data}    1

The reported adapter total should count every artifact in the project
    [Documentation]    An exact count -- a total that drifts from what the project holds means the
    ...    listing is reaching artifacts it should not, or missing ones it should.
    ${pagination}=    Get From Dictionary    ${TEST_ADAPTER_LIST}    pagination
    Should Be Equal As Integers    ${pagination}[total]    ${TEST_ADAPTER_COUNT}

Every listed adapter should report its weights as not ready
    [Documentation]    The adapter is registered without its weight files being uploaded, so the
    ...    reported status must be a definite not-ready rather than an unknown.
    ${data}=    Get From Dictionary    ${TEST_ADAPTER_LIST}    data
    Should Not Be Empty    ${data}
    FOR    ${artifact}    IN    @{data}
        Should Be Equal    ${artifact}[storage][readiness]    NotReady
    END

The adapter artifact list should not contain the unclaimed adapter weights
    ${locations}=    Adapter Storage Locations In List
    Should Not Contain    ${locations}    ${TEST_UNCLAIMED_ADAPTER_URI}

The adapter artifact list should contain the uploaded adapter
    ${locations}=    Adapter Storage Locations In List
    Should Contain    ${locations}    ${TEST_ADAPTER_STORAGE_URI}

The registered adapter weights should now appear in the project list
    [Documentation]    Registering weights the project already held is what puts them in the list:
    ...    before it there was no record to name them by, and after it there is.
    ${adapter}=    The Listed Adapter Stored At    ${TEST_UNCLAIMED_ADAPTER_URI}
    Should Be Equal    ${adapter}[artifact][metadata][name]    ${TEST_ADAPTER_NAME}

The registration result should describe the adapter the same way the project list does
    [Documentation]    A client renders the adapter it just registered straight into the collection
    ...    it is already showing, so the two descriptions have to agree rather than merely overlap.
    ${listed}=    The Listed Adapter Stored At    ${TEST_UNCLAIMED_ADAPTER_URI}
    VAR    ${created}    ${TEST_ADAPTER_REGISTRATION_RESULT}
    Should Be Equal    ${created}[artifact][metadata][name]    ${listed}[artifact][metadata][name]
    Should Be Equal    ${created}[storage][uri]    ${listed}[storage][uri]
    Should Be Equal    ${created}[storage][readiness]    ${listed}[storage][readiness]
    Should Be Equal    ${created}[artifact][spec][compatibleWith]    ${listed}[artifact][spec][compatibleWith]

The adapter artifact detail is retrieved by name
    ${namespace}=    Get Project Namespace
    ${response}=    Get Artifact    ${namespace}    ${TEST_ADAPTER_NAME}
    VAR    ${TEST_ADAPTER_DETAIL_RESPONSE}    ${response}    scope=TEST

The adapter artifact detail is requested for name "${name}"
    ${namespace}=    Get Project Namespace
    ${response}=    Get Artifact    ${namespace}    ${name}
    VAR    ${TEST_ADAPTER_DETAIL_RESPONSE}    ${response}    scope=TEST

The externally created adapter artifact detail is requested
    ${namespace}=    Get Project Namespace
    ${response}=    Get Artifact    ${namespace}    ${TEST_FOREIGN_ADAPTER_NAME}
    VAR    ${TEST_ADAPTER_DETAIL_RESPONSE}    ${response}    scope=TEST

The adapter artifact detail response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_ADAPTER_DETAIL_RESPONSE.status_code}    ${expected_status}

The adapter should be found
    The adapter artifact detail response status should be "200"

The adapter should be reported as not found
    The adapter artifact detail response status should be "404"

The adapter artifact detail should describe the requested adapter
    [Documentation]    A definite readiness value -- not just the field's presence -- proves the
    ...    computation ran for the single-artifact endpoint too, not only for the list.
    VAR    ${artifact}    ${TEST_ADAPTER_DETAIL_RESPONSE.json()}
    Should Be Equal    ${artifact}[artifact][metadata][name]    ${TEST_ADAPTER_NAME}
    Should Be Equal    ${artifact}[storage][readiness]    NotReady

The adapter should report the base model it fits
    [Documentation]    The declaration is read back off the adapter rather than kept beside it, so a
    ...    client learns what the adapter attaches to from the adapter itself.
    VAR    ${artifact}    ${TEST_ADAPTER_DETAIL_RESPONSE.json()}
    Should Contain    ${artifact}[artifact][spec][compatibleWith]    ${ADAPTER_BASE_MODEL_ID}

The adapter should report the rank it was registered with
    [Documentation]    Details already stored beside the weights outrank the registration wherever
    ...    they speak, but where they are silent the user's own declaration is all there is -- so it
    ...    has to survive rather than be dropped on the way in.
    VAR    ${artifact}    ${TEST_ADAPTER_DETAIL_RESPONSE.json()}
    Should Be Equal As Integers    ${artifact}[artifact][spec][rank]    ${ADAPTER_RANK}

The adapter should carry the description it was registered with
    [Documentation]    The description is the user's own words about what the adapter is for, so it
    ...    has to come back as written rather than being reduced to a name.
    VAR    ${artifact}    ${TEST_ADAPTER_DETAIL_RESPONSE.json()}
    VAR    ${annotations}    ${artifact}[artifact][metadata][annotations]
    Should Be Equal    ${annotations}[aiwb.apps.eai.amd.com/description]    ${ADAPTER_DESCRIPTION}

The fine-tuning adapter should carry its description
    [Documentation]    A description supplied for a fine-tuning run belongs to the adapter it
    ...    produces and is returned when that adapter is inspected later.
    VAR    ${artifact}    ${TEST_ADAPTER_DETAIL_RESPONSE.json()}
    VAR    ${annotations}    ${artifact}[artifact][metadata][annotations]
    Should Be Equal    ${annotations}[aiwb.apps.eai.amd.com/description]    ${ADAPTER_DESCRIPTION}

The fine-tuning adapter should report its creator
    [Documentation]    The submitter annotation a fine-tuning run stamps on the adapter it
    ...    produces survives being read back, so the project can still show who created it
    ...    when the adapter is inspected.
    VAR    ${artifact}    ${TEST_ADAPTER_DETAIL_RESPONSE.json()}
    VAR    ${annotations}    ${artifact}[artifact][metadata][annotations]
    Should Be Equal    ${annotations}[airm.silogen.ai/submitter]    ${ADAPTER_SUBMITTER}

The adapter should be ready even though the project holds no such base model
    [Documentation]    The declared base model is one the project never held, so a ready adapter is
    ...    the proof that compatibility is a declaration rather than a link something has to resolve.
    VAR    ${artifact}    ${TEST_ADAPTER_DETAIL_RESPONSE.json()}
    Should Be Equal    ${artifact}[storage][readiness]    Ready

An adapter registered for upload whose weights never arrived
    [Documentation]    Registers an adapter through the upload flow and never sends the weights,
    ...    which is what a user who walked away mid-upload leaves behind: the project owns a named
    ...    adapter with nothing servable behind it.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${compatible_with}=    Create List    ${ADAPTER_BASE_MODEL_ID}
    ${response}=    Create Artifact For Upload
    ...    ${namespace}
    ...    example-org/e2e-pending-adapter-${suffix}
    ...    ${compatible_with}
    ...    expected_status=201
    VAR    ${body}    ${response.json()}
    Track Adapter Artifact For Cleanup    ${namespace}    ${body}[artifact][metadata][name]
    Track Adapter Weights For Cleanup    ${namespace}    ${body}[storage][uri]
    VAR    ${TEST_ADAPTER_NAME}    ${body}[artifact][metadata][name]    scope=TEST

An adapter whose recorded weights lie outside the project
    [Documentation]    Records a storage location in another project's tree -- the shape a tampered
    ...    or mis-reconciled adapter takes. Every project shares one bucket, so this is the only
    ...    thing standing between a bad record and working links into another tenant's files.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-elsewhere-adapter-${suffix}
    ${uri}=    Apply AIMArtifact CR Recording Storage Outside The Project    ${name}    ${namespace}
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_ADAPTER_NAME}    ${name}    scope=TEST
    VAR    ${TEST_ADAPTER_FOREIGN_URI}    ${uri}    scope=TEST

The adapter is downloaded
    ${namespace}=    Get Project Namespace
    ${response}=    Download Artifact    ${namespace}    ${TEST_ADAPTER_NAME}    expected_status=200
    VAR    ${TEST_ADAPTER_DOWNLOAD_RESPONSE}    ${response}    scope=TEST
    VAR    ${TEST_ADAPTER_DOWNLOAD}    ${response.json()}    scope=TEST

The user attempts to download the adapter
    ${namespace}=    Get Project Namespace
    ${response}=    Download Artifact    ${namespace}    ${TEST_ADAPTER_NAME}
    VAR    ${TEST_ADAPTER_DOWNLOAD_RESPONSE}    ${response}    scope=TEST

A download is requested for the adapter named "${name}"
    ${namespace}=    Get Project Namespace
    ${response}=    Download Artifact    ${namespace}    ${name}
    VAR    ${TEST_ADAPTER_DOWNLOAD_RESPONSE}    ${response}    scope=TEST

A download of the adapter is requested from the second project
    ${namespace}=    Get Project Namespace
    ${response}=    Download Artifact    ${namespace}    ${TEST_ADAPTER_NAME}
    VAR    ${TEST_ADAPTER_DOWNLOAD_RESPONSE}    ${response}    scope=TEST

A download of the externally created adapter is requested
    ${namespace}=    Get Project Namespace
    ${response}=    Download Artifact    ${namespace}    ${TEST_FOREIGN_ADAPTER_NAME}
    VAR    ${TEST_ADAPTER_DOWNLOAD_RESPONSE}    ${response}    scope=TEST

The user carries the downloaded files back in as a new adapter
    [Documentation]    The files are fetched from where the download points and put back through the
    ...    ordinary upload, so the new adapter is built out of what travelled rather than out of what
    ...    the test remembered. A download hands over files and nothing else, so what the new adapter
    ...    is has to be declared on the way in; it is read off the project's own record of the
    ...    original. The storage is freshly allocated, so the two adapters share no files.
    ${namespace}=    Get Project Namespace
    ${original}=    Get Artifact    ${namespace}    ${TEST_ADAPTER_NAME}    expected_status=200
    VAR    ${spec}    ${original.json()}[artifact][spec]
    ${fetched}=    Fetch Downloaded Adapter Files    ${TEST_ADAPTER_DOWNLOAD}[files]
    ${paths}=    Downloaded Adapter File Paths
    ${response}=    Create Artifact With Upload
    ...    ${namespace}
    ...    ${spec}[modelId]
    ...    ${spec}[compatibleWith]
    ...    ${paths}
    ...    expected_status=201
    VAR    ${body}    ${response.json()}
    Track Adapter Artifact For Cleanup    ${namespace}    ${body}[artifact][metadata][name]
    Track Adapter Weights For Cleanup    ${namespace}    ${body}[storage][uri]
    ${sent}=    Upload Fetched Adapter Files To Provided Locations    ${body}[uploads]    ${fetched}
    VAR    ${TEST_REONBOARDED_ADAPTER_NAME}    ${body}[artifact][metadata][name]    scope=TEST
    VAR    ${TEST_REONBOARDED_STORAGE_URI}    ${body}[storage][uri]    scope=TEST
    VAR    ${TEST_REONBOARDED_FILES}    ${sent}    scope=TEST

The download should list every file the adapter is made of
    [Documentation]    Compared against everything the adapter's storage actually holds, path for
    ...    path -- a download naming only some of the files, or naming them in a layout of its own,
    ...    would look complete on its own, and the receiver would find out it was not only once the
    ...    adapter failed to load.
    ${namespace}=    Get Project Namespace
    ${stored}=    Objects Stored At Adapter Location    ${namespace}    ${TEST_ADAPTER_STORAGE_URI}
    ${offered}=    Downloaded Adapter File Paths
    Downloaded Files Should Match What Storage Holds
    ...    ${offered}    ${stored}    ${TEST_ADAPTER_STORAGE_URI}

The download should keep the nested file under its subdirectory
    [Documentation]    The path comes back as it was registered, subdirectory and all: reduced to a
    ...    bare filename it would land beside the weights instead of beneath them, and what the
    ...    receiver rebuilds would not be the adapter that was sent.
    ${offered}=    Downloaded Adapter File Paths
    Should Contain    ${offered}    ${ADAPTER_NESTED_FILE}

Every offered file should come with a link, and its size where storage reports one
    [Documentation]    The link is what makes a file fetchable, so no entry may lack it. The size
    ...    lets a receiver tell whether what arrived is all of it, and is stated as unknown where
    ...    storage reports none rather than passed off as an empty file.
    Every Downloaded File Should Have A Link And A Size    ${TEST_ADAPTER_DOWNLOAD}[files]

The adapter's files should be retrievable from where the download points
    [Documentation]    Fetched from outside the platform, using nothing but the links as issued, and
    ...    each one has to hand back exactly as many bytes as the download said it would. Weighed
    ...    against the stored objects as well, because the sizes the download states are its own
    ...    account of itself: bytes that agree with that account and not with what is stored would
    ...    pass every check made on the response alone.
    ${namespace}=    Get Project Namespace
    VAR    ${files}    ${TEST_ADAPTER_DOWNLOAD}[files]
    ${fetched}=    Fetch Downloaded Adapter Files    ${files}
    Fetched Adapter Files Should Be Whole    ${files}    ${fetched}
    Adapter Location Should Hold Exactly    ${namespace}    ${TEST_ADAPTER_STORAGE_URI}    ${fetched}

The new adapter should hold the files the download handed over
    [Documentation]    Compared byte for byte, each at its own path below a location of the new
    ...    adapter's own. The two adapters sharing a prefix would make the round trip a rename: what
    ...    proves the files travelled is that a second copy of them now exists somewhere the first
    ...    one does not point.
    ${namespace}=    Get Project Namespace
    Should Not Be Equal    ${TEST_REONBOARDED_STORAGE_URI}    ${TEST_ADAPTER_STORAGE_URI}
    ...    The new adapter reuses the original's storage, so nothing was actually carried across
    Adapter Location Should Hold Exactly
    ...    ${namespace}    ${TEST_REONBOARDED_STORAGE_URI}    ${TEST_REONBOARDED_FILES}

The new adapter should keep the nested file under its subdirectory
    [Documentation]    The file that sat below the weights is put back below them, so what the round
    ...    trip rebuilt is the adapter that was sent rather than a flattened version of it.
    Dictionary Should Contain Key    ${TEST_REONBOARDED_FILES}    ${ADAPTER_NESTED_FILE}

The new adapter should be ready to serve
    [Documentation]    Readiness is judged on the files that arrived, so an adapter reported ready
    ...    is the platform's own verdict that what came back is a complete adapter.
    ${namespace}=    Get Project Namespace
    ${response}=    Get Artifact    ${namespace}    ${TEST_REONBOARDED_ADAPTER_NAME}    expected_status=200
    Should Be Equal    ${response.json()}[storage][readiness]    Ready

The download should be refused as reaching outside the project
    [Documentation]    The refusal names the location the adapter records, so an operator can see
    ...    which record is wrong rather than being told only that the download will not happen, and
    ...    says that the location is the problem. Naming the location alone would not distinguish
    ...    this from the refusal an unwritten adapter gets, which quotes the same location back.
    Should Be Equal As Integers    ${TEST_ADAPTER_DOWNLOAD_RESPONSE.status_code}    409
    VAR    ${body}    ${TEST_ADAPTER_DOWNLOAD_RESPONSE.json()}
    Should Contain    ${body}[detail]    ${TEST_ADAPTER_FOREIGN_URI}
    Should Contain    ${body}[detail]    is not inside this project's storage

The download should be refused as incomplete
    [Documentation]    Handing out links to a half-written adapter would produce something that
    ...    cannot be loaded, so the refusal names the files a complete adapter has to hold.
    Should Be Equal As Integers    ${TEST_ADAPTER_DOWNLOAD_RESPONSE.status_code}    409
    VAR    ${body}    ${TEST_ADAPTER_DOWNLOAD_RESPONSE.json()}
    Should Contain    ${body}[detail]    adapter_config.json
    Should Contain    ${body}[detail]    adapter_model.safetensors

The adapter download should report it as not found
    [Documentation]    The refusal comes from the platform having no such adapter in this project,
    ...    which is what a bare 404 alone would not tell apart from the download not being offered.
    Should Be Equal As Integers    ${TEST_ADAPTER_DOWNLOAD_RESPONSE.status_code}    404
    VAR    ${body}    ${TEST_ADAPTER_DOWNLOAD_RESPONSE.json()}
    Should Contain    ${body}[detail]    not found in namespace

Downloaded Adapter File Paths
    [Documentation]    Extracts the file paths from the last download, relative to where the adapter
    ...    is stored.
    ${paths}=    Create List
    FOR    ${file}    IN    @{TEST_ADAPTER_DOWNLOAD}[files]
        Append To List    ${paths}    ${file}[path]
    END
    RETURN    ${paths}

A second ready project exists for namespace isolation
    [Documentation]    Switches the test to a freshly created project, so the adapter left behind
    ...    in the first one can be asked for from across a project boundary. The project must be a
    ...    fresh one: the shared project every other test runs in is the one holding the adapter, so
    ...    asking for it there crosses no boundary at all and the scenario would pass on nothing.
    A Fresh Project With User Access Exists

The adapter artifact detail is requested from the second project by name
    ${namespace}=    Get Project Namespace
    ${response}=    Get Artifact    ${namespace}    ${TEST_ADAPTER_NAME}
    VAR    ${TEST_ADAPTER_DETAIL_RESPONSE}    ${response}    scope=TEST

The adapter artifact is deleted
    ${namespace}=    Get Project Namespace
    ${response}=    Delete Artifact    ${namespace}    ${TEST_ADAPTER_NAME}
    VAR    ${TEST_ADAPTER_DELETE_RESPONSE}    ${response}    scope=TEST

The adapter artifact "${name}" is deleted
    ${namespace}=    Get Project Namespace
    ${response}=    Delete Artifact    ${namespace}    ${name}
    VAR    ${TEST_ADAPTER_DELETE_RESPONSE}    ${response}    scope=TEST

The externally created adapter artifact is deleted
    ${namespace}=    Get Project Namespace
    ${response}=    Delete Artifact    ${namespace}    ${TEST_FOREIGN_ADAPTER_NAME}
    VAR    ${TEST_ADAPTER_DELETE_RESPONSE}    ${response}    scope=TEST

The adapter artifact delete response status should be "${expected_status}"
    Should Be Equal As Integers    ${TEST_ADAPTER_DELETE_RESPONSE.status_code}    ${expected_status}

The delete should be accepted
    [Documentation]    A delete that actually removes something is taken on, not finished
    ...    synchronously -- the caller learns the outcome from the resource's own disappearance.
    The adapter artifact delete response status should be "202"

The delete should report nothing to remove
    [Documentation]    Deleting something that was never there to begin with, or that the platform
    ...    refuses to touch, completes at once with nothing left to reconcile.
    The adapter artifact delete response status should be "204"

The adapter artifact should no longer appear in the project list
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    60 sec    5 sec
    ...    AIMArtifact CR Should Be Absent    ${TEST_ADAPTER_NAME}    ${namespace}
    The project adapter artifact list is retrieved
    ${names}=    Adapter Names In List
    Should Not Contain    ${names}    ${TEST_ADAPTER_NAME}

The externally created adapter artifact should still exist in the project
    ${namespace}=    Get Project Namespace
    AIMArtifact CR Should Exist    ${TEST_FOREIGN_ADAPTER_NAME}    ${namespace}

An AIM deployment attaching the adapter artifact exists in the project
    ${namespace}=    Get Project Namespace
    VAR    ${name}    e2e-blocking-${TEST_ADAPTER_NAME}    scope=TEST
    Apply AIMService Referencing Artifact    ${name}    ${TEST_ADAPTER_NAME}    ${namespace}
    VAR    ${TEST_BLOCKING_SERVICE_NAME}    ${name}    scope=TEST

Remove blocking AIM deployment for adapter if present
    [Documentation]    Teardown for the delete-guard scenario -- without it the artifact stays
    ...    pinned by the 409 guard and suite cleanup cannot remove it.
    ${service}=    Get Variable Value    ${TEST_BLOCKING_SERVICE_NAME}    ${None}
    IF    $service is not None
        ${namespace}=    Get Project Namespace
        Delete AIMService CR    ${service}    ${namespace}
    END

The user attempts to delete the adapter artifact
    ${namespace}=    Get Project Namespace
    ${response}=    Delete Artifact    ${namespace}    ${TEST_ADAPTER_NAME}
    VAR    ${TEST_ADAPTER_DELETE_RESPONSE}    ${response}    scope=TEST

The delete refusal should name the blocking AIM deployment
    Should Be Equal As Integers    ${TEST_ADAPTER_DELETE_RESPONSE.status_code}    409
    VAR    ${body}    ${TEST_ADAPTER_DELETE_RESPONSE.json()}
    Should Contain    ${body}[detail]    ${TEST_BLOCKING_SERVICE_NAME}

The delete refusal should say how to override it
    [Documentation]    A refusal that does not tell the caller about force leaves them stuck.
    Should Be Equal As Integers    ${TEST_ADAPTER_DELETE_RESPONSE.status_code}    409
    VAR    ${body}    ${TEST_ADAPTER_DELETE_RESPONSE.json()}
    Should Contain    ${body}[detail]    force=true

The user force-deletes the adapter artifact
    ${namespace}=    Get Project Namespace
    ${response}=    Delete Artifact    ${namespace}    ${TEST_ADAPTER_NAME}    force=${True}
    VAR    ${TEST_ADAPTER_DELETE_RESPONSE}    ${response}    scope=TEST

The blocking AIM deployment should still exist
    [Documentation]    A force delete removes the adapter only -- the deployment that referenced it
    ...    is left in place rather than torn down with it. Only its continued existence is checked:
    ...    the fixture is a bare AIMService with nothing deployable behind it, so it never reaches
    ...    Running and asserting on serving state here would assert on the fixture, not the delete.
    ${namespace}=    Get Project Namespace
    AIMService CR Should Exist    ${TEST_BLOCKING_SERVICE_NAME}    ${namespace}

The adapter artifact should still exist in the project
    ${namespace}=    Get Project Namespace
    Get Artifact    ${namespace}    ${TEST_ADAPTER_NAME}    expected_status=200

The uploaded adapter is deleted
    [Documentation]    Names which of the two adapters is going, so a scenario holding both stays
    ...    readable. The other one is the claimant that has to keep working.
    The adapter artifact is deleted

The uploaded adapter should no longer appear in the project list
    The adapter artifact should no longer appear in the project list

Its weights should no longer occupy project storage
    [Documentation]    Reclaiming happens within the delete, so once it is accepted the location the
    ...    workbench allocated holds nothing at all -- not a stale marker, not the recovery copy of
    ...    the adapter's identity that was written beside the weights.
    ${namespace}=    Get Project Namespace
    ${stored}=    Objects Stored At Adapter Location    ${namespace}    ${TEST_ADAPTER_STORAGE_URI}
    Should Be Empty    ${stored}    Weights were left behind at ${TEST_ADAPTER_STORAGE_URI}: ${stored}

Nothing the training run stored should remain
    [Documentation]    Reclaiming happens within the delete and covers the whole run folder, so once
    ...    the delete is accepted neither the adapter weights nor the run-level files beside them are
    ...    left behind.
    ${namespace}=    Get Project Namespace
    ${stored}=    Objects Stored At Adapter Location    ${namespace}    ${TEST_RUN_STORAGE_URI}
    Should Be Empty    ${stored}    The training run's output was left behind at ${TEST_RUN_STORAGE_URI}: ${stored}

The other training run's output should remain untouched
    [Documentation]    Compared against exactly what the other run held before the delete, so a
    ...    reclaim that reached past its own run folder is caught even if it only took some files.
    ${namespace}=    Get Project Namespace
    ${stored}=    Objects Stored At Adapter Location    ${namespace}    ${TEST_OTHER_RUN_STORAGE_URI}
    Lists Should Be Equal    ${stored}    ${TEST_OTHER_RUN_STORAGE_CONTENTS}

The user's files should remain untouched
    [Documentation]    Compared against exactly what the location held before the delete. "Still has
    ...    files" would pass even if the delete had taken some of them.
    ${namespace}=    Get Project Namespace
    ${stored}=    Objects Stored At Adapter Location    ${namespace}    ${TEST_ADAPTER_STORAGE_URI}
    Lists Should Be Equal    ${stored}    ${TEST_ADAPTER_STORAGE_CONTENTS}

The stored weights should remain available to the second adapter
    [Documentation]    The surviving adapter still resolves and still reports its weights servable,
    ...    which it can only do while every file it needs is still where it points.
    ${namespace}=    Get Project Namespace
    ${response}=    Get Artifact    ${namespace}    ${TEST_SECOND_ADAPTER_NAME}    expected_status=200
    VAR    ${artifact}    ${response.json()}
    Should Be Equal    ${artifact}[storage][uri]    ${TEST_ADAPTER_STORAGE_URI}
    Should Be Equal    ${artifact}[storage][readiness]    Ready

Adapter Names In List
    [Documentation]    Extracts the artifact names from the last retrieved list response.
    ${data}=    Get From Dictionary    ${TEST_ADAPTER_LIST}    data
    ${names}=    Create List
    FOR    ${artifact}    IN    @{data}
        Append To List    ${names}    ${artifact}[artifact][metadata][name]
    END
    RETURN    ${names}

Adapter Storage Locations In List
    [Documentation]    Extracts the storage locations from the last retrieved list response, so a
    ...    scenario can look for weights it put somewhere it knows.
    ${data}=    Get From Dictionary    ${TEST_ADAPTER_LIST}    data
    ${locations}=    Create List
    FOR    ${artifact}    IN    @{data}
        Append To List    ${locations}    ${artifact}[storage][uri]
    END
    RETURN    ${locations}

Track Adapter Artifact For Cleanup
    [Documentation]    Records an artifact so suite teardown removes it.
    [Arguments]    ${namespace}    ${name}
    ${tracked}=    Get Variable Value    ${CREATED_ADAPTER_ARTIFACTS}    ${None}
    IF    $tracked is None
        ${tracked}=    Create List
        VAR    ${CREATED_ADAPTER_ARTIFACTS}    ${tracked}    scope=SUITE
    END
    Append To List    ${CREATED_ADAPTER_ARTIFACTS}    ${namespace}:::${name}

Clean Up All Created Adapter Artifacts
    [Documentation]    Deletes every tracked artifact and confirms each CR is gone before
    ...    project teardown removes the namespace out from under them.
    ${tracked}=    Get Variable Value    ${CREATED_ADAPTER_ARTIFACTS}    ${None}
    IF    $tracked is None
        RETURN
    END
    FOR    ${entry}    IN    @{tracked}
        ${namespace}    ${name}=    Split String    ${entry}    :::
        TRY
            Delete Artifact    ${namespace}    ${name}
        EXCEPT    AS    ${error}
            Log    Failed to delete artifact ${name} in ${namespace}: ${error}    level=WARN
        END
    END
    FOR    ${entry}    IN    @{tracked}
        ${namespace}    ${name}=    Split String    ${entry}    :::
        TRY
            Wait Until Keyword Succeeds    60 sec    5 sec
            ...    AIMArtifact CR Should Be Absent    ${name}    ${namespace}
        EXCEPT    AS    ${error}
            Log    Artifact ${name} in ${namespace} still present after delete: ${error}    level=WARN
        END
    END
    VAR    ${CREATED_ADAPTER_ARTIFACTS}    ${None}    scope=SUITE

The Listed Adapter Stored At
    [Documentation]    Resolves an adapter from the last retrieved list by where its weights sit.
    ...    Keyed on the storage location rather than the name, because a scenario that put weights
    ...    somewhere knows the location while the platform mints the name.
    [Arguments]    ${uri}
    ${data}=    Get From Dictionary    ${TEST_ADAPTER_LIST}    data
    FOR    ${artifact}    IN    @{data}
        IF    $artifact['storage']['uri'] == $uri
            RETURN    ${artifact}
        END
    END
    Fail    No adapter stored at ${uri} appears in the retrieved list

Track Adapter Weights For Cleanup
    [Documentation]    Records a storage location the suite caused to be written so teardown removes
    ...    it. Tracked by location rather than by adapter name because the platform mints the name
    ...    for weights it allocates storage for -- the location it reports back is the only handle
    ...    the suite is given.
    [Arguments]    ${namespace}    ${uri}
    ${tracked}=    Get Variable Value    ${CREATED_ADAPTER_WEIGHTS}    ${None}
    IF    $tracked is None
        ${tracked}=    Create List
        VAR    ${CREATED_ADAPTER_WEIGHTS}    ${tracked}    scope=SUITE
    END
    Append To List    ${CREATED_ADAPTER_WEIGHTS}    ${namespace}:::${uri}

Clean Up All Created Adapter Weights
    [Documentation]    Removes every tracked storage location. A location the product reclaimed
    ...    during its own delete is already empty, so removing it again is a no-op rather than a
    ...    teardown failure -- what still needs removing are the locations deletion deliberately
    ...    leaves alone.
    ${tracked}=    Get Variable Value    ${CREATED_ADAPTER_WEIGHTS}    ${None}
    IF    $tracked is None
        RETURN
    END
    FOR    ${entry}    IN    @{tracked}
        ${namespace}    ${uri}=    Split String    ${entry}    :::
        TRY
            Remove Adapter Weights At Storage Location    ${namespace}    ${uri}
        EXCEPT    AS    ${error}
            Log    Failed to remove adapter weights at ${uri} in ${namespace}: ${error}    level=WARN
        END
    END
    VAR    ${CREATED_ADAPTER_WEIGHTS}    ${None}    scope=SUITE
