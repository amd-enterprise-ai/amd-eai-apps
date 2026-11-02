# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Business-logic keywords for the quota provisioning-race regression.
...                 Uses an isolated simulated cluster to control status-message ordering
...                 without mutating shared cluster reconciliation.
Resource            airm_projects.resource
Resource            resources/deployment.resource
Library             ../libraries/QuotaSnapshot.py


*** Variables ***
# Raised from the minimum 1000 milliCPU quota request, and well inside the simulated node's 4000.
${RAISED_CPU_MILLI_CORES}       2000


*** Keywords ***
An isolated cluster is ready for a new project
    [Documentation]    Creates a test-owned simulated cluster and publishes its capacity.
    ...                Sets: TEST_CLUSTER_ID, TEST_CLUSTER_NAME, TEST_CLUSTER_SECRET
    ${prefix}=    Test Prefix
    # The name must be unique per run, not just per user: cluster names carry a case-insensitive
    # unique index and the first heartbeat renames the cluster to this value, so a leftover
    # cluster of the same name would make that rename fail inside the shared message consumer.
    ${unique_suffix}=    Generate Random String    8    [LOWER]
    VAR    ${cluster_name}    ${prefix}quota-race-${unique_suffix}
    # The create payload carries no name: clusters are named by their first heartbeat.
    ${cluster_data}=    Create Dictionary
    ${response}=    Create cluster    ${cluster_data}    expected_status=200
    ${cluster_id}=    Get From Dictionary    ${response.json()}    id
    ${cluster_secret}=    Get From Dictionary    ${response.json()}    userSecret
    VAR    ${TEST_CLUSTER_ID}    ${cluster_id}    scope=TEST
    VAR    ${TEST_CLUSTER_NAME}    ${cluster_name}    scope=TEST
    VAR    ${TEST_CLUSTER_SECRET}    ${cluster_secret}    scope=TEST
    VAR    ${TEST_RABBITMQ_HOST}    ${None}    scope=TEST
    VAR    ${TEST_RABBITMQ_PORT}    ${None}    scope=TEST

    ${rabbitmq_host}    ${rabbitmq_port}=    RabbitMQ connection for quota race test
    VAR    ${TEST_RABBITMQ_HOST}    ${rabbitmq_host}    scope=TEST
    VAR    ${TEST_RABBITMQ_PORT}    ${rabbitmq_port}    scope=TEST
    ${marker}=    Make Simulated Cluster Ready
    ...    ${cluster_id}    ${cluster_secret}    ${cluster_name}
    ...    ${rabbitmq_host}    ${rabbitmq_port}
    VAR    ${QUOTA_SNAPSHOT_MARKER}    ${marker}    scope=TEST
    Wait Until Keyword Succeeds    1 min    1 sec    Verify quota snapshot marker was processed
    Wait Until Keyword Succeeds    1 min    1 sec    Verify simulated cluster is healthy

RabbitMQ connection for quota race test
    [Documentation]    Resolves RabbitMQ for both in-cluster and local test execution.
    ...                The AMQP listener is named explicitly because the broker is TLS-enabled:
    ...                its Service also carries amqps, management, management-tls and
    ...                prometheus-tls, and the operator writes those ports in an order that
    ...                carries no meaning. This test speaks plaintext AMQP, as the real agent
    ...                does, so it needs the port the agent connects to rather than whichever
    ...                one happens to be listed first.
    ${in_cluster}=    Is Running In Cluster
    IF    ${in_cluster}
        ${rabbitmq_host}=    Internal Host For    airm    airm-infra-rabbitmq-rabbitmq    port_name=amqp
    ELSE
        ${rabbitmq_host}=    External Host For    airm    airm-infra-rabbitmq-rabbitmq    port_name=amqp
    END
    ${host}    ${port}=    Evaluate    $rabbitmq_host.rsplit(':', 1)
    RETURN    ${host}    ${port}

A new project is still being provisioned
    [Documentation]    Creates a fresh project on the isolated cluster.
    ...                Sets: TEST_PROJECT_ID, TEST_PROJECT
    Minimum quota data is prepared
    Valid project data with quota is prepared
    Create project request is sent

