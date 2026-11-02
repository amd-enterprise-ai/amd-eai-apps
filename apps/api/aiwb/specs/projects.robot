# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for project listing and project-scoped workload
...                 dashboard stats and metrics. Verifies project listing,
...                 workload stats, workload metrics, and access control operations.
Resource            resources/airm_keywords.resource
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource
Resource            resources/aiwb_projects.resource
Resource            resources/aiwb_models.resource
Resource            resources/aiwb_datasets.resource
Resource            resources/aiwb_test_data.resource
Library             Collections
Suite Teardown      Clean Up All Tracked Resources


*** Test Cases ***
List accessible projects
    [Documentation]    Verify that accessible projects are returned for the user.
    [Tags]    projects    list    smoke
    Given a ready project with user access exists
    When AIWB list projects request is sent
    Then response status should be 200
    And response should contain project list
    And project list should include current project

Get project workload stats returns resource counts
    [Documentation]    Verify that project workload stats return resource counts grouped by status.
    [Tags]    projects    stats    smoke
    Given a ready project with user access exists
    When AIWB project workload stats request is sent
    Then response status should be 200
    And response should contain workload stats structure

Get project workload metrics returns paginated workload list
    [Documentation]    Verify that project workload metrics return a paginated list of workloads.
    [Tags]    projects    metrics    smoke
    Given a ready project with user access exists
    When AIWB project workload metrics request is sent
    Then response status should be 200
    And response should contain paginated metrics structure

Get project workload metrics with pagination parameters
    [Documentation]    Verify that project workload metrics accept pagination parameters.
    [Tags]    projects    metrics
    Given a ready project with user access exists
    When AIWB project workload metrics request is sent    page=1    page_size=5
    Then response status should be 200
    And response should contain paginated metrics structure

Get project workload metrics with workload type filter
    [Documentation]    Verify that project workload metrics accept workload type filter.
    [Tags]    projects    metrics
    Given a ready project with user access exists
    When AIWB project workload metrics request is sent    workload_type=INFERENCE
    Then response status should be 200
    And response should contain paginated metrics structure

Get project GPU utilization metric
    [Documentation]    Verify that GPU utilization metric can be queried for a project.
    [Tags]    projects    metrics    gpu
    Given a ready project with user access exists
    When AIWB project workload metric request is sent for "gpu_device_utilization"
    Then response status should be 200

Get project GPU memory utilization metric
    [Documentation]    Verify that GPU memory utilization metric can be queried for a project.
    [Tags]    projects    metrics    gpu
    Given a ready project with user access exists
    When AIWB project workload metric request is sent for "gpu_memory_utilization"
    Then response status should be 200

Get project CPU usage metric
    [Documentation]    Verify that the CPU usage metric can be queried for a project.
    [Tags]    projects    metrics    smoke
    Given a ready project with user access exists
    When AIWB project workload metric request is sent for "cpu_usage"
    Then response status should be 200

Get project system memory usage metric
    [Documentation]    Verify that the system memory usage metric can be queried for a project.
    [Tags]    projects    metrics    smoke
    Given a ready project with user access exists
    When AIWB project workload metric request is sent for "system_memory_usage"
    Then response status should be 200

Project with an assigned GPU quota sees its allocation alongside usage
    [Documentation]    A project with a GPU quota should see that quota reported as the
    ...    allocation ceiling next to its GPU device usage.
    [Tags]    projects    metrics    gpu
    Given a ready project with user access exists
    And project quota is set to    gpu_count=2
    When AIWB project workload metric request is sent for "gpu_device_utilization"
    Then response status should be 200
    And GPU device metric should report an allocation ceiling of "2"

Project without an assigned GPU quota sees cluster capacity available
    [Documentation]    A project without a dedicated GPU quota can borrow the cluster's
    ...    GPUs, so its GPU device usage should show the cluster capacity as available.
    ...    Uses an isolated project rather than the shared default, since other
    ...    suites assign a GPU quota to the shared project.
    [Tags]    projects    metrics    gpu
    Given a fresh project with user access exists
    When AIWB project workload metric request is sent for "gpu_device_utilization"
    Then response status should be 200
    And GPU device metric should report cluster capacity as its available ceiling

Project workload metric rejects start after end
    [Documentation]    Verify that the API rejects metrics requests where start is after end.
    [Tags]    projects    metrics    smoke    negative
    Given a ready project with user access exists
    When AIWB project workload metric request is sent with invalid date range    start_after_end
    Then response status should be 400

Project workload metric rejects start too far in the past
    [Documentation]    Verify that the API rejects metrics requests where start is older than 30 days.
    [Tags]    projects    metrics    smoke    negative
    Given a ready project with user access exists
    When AIWB project workload metric request is sent with invalid date range    start_too_old
    Then response status should be 400

Project workload metric rejects end in the future
    [Documentation]    Verify that the API rejects metrics requests where end is in the future.
    [Tags]    projects    metrics    smoke    negative
    Given a ready project with user access exists
    When AIWB project workload metric request is sent with invalid date range    end_in_future
    Then response status should be 400

Project listing excludes projects without user access
    [Documentation]    Verify that project listing only includes projects the user has access to.
    [Tags]    projects    list    smoke    access-control
    Given a ready project with user access exists
    And a project without user access exists
    When AIWB list projects request is sent
    Then response should contain project list
    And project list should include current project
    And project list should not include inaccessible project

Get project workload metrics exposes creation metadata for fine-tuned AIM services
    [Documentation]    createdAt and createdBy must not be null for fine-tuned AIM services
    ...    deployed in a project, even though they have no Postgres row.
    [Tags]    projects    metrics    finetuning    gpu
    Given a ready project with user access exists
    And project quota is set to    gpu_count=2
    And secret "minio-credentials-fetcher" is assigned to project
    And a finetuning workload exists
    And finetuned model onboarding status should be "ready"
    And fine-tuned model is deployed as an AIM service
    When AIWB project workload metrics request is sent
    Then response status should be 200
    And the fine-tuned AIM service entry should expose its creator and creation time
