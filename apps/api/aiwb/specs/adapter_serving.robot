# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for serving a deployment together with LoRA adapters, and for
...                 changing the adapters of one already running. Covers what a deployment reports
...                 when nothing is attached, the adapter arrangement a created deployment records,
...                 a deployment that actually serves a compatible adapter, the reasons an adapter
...                 is turned away -- a base model it cannot serve, weights that never finished
...                 uploading, serving hardware that cannot carry it at all -- the refusal of a
...                 whole deployment over a single unusable adapter, the sets a running deployment
...                 will and will not accept, a change carrying a scaling change with it, a
...                 scaling-only change on a deployment that cannot change its adapters, and the
...                 release of an adapter once nothing is serving it.
...
...                 The change scenarios act on a deployment created directly rather than deployed.
...                 A change only reads and rewrites the adapter set the deployment records, so
...                 standing a model up on a GPU would buy them nothing -- pinning a real
...                 adapter-capable profile there would schedule the workload for real, holding an
...                 accelerator that a spec-only scenario never needs. Those deployments pin an
...                 unresolvable profile name instead, which keeps them from scheduling at all.
...
...                 Refusing a request for adapters on serving hardware that cannot carry them is
...                 proved here rather than left to unit tests: the claim is that the refusal comes
...                 from the request itself, before anything is created, and only an end-to-end run
...                 shows where it actually comes from. Both shapes a user can ask in are covered --
...                 naming an adapter outright, and asking only that adapters stay free to change.
...                 Neither costs an accelerator, because nothing is created to schedule. Its
...                 counterpart is here too -- the same request going through on hardware that can
...                 honour it -- and that one does schedule, because being accepted means a
...                 deployment is created.
...
...                 That refusal is only reachable when the request pins the hardware. Left to
...                 choose, the engine picks after the deployment exists and owns the rejection
...                 itself, so there is nothing for the platform to refuse up front.
# Nearly every scenario below picks its model out of the cluster's AIM catalog, so it needs that
# catalog to carry a Ready model. Defaulting the whole suite to the dependency and opting the few
# exceptions out keeps a newly added scenario safe: it inherits the tag rather than silently
# reintroducing a structural failure on a cluster with no catalog.
Test Tags           needs-aim-images
Resource            resources/aiwb_adapter_serving.resource
Resource            resources/airm_projects.resource
Suite Teardown      Run Keywords
...                     Clean Up All Created Adapter Artifacts
...                     AND    Clean Up All Created Adapter Weights
...                     AND    Clean Up All Created Projects With Wait


*** Test Cases ***
Deploying without adapters reports none
    [Documentation]    A deployment nobody attached adapters to says so, so a client can tell an
    ...    unattached deployment apart from one whose adapters have not been reported yet.
    [Tags]    adapters    deploy    gpu
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And the project has GPU quota available
    And an AIM exists in system
    When the model is deployed without adapters
    Then the deployment should report no adapters

Deployment records the adapter arrangement it was asked for
    [Documentation]    The adapter named in the deploy request, and the choice to let adapters
    ...    change while the deployment runs, both reach the deployment the engine reconciles. The
    ...    choice is only ever made at this moment -- a deployment cannot be moved between the two
    ...    afterwards -- so a request that is not carried over strands the user. Only the record is
    ...    checked; bringing the model up is the responsibility of the scenario this suite defers.
    [Tags]    adapters    deploy    gpu    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And the project has GPU quota available
    And an AIM exists in system
    And an adapter the model can serve exists in the project
    When the model is deployed with the adapter it can serve and adapters left free to change
    Then the deployment should record the adapter it was asked to serve
    And the deployment should record that its adapters may change while it runs

A deployment actually serves a compatible adapter
    [Documentation]    A deployment carrying an adapter it can serve comes up and reports the
    ...    adapter available for inference, not merely recorded. The change scenarios later in this
    ...    suite only prove the record reaches the deployment's manifest; this is the one scenario
    ...    that proves the engine follows through and the platform passes that through too.
    [Tags]    adapters    deploy    gpu    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And the project has adapter-serving quota available
    And an adapter the model can serve exists in the project
    When the model is deployed with a compatible adapter attached
    Then the deployment should become ready and serve the adapter

Deploying an adapter the model cannot serve is refused
    [Documentation]    An adapter trained against a different base model would produce nonsense if
    ...    it were loaded, so the deployment is refused before anything is created rather than
    ...    failing once the model server rejects the weights.
    [Tags]    adapters    deploy    negative    smoke    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM exists in system
    And an adapter the model cannot serve exists in the project
    When the user attempts to deploy the model with the adapter it cannot serve
    Then the deployment should be refused
    And the refusal should say the adapter cannot serve this model
    And no deployment should have been created

