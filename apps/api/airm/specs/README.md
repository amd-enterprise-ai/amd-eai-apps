<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AIRM End-to-End Tests

End-to-end tests for the AI Resource Manager (AIRM) backend service, covering API endpoints, workload management, project management, quotas, secrets, and storage using Robot Framework.

## Quick Start

### Prerequisites

1. **Install [uv](https://docs.astral.sh/uv/) and `kubectl`.**

2. **Configure Kubernetes authentication** in your kubeconfig (`~/.kube/config`):

   The test infrastructure automatically handles authentication using OIDC credentials from your kubeconfig. Configure the `users` section with OIDC login:

   ```yaml
   users:
     - name: your-context-name
       user:
         exec:
           apiVersion: client.authentication.k8s.io/v1beta1
           args:
             - oidc-login
             - get-token
             - --oidc-issuer-url=https://kc.<your-domain>/realms/airm
             - --oidc-client-id=k8s
             - --oidc-client-secret=<insert client secret>
             - --grant-type=password
             - --username=<keycloak user with admin privileges>
             - --password=<very secret password>
           command: kubectl
           env: null
           interactiveMode: IfAvailable
           provideClusterInfo: false
   ```

   **Important**: Replace placeholder values with your actual credentials:
   - `--oidc-issuer-url`: Your Keycloak realm URL
   - `--oidc-client-secret`: Client secret from Keycloak
   - `--username`: Keycloak user with admin privileges
   - `--password`: User's password

3. **Set active Kubernetes context**:
   ```bash
   kubectl config use-context your-context-name
   ```

### Running Tests

Tests are run using Robot Framework via `uv run robot`. The specs directory includes an `arguments.txt` file with recommended settings (pythonpath, output directory, log level, etc.).

**Note:** The `arguments.txt` file is **safe to use with all test suites**. It includes common settings for pythonpath, output directory, and log level.

#### Setup

```bash
# Install AIRM dev dependencies (includes Robot Framework and all required libraries)
cd apps/api/airm
uv sync --dev

# Navigate to the specs directory
cd specs
```

#### Running Tests

**Important:** Since the `pyproject.toml` is in `apps/api/airm/` and tests are in `apps/api/airm/specs/`, use `--project ..` when running from the specs directory so `uv` uses the same virtual environment.

```bash
# Run all tests using arguments.txt (recommended)
uv run --project .. robot --argumentfile arguments.txt .

# Run smoke tests (quick validation)
uv run --project .. robot --argumentfile arguments.txt --include smoke .

# Exclude GPU-intensive tests
uv run --project .. robot --argumentfile arguments.txt --exclude gpu .

# Run a single test suite
uv run --project .. robot --argumentfile arguments.txt projects.robot

# Run a specific test by name
uv run --project .. robot --argumentfile arguments.txt --test "Create project and verify status" .

# Override output directory if needed
uv run --project .. robot --argumentfile arguments.txt --outputdir /custom/path .

# Rerun only failed tests
uv run --project .. robot --argumentfile arguments.txt --rerunfailed results/output.xml .
```

**Common tag filtering patterns:**

```bash
# Quick smoke test (no GPU required)
uv run --project .. robot --argumentfile arguments.txt --include smoke --exclude gpu .

# Run all tests except GPU-intensive ones
uv run --project .. robot --argumentfile arguments.txt --exclude gpu .

# Run only project-related tests
uv run --project .. robot --argumentfile arguments.txt --include projects .

# Run tests that are BOTH smoke AND projects
uv run --project .. robot --argumentfile arguments.txt --include smokeANDprojects .

# Run tests from specific subdirectory
uv run --project .. robot --argumentfile arguments.txt airm/
```

**Test Organization:**

Tests are organized into logical subdirectories:

- **`airm/`** - Infrastructure management (projects, quotas, secrets, storage, workloads, preemption)
- **Root level** - Special suites (health.robot, test_tracking.robot)

### Configuration

The `arguments.txt` file contains common Robot Framework settings. You can override any argument:

```bash
# Override log level for debugging
uv run --project .. robot --argumentfile arguments.txt --loglevel TRACE .

# Change output directory
uv run --project .. robot --argumentfile arguments.txt --outputdir /tmp/results .
```

Per-test timeout overrides use `Test Timeout` in a suite's `*** Settings ***` table or `[Timeout]` in a test case.

See `arguments.txt` for available options.

### Analyzing Test Results

After running tests, Robot Framework generates HTML reports in `specs/results/`:

- **`log.html`** - Detailed execution log with expandable keyword tree (open in browser)
- **`report.html`** - High-level test report with statistics and pass/fail summary
- **`output.xml`** - Machine-readable results

#### Browser-Based Analysis

```bash
firefox specs/results/log.html
```

### Test Tags

Tests use Robot Framework tags for filtering and test selection. Use tags to run subsets of tests based on functionality, speed, or resource requirements.

**General-Purpose Tags:**

| Tag       | Purpose                               | Usage                                                                                                      |
| --------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `smoke`   | Fast tests for quick validation       | Quick smoke testing without waiting. Typically completes in <1 minute per test. Use: `--include smoke`     |
| `gpu`     | Tests requiring GPU resources         | Excludes GPU-intensive tests (AIM deployments, finetuning). Use: `--exclude gpu` for CPU-only environments |
| `kubectl` | Tests using kubectl/helm verification | Tests that interact directly with Kubernetes resources. Useful for isolating K8s-specific tests            |

**Feature-Specific Tags:**

Tests are also tagged by feature area (`projects`, `workload`, `quota`, `secret`, `storage`, `preemption`, `metrics`, `nodes`, `clusters`) and operation type (`create`, `delete`, `list`, etc.). See individual test files for complete tag lists.

## Test Suites

The test suites are organized into logical directories for better maintainability:

### AIRM Tests (`airm/`)

Infrastructure and platform management features: projects, quotas, secrets, storage, workloads, and preemption scenarios. List suites with `ls airm/*.robot`.

**Running AIRM tests:**

```bash
# All AIRM tests
uv run --project .. robot --argumentfile arguments.txt airm/

# Specific AIRM suite
uv run --project .. robot --argumentfile arguments.txt airm/projects.robot
```

### Root Level Tests

Special-purpose test suites at the root level (health checks, test infrastructure).

## Test Architecture

### Directory Structure

```
specs/
├── *.robot                              # Root-level test suites (health, tracking)
├── airm/                                # AIRM infrastructure test suites
│   └── *.robot
├── libraries/                           # Python libraries (port forwarding, auth, utils)
└── resources/
    ├── airm_*.resource                  # Business logic keywords (high-level)
    ├── api/                             # Low-level HTTP operation keywords
    │   └── common.resource              # Safe HTTP request wrappers
    ├── common/                          # Shared utilities (resource tracking, resolver)
    ├── kubectl_*.resource               # Kubernetes verification keywords
    ├── authorization.resource           # Auth and OIDC validation
    └── deployment.resource              # Service endpoint resolution
```

### Three-Layer Architecture

Tests follow a layered approach for maintainability:

1. **Test Files (.robot)** - BDD-style Given-When-Then test cases
2. **AIRM Resources (airm\_\*.resource)** - Business logic keywords
3. **API Resources (api/\*.resource)** - Low-level HTTP operations

**Important:** Test files should NEVER call API resources directly. Always go through AIRM resource keywords.

**Example Flow:**

```robot
# Test file (airm/projects.robot)
Test Case: Create and verify project
    Given a cluster exists in system
    And valid project data is prepared
    When create project request is sent
    Then response status should be 200
    And project should exist in system

# Catalog layer (airm_projects.resource)
Project should exist in system
    ${id}=    The project
    ${response}=    Get project    ${id}
    Should Be Equal As Integers    ${response.status_code}    200

# API layer (api/projects.resource)
Get project
    [Arguments]    ${project_id}
    ${endpoint}=    Set Variable    /v1/projects/${project_id}
    ${response}=    Safe Get Request    ${endpoint}
    RETURN    ${response}
```

### Connection Resilience

Tests access cluster services via automatic port forwarding with built-in resilience:

- **Automatic Port Forwarding**: Created on-demand for required services (airm-api, cluster-auth)
- **Caching**: Port forwards cached for 1 hour via `libraries/KubeConnection.py`
- **Health Checks**: Socket validation before each HTTP request
- **Auto-Recovery**: Automatic recreation on failure ensures test reliability

**Safe HTTP Request Keywords** (defined in `resources/api/common.resource`):

- `Safe Get Request` - GET with port forward validation
- `Safe Post Request` - POST with port forward validation
- `Safe Put Request` - PUT with port forward validation
- `Safe Delete Request` - DELETE with port forward validation
- `Safe Patch Request` - PATCH with port forward validation

**Always use safe wrappers** when adding new resource keywords:

```robot
# ✅ CORRECT - Uses safe wrapper
My New Keyword
    ${response}=    Safe Get Request    /v1/my-endpoint
    RETURN    ${response}

# ❌ WRONG - Direct RequestsLibrary call
My New Keyword
    ${response}=    Get On Session    ${API_SESSION}    /v1/my-endpoint
    RETURN    ${response}
```

## Writing and Maintaining Tests

### Test Structure Best Practices

**1. Use BDD-Style Keywords**

```robot
Test Case: Create and delete project
    [Tags]    smoke    projects
    Given a cluster exists in system
    And valid project data is prepared
    When create project request is sent
    Then response status should be 200
    And project should exist in system
    When delete project request is sent
    Then response status should be 204
```

**2. Test Independence**

- Each test should be self-contained
- Use test-scoped variables for test data
- Clean up only test-created resources
- Don't assume environment state

**3. Resource Management**

- Track created resources in `@{CREATED_RESOURCE_IDS}`
- Use suite teardown for cleanup
- Rely on project deletion CASCADE for orphaned resources

**4. Logging Levels**

```robot
# TRACE - Repetitive polling/status checks
Log    Waiting for workload status...    TRACE

# DEBUG - API requests/responses, resource IDs
Log    Created project ID: ${PROJECT_ID}    DEBUG

# INFO - Key milestones, state transitions
Log    Project reached Running state    INFO

# WARN - Recoverable issues, fallbacks
Log    Port forward died, recreating...    WARN
```

### Adding New Test Suites

1. **Create test file** following naming convention: `<feature>.robot`

2. **Add appropriate tags** for filtering:

   ```robot
   *** Test Cases ***
   My Test Case
       [Tags]    smoke    <feature>    <category>
       ...
   ```

3. **Reuse existing keywords** from AIRM resources:

   ```robot
   *** Settings ***
   Resource    resources/airm_projects.resource
   Resource    resources/airm_workloads.resource
   ```

4. **Document test purpose**:

   ```robot
   *** Test Cases ***
   Create project with custom quota
       [Documentation]    Verify project creation with custom resource quota
       [Tags]    projects    quotas
       ...
   ```

5. **Ensure proper cleanup**:
   ```robot
   *** Settings ***
   Suite Teardown    Cleanup Created Resources
   ```

### Adding New Resource Keywords

When extending test capabilities:

1. **Follow the layer architecture**:
   - API keywords in `resources/api/<feature>.resource`
   - Business logic in `resources/airm_<feature>.resource`

2. **Use safe HTTP wrappers**:

   ```robot
   # In resources/api/my_feature.resource
   Get My Resource
       [Arguments]    ${resource_id}
       ${endpoint}=    Set Variable    /v1/my-resource/${resource_id}
       ${response}=    Safe Get Request    ${endpoint}
       RETURN    ${response}
   ```

3. **Add documentation**:

   ```robot
   My Keyword
       [Documentation]    Brief description of what this keyword does
       [Arguments]    ${arg1}    ${arg2}=default
       ...
   ```

4. **Return values consistently**:

   ```robot
   # Return response objects from API keywords
   Create Resource
       ${response}=    Safe Post Request    /v1/resources    json=${data}
       RETURN    ${response}

   # Return domain objects from catalog keywords
   Resource Should Be Created
       ${response}=    Create Resource
       Should Be Equal As Integers    ${response.status_code}    201
       ${resource_id}=    Set Variable    ${response.json()['id']}
       RETURN    ${resource_id}
   ```

### Common Patterns

**Creating Projects with Quotas:**

```robot
# Minimum quota for quota-specific tests
Given a cluster exists in system
And minimum quota data is prepared
And valid project data with quota is prepared
When create project request is sent
Then response status should be 200

# Zero quota for other tests
Given a cluster exists in system
And valid project data is prepared  # Uses zero quota fallback
When create project request is sent
Then response status should be 200
```

**Waiting for Workload Status:**

```robot
# Use built-in wait keywords
Wait For Workload Status    ${WORKLOAD_ID}    Running    timeout=300s

# For custom conditions
Wait Until Keyword Succeeds    5 min    10 sec
...    Workload Should Have Status    ${WORKLOAD_ID}    Running
```

**Resource Tracking and Cleanup:**

```robot
*** Settings ***
Suite Setup       Initialize Test Suite
Suite Teardown    Cleanup Created Resources

*** Keywords ***
Track Created Resource
    [Arguments]    ${resource_id}
    Append To List    ${CREATED_RESOURCE_IDS}    ${resource_id}

Cleanup Created Resources
    FOR    ${resource_id}    IN    @{CREATED_RESOURCE_IDS}
        Run Keyword And Ignore Error    Delete Resource    ${resource_id}
    END
```

## Troubleshooting

### Common Issues

**Authentication failures:**

- Verify kubeconfig OIDC settings are correct
- Check that kubectl context is set to the correct cluster
- Ensure OIDC credentials in kubeconfig are valid

**Port forwarding issues:**

- Tests should auto-recover via safe HTTP wrappers
- Check stuck processes: `ps aux | grep "kubectl port-forward"`
- Verify cluster connectivity: `kubectl get pods -n airm`

**Resource conflicts:**

- Check for orphaned resources from previous runs
- Verify project cleanup is working
- Use unique resource names with timestamps

**Timeout issues:**

- Adjust wait timeouts for your environment
- Check cluster resources: `kubectl describe nodes`
- Verify workload logs: `kubectl logs -n <namespace> <pod-name>`

### Debug Commands

```bash
# Run with verbose logging
uv run --project .. robot --argumentfile arguments.txt --loglevel TRACE .

# Dry run to validate test structure
uv run --project .. robot --argumentfile arguments.txt --dryrun .
```

### Getting Help

- View test results: `specs/results/log.html`
- Check Robot Framework logs for detailed execution trace
- Refer to [Robot Framework User Guide](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html)

## Related Documentation

- **[Robot Framework User Guide](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html)** - Official Robot Framework documentation
- **[RequestsLibrary Documentation](https://marketsquare.github.io/robotframework-requests/doc/RequestsLibrary.html)** - HTTP request library reference