The cluster reports an allocation snapshot without the new project
    [Documentation]    Publishes an intentionally early empty allocation snapshot and waits
    ...                until AIRM has consumed it.
    Quota should be older than the coming snapshot
    ${marker}=    Publish Quota Snapshot Without Project
    ...    ${TEST_CLUSTER_ID}    ${TEST_CLUSTER_SECRET}    ${TEST_CLUSTER_NAME}
    ...    ${TEST_RABBITMQ_HOST}    ${TEST_RABBITMQ_PORT}
    VAR    ${QUOTA_SNAPSHOT_MARKER}    ${marker}    scope=TEST
    Wait Until Keyword Succeeds    1 min    1 sec    Verify quota snapshot marker was processed

Quota should be older than the coming snapshot
    [Documentation]    Guards against clock skew between the test runner and the platform.
    ...                A snapshot stamped before the quota is discarded as out of order, which
    ...                would let this test pass even against unfixed code.
    ${response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    ${quota_updated_at}=    Get From Dictionary    ${response.json()}[quota]    updatedAt
    ${now}=    Current UTC Timestamp
    Timestamp Should Be At Or After    ${now}    ${quota_updated_at}

Verify quota snapshot marker was processed
    [Documentation]    Confirms AIRM consumed all messages through the marker heartbeat.
    ${response}=    Get cluster    ${TEST_CLUSTER_ID}    expected_status=200
    ${last_heartbeat}=    Get From Dictionary    ${response.json()}    lastHeartbeatAt
    Timestamp Should Be At Or After    ${last_heartbeat}    ${QUOTA_SNAPSHOT_MARKER}

Verify simulated cluster is healthy
    [Documentation]    Confirms the isolated cluster accepts project creation.
    ${response}=    Get cluster    ${TEST_CLUSTER_ID}    expected_status=200
    Should Be Equal    ${response.json()}[status]    healthy

The project remains in progress and finishes ready instead of failing
    [Documentation]    Confirms the early snapshot did not fail the project, then reports
    ...                its matching quota and namespace state to complete provisioning.
    Project status should be one of    Pending, Provisioning
    ${marker}=    Publish Project Ready
    ...    ${TEST_CLUSTER_ID}    ${TEST_CLUSTER_SECRET}    ${TEST_CLUSTER_NAME}
    ...    ${TEST_RABBITMQ_HOST}    ${TEST_RABBITMQ_PORT}
    ...    ${TEST_PROJECT_ID}    ${TEST_PROJECT}[name]
    ...    ${TEST_QUOTA_DATA}[cpuMilliCores]    ${TEST_QUOTA_DATA}[memoryBytes]
    ...    ${TEST_QUOTA_DATA}[ephemeralStorageBytes]    ${TEST_QUOTA_DATA}[gpuCount]
    VAR    ${QUOTA_SNAPSHOT_MARKER}    ${marker}    scope=TEST
    Wait Until Keyword Succeeds    1 min    1 sec    Verify quota snapshot marker was processed
    Project should transition to "ready"    timeout=1 min

A provisioned project with a confirmed quota exists
    [Documentation]    Creates a project on the isolated cluster and reports its matching
    ...                allocation, so the quota is confirmed before the update under test.
    ...                Sets: TEST_PROJECT_ID, TEST_PROJECT, TEST_QUOTA_DATA
    A new project is still being provisioned
    The cluster reports the allocation    ${TEST_QUOTA_DATA}
    The cluster reports the namespace as active
    Project should transition to "ready"    timeout=1 min

The project quota is raised
    [Documentation]    Raises the project's CPU allocation, which returns the quota to Pending
    ...                until the cluster confirms the new value.
    ...                Sets: TEST_RAISED_QUOTA_DATA
    ${raised_quota}=    Create Dictionary
    ...    cpuMilliCores=${RAISED_CPU_MILLI_CORES}
    ...    memoryBytes=${TEST_QUOTA_DATA}[memoryBytes]
    ...    ephemeralStorageBytes=${TEST_QUOTA_DATA}[ephemeralStorageBytes]
    ...    gpuCount=${TEST_QUOTA_DATA}[gpuCount]
    ${project_data}=    Create Dictionary    description=${TEST_PROJECT_DESC}    quota=${raised_quota}
    Update project    ${TEST_PROJECT_ID}    ${project_data}    expected_status=200
    VAR    ${TEST_RAISED_QUOTA_DATA}    ${raised_quota}    scope=TEST

The cluster reports the previous allocation
    [Documentation]    Publishes a snapshot that still carries the pre-update allocation, as a
    ...                cluster that has not applied the raise yet would.
    # Without this the snapshot can be stamped before the raise and discarded as out of order,
    # which passes the test without ever reaching the behaviour it covers.
    Quota should be older than the coming snapshot
    The cluster reports the allocation    ${TEST_QUOTA_DATA}

The cluster reports the raised allocation
    [Documentation]    Publishes the snapshot that confirms the raise.
    The cluster reports the allocation    ${TEST_RAISED_QUOTA_DATA}

The cluster reports the allocation
    [Documentation]    Publishes a quota snapshot carrying the given allocation and waits until
    ...                AIRM has consumed it.
    [Arguments]    ${quota_data}
    ${marker}=    Publish Quota Allocation
    ...    ${TEST_CLUSTER_ID}    ${TEST_CLUSTER_SECRET}    ${TEST_CLUSTER_NAME}
    ...    ${TEST_RABBITMQ_HOST}    ${TEST_RABBITMQ_PORT}
    ...    ${TEST_PROJECT}[name]
    ...    ${quota_data}[cpuMilliCores]    ${quota_data}[memoryBytes]
    ...    ${quota_data}[ephemeralStorageBytes]    ${quota_data}[gpuCount]
    VAR    ${QUOTA_SNAPSHOT_MARKER}    ${marker}    scope=TEST
    Wait Until Keyword Succeeds    1 min    1 sec    Verify quota snapshot marker was processed

The cluster reports the namespace as active
    [Documentation]    Reports the namespace as Active so the project can reach Ready.
    ${marker}=    Publish Project Ready
    ...    ${TEST_CLUSTER_ID}    ${TEST_CLUSTER_SECRET}    ${TEST_CLUSTER_NAME}
    ...    ${TEST_RABBITMQ_HOST}    ${TEST_RABBITMQ_PORT}
    ...    ${TEST_PROJECT_ID}    ${TEST_PROJECT}[name]
    ...    ${TEST_QUOTA_DATA}[cpuMilliCores]    ${TEST_QUOTA_DATA}[memoryBytes]
    ...    ${TEST_QUOTA_DATA}[ephemeralStorageBytes]    ${TEST_QUOTA_DATA}[gpuCount]
    VAR    ${QUOTA_SNAPSHOT_MARKER}    ${marker}    scope=TEST
    Wait Until Keyword Succeeds    1 min    1 sec    Verify quota snapshot marker was processed

The project remains in progress and finishes ready with the raised quota
    [Documentation]    Confirms the lagging snapshot neither failed the project nor discarded the
    ...                raise, then reports the raised allocation and verifies the project
    ...                completes carrying it.
    The project should be back in progress
    The raised quota should still be awaiting confirmation
    The cluster reports the raised allocation
    Project should transition to "ready"    timeout=1 min
    The confirmed quota should carry the raised allocation

The project should be back in progress
    [Documentation]    Raising the quota puts the project back in progress, and the lagging
    ...                snapshot must leave it there. Ready is excluded on purpose: a project that
    ...                is still Ready while its quota is Pending means the raise never reached the
    ...                project's own status, which is as much a regression as failing it.
    Project status should be one of    Pending, PartiallyReady

The raised quota should still be awaiting confirmation
    [Documentation]    The raise must survive the lagging snapshot untouched and stay Pending
    ...                until the cluster confirms it. Against unfixed code the quota is Failed
    ...                here, which is the regression this scenario exists to catch.
    ${response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    Should Be Equal    ${response.json()}[quota][status]    Pending
    Should Be Equal As Integers
    ...    ${response.json()}[quota][cpuMilliCores]    ${RAISED_CPU_MILLI_CORES}

The confirmed quota should carry the raised allocation
    [Documentation]    Once the cluster reports the raise, the quota is Ready at the new value.
    ${response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    Should Be Equal    ${response.json()}[quota][status]    Ready
    Should Be Equal As Integers
    ...    ${response.json()}[quota][cpuMilliCores]    ${RAISED_CPU_MILLI_CORES}

The cluster reports a quota failure without saying why
    [Documentation]    Publishes a quota failure carrying no reason. A failure message is not
    ...                subject to the provisioning grace, so it fails the fresh quota immediately.
    # Without this the failure can be stamped before the quota and discarded as out of order,
    # which passes the test without ever reaching the behaviour it covers.
    Quota should be older than the coming snapshot
    ${marker}=    Publish Quota Failure Without Reason
    ...    ${TEST_CLUSTER_ID}    ${TEST_CLUSTER_SECRET}    ${TEST_CLUSTER_NAME}
    ...    ${TEST_RABBITMQ_HOST}    ${TEST_RABBITMQ_PORT}
    VAR    ${QUOTA_SNAPSHOT_MARKER}    ${marker}    scope=TEST
    Wait Until Keyword Succeeds    1 min    1 sec    Verify quota snapshot marker was processed

The project explains the failure and stops explaining it once the quota recovers
    [Documentation]    A failure with no reason must still be explained to the user, and that
    ...                explanation must disappear once the cluster confirms the quota.
    The failed quota should carry a stand-in reason
    The cluster reports the namespace as active
    Project should transition to "ready"    timeout=1 min
    The recovered quota should carry no reason

The failed quota should carry a stand-in reason
    [Documentation]    The cluster gave no reason, so the platform supplies one rather than
    ...                reporting a failure the user cannot interpret.
    ${response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    Should Be Equal    ${response.json()}[quota][status]    Failed
    Should Not Be Empty    ${response.json()}[quota][statusReason]

The recovered quota should carry no reason
    [Documentation]    Against unfixed code the quota is Ready while still advertising the failure
    ...                it recovered from, which is the regression this check exists to catch.
    ${response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    Should Be Equal    ${response.json()}[quota][status]    Ready
    Should Be Equal    ${response.json()}[quota][statusReason]    ${None}

Clean up quota provisioning race test
    [Documentation]    Deletes the project through simulated component updates, then deletes the
    ...                isolated cluster. Cleanup tolerates partial failure so one broken test does
    ...                not cascade, but a cluster that survives is reported rather than hidden:
    ...                the backend refuses to delete a cluster that still has projects, and its
    ...                broker vhost is only released once the cluster itself goes.
    ${cluster_id}=    Get Variable Value    ${TEST_CLUSTER_ID}    ${None}
    TRY
        Delete the simulated project
    EXCEPT    AS    ${error}
        Log    Simulated project cleanup failed: ${error}    WARN
    FINALLY
        IF    $cluster_id is not None
            Delete the simulated cluster    ${cluster_id}
        END
    END

Delete the simulated cluster
    [Documentation]    Deletes the cluster and confirms it is actually gone, so a delete refused
    ...                because a project outlived it is surfaced instead of passing silently.
    [Arguments]    ${cluster_id}
    ${response}=    Delete cluster    ${cluster_id}    expected_status=any
    TRY
        Wait Until Keyword Succeeds    30 sec    2 sec
        ...    Resource Should Not Exist    Get cluster    ${cluster_id}
    EXCEPT
        Log    Leaked simulated cluster ${cluster_id}: delete returned ${response.status_code}
        ...    and the cluster still exists. Its broker vhost is leaked too.    WARN
    END

Delete the simulated project
    [Documentation]    Deletes the project and reports the component deletions the cluster
    ...                would normally send, so the cluster has no projects left to block its
    ...                own deletion.
    ${project_id}=    Get Variable Value    ${TEST_PROJECT_ID}    ${None}
    ${rabbitmq_host}=    Get Variable Value    ${TEST_RABBITMQ_HOST}    ${None}
    IF    $project_id is None or $rabbitmq_host is None    RETURN

    Delete project    ${project_id}    expected_status=any
    ${marker}=    Publish Project Deleted
    ...    ${TEST_CLUSTER_ID}    ${TEST_CLUSTER_SECRET}    ${TEST_CLUSTER_NAME}
    ...    ${rabbitmq_host}    ${TEST_RABBITMQ_PORT}    ${project_id}
    VAR    ${QUOTA_SNAPSHOT_MARKER}    ${marker}    scope=TEST
    Wait Until Keyword Succeeds    1 min    1 sec
    ...    Resource Should Not Exist    Get project    ${project_id}