Deploying an adapter whose upload has not finished is refused
    [Documentation]    An adapter whose weights never arrived cannot be loaded, so the user is told
    ...    to finish the upload rather than left with a deployment that crashes on the missing
    ...    files.
    [Tags]    adapters    deploy    negative
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM exists in system
    And an adapter whose upload has not finished exists in the project
    When the user attempts to deploy the model with the adapter whose upload has not finished
    Then the deployment should be refused
    And the refusal should say the adapter has no uploaded weights
    And no deployment should have been created

Deploying an adapter onto serving hardware that cannot carry it is refused
    [Documentation]    An adapter is only usable on a runtime built to load one. Pointing a
    ...    deployment at hardware that cannot is refused while the user can still pick different
    ...    hardware, rather than accepted and left to fail once the engine reaches the same
    ...    conclusion -- by which point the user is watching a deployment that will never serve.
    [Tags]    adapters    deploy    negative    smoke    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM whose serving hardware cannot carry adapters exists in system
    And an adapter the model can serve exists in the project
    When the user attempts to deploy the model onto that hardware with a compatible adapter
    Then the deployment should be refused
    And the refusal should say the chosen hardware cannot serve adapters
    And no deployment should have been created

Deploying with adapters left free to change onto hardware that cannot carry them is refused
    [Documentation]    Asking to keep adapters changeable is a promise about the whole life of the
    ...    deployment, and it cannot be granted after the fact -- so a user who starts with none
    ...    still has to be told now that the hardware will never honour it. Accepted instead, they
    ...    would find out only when their first adapter is turned away by a deployment they can no
    ...    longer change and have to tear down.
    [Tags]    adapters    deploy    negative    smoke
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM whose serving hardware cannot carry adapters exists in system
    When the user attempts to deploy the model onto that hardware with no adapters but free to change them
    Then the deployment should be refused
    And the refusal should say the chosen hardware cannot serve adapters
    And no deployment should have been created

Deploying with adapters left free to change onto hardware that can carry them is accepted
    [Documentation]    Starting with no adapters is an ordinary way to open a deployment to them --
    ...    stand the endpoint up first, attach as adapters are trained. The refusals above must not
    ...    cost a user that, so the same request the incapable hardware turns away is shown going
    ...    through on hardware that can honour it, and reaching the deployment the engine
    ...    reconciles. This one pins a real adapter-capable profile, so it schedules for real.
    [Tags]    adapters    deploy    gpu    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And the project has adapter-serving quota available
    When the model is deployed onto that hardware with no adapters but free to change them
    Then the deployment should be accepted
    And the deployment should record that its adapters may change while it runs

One unusable adapter refuses the whole deployment
    [Documentation]    A deployment is all-or-nothing: a user who attaches several adapters gets no
    ...    partial deployment quietly serving the usable ones, and the refusal points at the one
    ...    they have to replace instead of making them work it out by elimination.
    [Tags]    adapters    deploy    negative    smoke    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM exists in system
    And an adapter the model can serve exists in the project
    And an adapter the model cannot serve exists in the project
    When the user attempts to deploy the model with both adapters
    Then the deployment should be refused
    And the refusal should name only the adapter that cannot be served
    And no deployment should have been created

Removing an adapter once no deployment uses it succeeds
    [Documentation]    The guard that protects an adapter a deployment is serving lets go the
    ...    moment nothing serves it, so a user who has taken the deployment away is not left with
    ...    an adapter they can never remove.
    # Its deployment is applied straight as a spec-only service pinning an unresolvable profile,
    # so it never picks a model out of the catalog and holds where there is none.
    [Tags]    -needs-aim-images    adapters    delete    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    And an AIM deployment attaching the adapter artifact exists in the project
    When the deployment using the adapter is removed
    And the adapter artifact is deleted
    Then the adapter artifact removal should be accepted
    And the adapter artifact should no longer appear in the project list

Changing the adapters of a deployment that allows it is accepted
    [Documentation]    A deployment created free to change its adapters takes a new set while it
    ...    runs, and the set it was asked for reaches the deployment the engine reconciles.
    ...    Acceptance is not a claim that the adapter is serving traffic, which is asserted here
    ...    too: a user who reads it as one sends requests the model cannot answer.
    [Tags]    adapters    update    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM exists in system
    And an adapter the model can serve exists in the project
    And a deployment whose adapters may change while it runs exists
    When the user changes the adapters the deployment should serve
    Then the change should be accepted
    And the deployment should record the adapters it was asked to serve
    And the deployment should not yet report the new adapters as available for inference

Changing the adapters and the scaling of a deployment together is accepted
    [Documentation]    A user who wants both changes gets both from one request. Asking for them
    ...    together is not refused, and neither change lands without the other -- a deployment left
    ...    holding half of what was asked for is what a caller cannot recover from on their own.
    [Tags]    adapters    update    scaling    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM exists in system
    And an adapter the model can serve exists in the project
    And a deployment whose adapters may change while it runs exists
    When the user changes the adapters and how the deployment scales at once
    Then the change should be accepted
    And the deployment should record the adapters it was asked to serve
    And the deployment should record the scaling it was asked for

Removing every adapter from a deployment that allows it is accepted
    [Documentation]    Asking for an empty set detaches everything, so a user can take an adapter
    ...    out of service without taking the deployment down with it.
    [Tags]    adapters    update    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM exists in system
    And an adapter the model can serve exists in the project
    And a deployment whose adapters may change while it runs is serving that adapter
    When the user removes every adapter from the deployment
    Then the change should be accepted
    And the deployment should record no adapters

Changing the adapters of a deployment fixed at creation is refused
    [Documentation]    Whether adapters may change is settled when the deployment is created and
    ...    can never be granted afterwards, so the user is told to redeploy rather than left
    ...    watching for a change that was accepted and will never take effect.
    [Tags]    adapters    update    negative    smoke    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM exists in system
    And an adapter the model can serve exists in the project
    And a deployment whose adapters were fixed when it was created exists
    When the user changes the adapters the deployment should serve
    Then the change should be refused
    And the refusal should say the deployment cannot change its adapters
    And the deployment should record no adapters

Changing only the scaling of a deployment fixed at creation leaves its adapters alone
    [Documentation]    Whether adapters may change gates adapter changes only, not the endpoint as
    ...    a whole, so a deployment created without that freedom still accepts a change that only
    ...    asks it to scale. Saying nothing about adapters asks for nothing: the ones it is already
    ...    serving stay, rather than being quietly taken out of service by a request that never
    ...    mentioned them.
    [Tags]    adapters    update    scaling    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM exists in system
    And an adapter the model can serve exists in the project
    And a deployment whose adapters were fixed when it was created is serving that adapter
    When the user changes only how the deployment scales
    Then the change should be accepted
    And the deployment should record the scaling it was asked for
    And the deployment should still record the adapter it was already serving

Changing to an adapter the model cannot serve is refused
    [Documentation]    A running deployment is held to the compatibility rule a new one is: an
    ...    adapter trained against a different base model is turned away before it reaches the
    ...    deployment, rather than after the model server chokes on the weights.
    [Tags]    adapters    update    negative    smoke    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM exists in system
    And an adapter the model cannot serve exists in the project
    And a deployment whose adapters may change while it runs exists
    When the user attempts to change the deployment to an adapter the model cannot serve
    Then the change should be refused
    And the refusal should say the requested adapter cannot serve this model
    And the deployment should record no adapters

Changing the adapters of a deployment that does not exist is refused
    [Documentation]    Naming a deployment the project does not hold is reported as a missing
    ...    deployment, so a user chasing a stale identifier is not left believing the adapters
    ...    they asked for were the problem.
    # Names a deployment that was never created, so it never reaches the AIM catalog -- the one
    # scenario here that holds on a cluster publishing no models.
    [Tags]    -needs-aim-images    adapters    update    negative    smoke
    Given a ready project with user access exists
    When the user attempts to change the adapters of a deployment that does not exist
    Then the deployment should not be found

An adapter released by a change can then be removed
    [Documentation]    The guard protecting an adapter a deployment is serving reads the
    ...    deployment's current set, so detaching an adapter releases it there and then. Without
    ...    that, freeing an adapter would mean taking the whole deployment down.
    [Tags]    adapters    update    delete    kubectl
    [Teardown]    Remove the deployment created by this test
    Given a ready project with user access exists
    And an AIM exists in system
    And an adapter the model can serve exists in the project
    And a deployment whose adapters may change while it runs is serving that adapter
    When the user removes every adapter from the deployment
    And the released adapter is deleted
    Then the released adapter removal should be accepted
    And the released adapter should no longer appear in the project list
