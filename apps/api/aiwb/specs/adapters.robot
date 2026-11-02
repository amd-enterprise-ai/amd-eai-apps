# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for project adapter artifact management.
...                 Covers listing, detail retrieval, download, and deletion of the LoRA adapters
...                 a project owns -- including the base models an adapter declares it fits,
...                 the guard that refuses to delete an adapter a live AIM deployment still
...                 attaches, and the boundary that keeps adapters authored outside the
...                 platform, or weights nothing has registered, out of reach.
Resource            resources/airm_projects.resource
Resource            resources/aiwb_adapters.resource
Suite Teardown      Run Keywords
...                     Clean Up All Created Adapter Artifacts
...                     AND    Clean Up All Created Adapter Weights
...                     AND    Clean Up All Created Projects With Wait


*** Test Cases ***
Project without adapters returns an empty list
    [Documentation]    A project that has never produced an adapter reports none.
    [Tags]    adapters    list    smoke
    Given a ready project with user access exists
    When the project adapter artifact list is retrieved
    Then the adapter artifact list should be empty

Adapters produced by fine-tuning appear in the project list
    [Documentation]    Adapters the fine-tuning engine leaves behind are visible to the project.
    [Tags]    adapters    list    smoke    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    When the project adapter artifact list is retrieved
    Then the adapter artifact list should contain the fine-tuning adapter

Narrowing the list to adapters still returns them
    [Documentation]    A client asking only for adapters gets them, so a filter meant to separate
    ...    artifact kinds never hides the kind it was asked for.
    [Tags]    adapters    list    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    When the project adapter artifact list is retrieved for adapters only
    Then the adapter artifact list should contain the fine-tuning adapter

Adapter list is returned page by page
    [Documentation]    A page holds only the requested number of adapters while the reported
    ...    total still counts every adapter in the project.
    ...    Uses a fresh project so the reported total counts only this test's artifacts —
    ...    a shared project accumulates adapters from other tests and inflates the total.
    [Tags]    adapters    list    pagination    kubectl
    Given a fresh project with user access exists
    And multiple adapter artifacts exist in the project
    When the project adapter artifact list is retrieved with page size 1
    Then the returned adapter page should hold a single artifact
    And the reported adapter total should count every artifact in the project

Adapter whose weights have not landed is listed as not ready
    [Documentation]    An adapter registered before its weight files reach storage is reported
    ...    as not ready, so a client can tell it apart from one it can serve.
    [Tags]    adapters    list    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    When the project adapter artifact list is retrieved
    Then every listed adapter should report its weights as not ready

Adapter weights no artifact claims stay out of the project list
    [Documentation]    Weights left in project storage are not adapters the project owns until
    ...    something registers them, so the list never reports them: with no record there is
    ...    nothing to name, inspect, or delete.
    [Tags]    adapters    list    kubectl
    Given a ready project with user access exists
    And adapter weights that no artifact claims exist in the project storage
    When the project adapter artifact list is retrieved
    Then the adapter artifact list should not contain the unclaimed adapter weights

Adapters can be narrowed to the ones whose weights are ready
    [Documentation]    A user looking for something to serve can exclude adapters whose weights
    ...    have not landed, so only the ones that can actually be deployed reach the shortlist.
    [Tags]    adapters    list    kubectl
    Given a ready project with user access exists
    And an adapter whose weights were uploaded through the workbench
    And a fine-tuning adapter artifact exists in the project
    When the project adapter artifact list of ready adapters is retrieved
    Then the adapter artifact list should contain the uploaded adapter
    And the adapter artifact list should not contain the fine-tuning adapter

Adapter weights the project already holds can be registered where they are
    [Documentation]    Weights sitting in the project's storage are onboarded the same way any
    ...    existing storage location is, and registering them is what puts them in the project list.
    [Tags]    adapters    list    create    kubectl
    Given a ready project with user access exists
    And adapter weights that no artifact claims exist in the project storage
    When the user registers the unclaimed adapter weights from where they are stored
    And the project adapter artifact list is retrieved
    Then the registered adapter weights should now appear in the project list

Registering an adapter reports the base model it fits
    [Documentation]    An adapter is registered against the base models it may attach to, and the
    ...    project reports that back so a user can tell what the adapter serves without opening its
    ...    weights. Nothing has to hold those base models for the adapter to be registered and ready.
    [Tags]    adapters    create    kubectl
    Given a ready project with user access exists
    And adapter weights that no artifact claims exist in the project storage
    When the user registers the unclaimed adapter weights from where they are stored
    And the adapter artifact detail is retrieved by name
    Then the adapter should report the base model it fits
    And the adapter should be ready even though the project holds no such base model

Registering an adapter keeps the description it was given
    [Documentation]    A user explains what an adapter is for in their own words at registration, and
    ...    the project has to hand those words back when the adapter is inspected later.
    [Tags]    adapters    create    kubectl
    Given a ready project with user access exists
    And adapter weights that no artifact claims exist in the project storage
    When the user registers the unclaimed adapter weights from where they are stored
    And the adapter artifact detail is retrieved by name
    Then the adapter should carry the description it was registered with

Registering stored weights that record no rank keeps the rank it was given
    [Documentation]    Weights already in the project carry stored details of their own, and those
    ...    details are what the project trusts about them. Where they say nothing about the adapter's
    ...    rank there is nothing to trust, so the rank the user states at registration is what the
    ...    project has to report back.
    [Tags]    adapters    create    kubectl
    Given a ready project with user access exists
    And adapter weights already in the project whose stored details record no rank
    When the user registers the stored adapter weights and states their rank
    And the adapter artifact detail is retrieved by name
    Then the adapter should report the rank it was registered with

An adapter produced by fine-tuning reports the base model it fits
    [Documentation]    The declaration belongs to the adapter, not to the API that registered it, so
    ...    an adapter the fine-tuning engine left behind is described the same way as one onboarded here.
    [Tags]    adapters    detail    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    When the adapter artifact detail is retrieved by name
    Then the adapter should report the base model it fits

An adapter produced by fine-tuning keeps its description
    [Documentation]    A user's explanation of a fine-tuning run remains attached to the adapter
    ...    it produces and is returned when the adapter is inspected later.
    [Tags]    adapters    detail    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    When the adapter artifact detail is retrieved by name
    Then the fine-tuning adapter should carry its description

An adapter produced by fine-tuning reports its creator
    [Documentation]    The submitter annotation a fine-tuning run stamps on the adapter it
    ...    produces survives being read back, so the project can still show who created it
    ...    when the adapter is inspected.
    [Tags]    adapters    detail    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    When the adapter artifact detail is retrieved by name
    Then the fine-tuning adapter should report its creator

Registering an adapter describes it the same way the project list does
    [Documentation]    A client that has just registered an adapter should be able to render it
    ...    straight into the collection it is already showing, rather than fetching it again to get
    ...    a description in a different shape.
    [Tags]    adapters    create    kubectl
    Given a ready project with user access exists
    And adapter weights that no artifact claims exist in the project storage
    When the user registers the unclaimed adapter weights from where they are stored
    And the project adapter artifact list is retrieved
    Then the registration result should describe the adapter the same way the project list does

Registering an adapter whose declared file would not land under its storage is refused
    [Documentation]    A registration declares where each of the adapter's files is to be written,
    ...    relative to the storage the project sets aside for it. Some shapes of path do not name one
    ...    definite file under that storage: a step that resolves away moves the file or erases it,
    ...    and an opening that a receiving platform reads as rooted elsewhere discards the storage
    ...    entirely. Either way the file would not end up where the registration said, so the project
    ...    refuses the registration instead of taking it in and finding out afterwards. Every shape
    ...    below is refused for the same reason, so they are one scenario over the shapes rather than
    ...    one scenario each.
    [Tags]    adapters    create    negative
    [Setup]    Given a ready project with user access exists
    [Template]    Registering an adapter that declares the file path should be refused
    # A step that resolves away
    weights/./notes.md
    # Rooted at a drive rather than at the adapter's storage, absolute and relative alike
    C:/outside/notes.md
    C:outside/notes.md
    # A separator this platform does not read but the receiving one does, each doubled so that
    # Robot passes the backslash on rather than reading it as the start of an escape
    weights\\..\\..\\notes.md

Retrieve a single adapter by name
    [Documentation]    An adapter can be inspected individually once it exists.
    [Tags]    adapters    detail    smoke    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    When the adapter artifact detail is retrieved by name
    Then the adapter should be found
    And the adapter artifact detail should describe the requested adapter

Requesting an unknown adapter reports it as not found
    [Documentation]    Asking for an adapter the project does not have is a clean not-found.
    [Tags]    adapters    detail    negative
    Given a ready project with user access exists
    When the adapter artifact detail is requested for name "does-not-exist"
    Then the adapter should be reported as not found

Adapter belonging to another project is not reachable
    [Documentation]    Adapters do not leak across project boundaries.
    [Tags]    adapters    detail    namespace    negative    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    And a second ready project exists for namespace isolation
    When the adapter artifact detail is requested from the second project by name
    Then the adapter should be reported as not found

Adapter created outside the platform stays hidden
    [Documentation]    An adapter another operator authored is neither listed nor readable,
    ...    so the platform never surfaces artifacts it does not own.
    [Tags]    adapters    list    detail    negative    kubectl
    Given a ready project with user access exists
    And an adapter artifact created outside the platform exists in the project
    When the project adapter artifact list is retrieved
    Then the adapter artifact list should not contain the externally created adapter
    When the externally created adapter artifact detail is requested
    Then the adapter should be reported as not found

Downloading an adapter hands back every file it is made of
    [Documentation]    An adapter a user has in one place should be usable in another, so a download
    ...    has to hand over every file the adapter is made of -- a partial set would look like an
    ...    export while producing something that cannot be loaded.
    [Tags]    adapters    download    smoke    kubectl
    Given a ready project with user access exists
    And an adapter whose weights were uploaded through the workbench
    When the adapter is downloaded
    Then the download should list every file the adapter is made of
    And every offered file should come with a link, and its size where storage reports one

Downloading an adapter hands back a file kept in a subdirectory
    [Documentation]    An adapter is whatever was registered with it, and a registration may place a
    ...    file below the weights rather than beside them. A download that skipped those files, or
    ...    offered them as if they sat at the root, would hand back an adapter the receiver cannot
    ...    put together again -- so what the project accepted on the way in comes back on the way out,
    ...    in the same shape.
    [Tags]    adapters    download    kubectl
    Given a ready project with user access exists
    And an adapter uploaded with an extra file in a subdirectory
    When the adapter is downloaded
    Then the download should list every file the adapter is made of
    And the download should keep the nested file under its subdirectory

Downloaded adapter files can be retrieved outside the platform
    [Documentation]    The point of a download is that the files travel: they are fetched directly by
    ...    whoever asked for them, without the platform carrying the bytes, so the links have to work
    ...    from outside it and deliver the whole file.
    [Tags]    adapters    download    kubectl
    Given a ready project with user access exists
    And an adapter whose weights were uploaded through the workbench
    When the adapter is downloaded
    Then the adapter's files should be retrievable from where the download points

A downloaded adapter can be brought back into a project
    [Documentation]    A download is only an export if the files it hands over can be imported again,
    ...    so they are fetched from where it points and put back in as a new adapter. What the new
    ...    adapter is gets declared on the way in, as any registration does; what has to survive the
    ...    trip is the files -- their contents and where they sit, which is why the adapter that
    ...    makes the trip keeps one of them below the weights rather than beside them. Both adapters
    ...    end up in the same project because a location outside it cannot be registered against, but
    ...    the new one is built from files that made the round trip rather than from the ones already
    ...    there.
    [Tags]    adapters    download    create    kubectl
    Given a ready project with user access exists
    And an adapter uploaded with an extra file in a subdirectory
    When the adapter is downloaded
    And the user carries the downloaded files back in as a new adapter
    Then the new adapter should hold the files the download handed over
    And the new adapter should keep the nested file under its subdirectory
    And the new adapter should be ready to serve

An adapter recording weights outside the project cannot be downloaded
    [Documentation]    Every project's files sit in one shared store, so the location an adapter
    ...    records is not trusted on its own: a download signs direct links to whatever it names, and
    ...    a record pointing outside the project would turn into working access to another tenant's
    ...    files.
    [Tags]    adapters    download    namespace    negative    kubectl
    Given a ready project with user access exists
    And an adapter whose recorded weights lie outside the project
    When the user attempts to download the adapter
    Then the download should be refused as reaching outside the project

An adapter whose weights never landed cannot be downloaded
    [Documentation]    A registration whose upload never finished names an adapter that does not
    ...    exist yet, and handing out links to it would produce files nothing can load.
    [Tags]    adapters    download    negative
    Given a ready project with user access exists
    And an adapter registered for upload whose weights never arrived
    When the user attempts to download the adapter
    Then the download should be refused as incomplete

Requesting a download of an unknown adapter reports it as not found
    [Documentation]    Asking to download an adapter the project does not have is a clean not-found.
    [Tags]    adapters    download    negative
    Given a ready project with user access exists
    When a download is requested for the adapter named "does-not-exist"
    Then the adapter download should report it as not found

An adapter belonging to another project cannot be downloaded
    [Documentation]    A download is a way out of the platform for the files behind an adapter, so the
    ...    project boundary has to hold here just as it does when the adapter is merely inspected.
    [Tags]    adapters    download    namespace    negative    kubectl
    Given a ready project with user access exists
    And an adapter whose weights were uploaded through the workbench
    And a second ready project exists for namespace isolation
    When a download of the adapter is requested from the second project
    Then the adapter download should report it as not found

An adapter created outside the platform cannot be downloaded
    [Documentation]    The platform does not hand out another operator's files, so an artifact it does
    ...    not own is as unreachable for download as it is for inspection.
    [Tags]    adapters    download    negative    kubectl
    Given a ready project with user access exists
    And an adapter artifact created outside the platform exists in the project
    When a download of the externally created adapter is requested
    Then the adapter download should report it as not found

Deleting an adapter created outside the platform leaves it untouched
    [Documentation]    The platform reports nothing to delete rather than removing another
    ...    operator's artifact.
    [Tags]    adapters    delete    negative    kubectl
    Given a ready project with user access exists
    And an adapter artifact created outside the platform exists in the project
    When the externally created adapter artifact is deleted
    Then the delete should report nothing to remove
    And the externally created adapter artifact should still exist in the project

Deleting an adapter removes it from the project
    [Documentation]    A delete is accepted and the adapter stops appearing in the project.
    [Tags]    adapters    delete    smoke    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    When the adapter artifact is deleted
    Then the delete should be accepted
    And the adapter artifact should no longer appear in the project list

Deleting an uploaded adapter reclaims its storage
    [Documentation]    Weights the workbench found room for and wrote are given back when the adapter
    ...    is deleted, so a project's storage does not grow by an adapter every time a user discards one.
    [Tags]    adapters    delete    storage    kubectl
    Given a ready project with user access exists
    And an adapter whose weights were uploaded through the workbench
    When the adapter artifact is deleted
    Then the adapter artifact should no longer appear in the project list
    And its weights should no longer occupy project storage

Deleting a fine-tuned adapter reclaims its training run's storage
    [Documentation]    A LoRA fine-tuning run leaves its adapter in a folder the workbench named for
    ...    the run, alongside run-level files nothing else refers to. Discarding the adapter gives the
    ...    whole run back, so a project's storage does not grow by a training run every time a user
    ...    throws one away.
    [Tags]    adapters    delete    storage    kubectl
    Given a ready project with user access exists
    And a fine-tuning run has left an adapter in project storage
    When the adapter artifact is deleted
    Then the delete should be accepted
    And the adapter artifact should no longer appear in the project list
    And nothing the training run stored should remain

Deleting a fine-tuned adapter leaves other training runs intact
    [Documentation]    Runs of the same base model sit side by side, so reclaiming one run's storage
    ...    must stop at that run and leave every file of its neighbours where it was.
    [Tags]    adapters    delete    storage    kubectl
    Given a ready project with user access exists
    And a fine-tuning run has left an adapter in project storage
    And another fine-tuning run of the same base model has stored its output
    When the adapter artifact is deleted
    Then nothing the training run stored should remain
    And the other training run's output should remain untouched

Deleting an onboarded adapter leaves the user's own files intact
    [Documentation]    Pointing an adapter at files a user already had does not hand those files to
    ...    the platform, so withdrawing the adapter has to leave every one of them exactly where it was.
    [Tags]    adapters    delete    storage    kubectl
    Given a ready project with user access exists
    And an adapter onboarded from storage the user already owned
    When the adapter artifact is deleted
    Then the adapter artifact should no longer appear in the project list
    And the user's files should remain untouched

Storage shared with another adapter is not reclaimed
    [Documentation]    One set of weights can be claimed by two adapters. Deleting the one the
    ...    platform stored them for still removes it, but the files stay, because the other adapter is
    ...    serving from them and reclaiming would break it.
    [Tags]    adapters    delete    storage    kubectl
    Given a ready project with user access exists
    And an adapter whose weights were uploaded through the workbench
    And a second adapter registered against the same stored weights
    When the uploaded adapter is deleted
    Then the uploaded adapter should no longer appear in the project list
    And the stored weights should remain available to the second adapter

Deleting an already-absent adapter reports nothing to delete
    [Documentation]    Deleting twice reaches the same end state without an error.
    [Tags]    adapters    delete    negative
    Given a ready project with user access exists
    When the adapter artifact "does-not-exist" is deleted
    Then the delete should report nothing to remove

Deleting an adapter a deployment still uses is refused
    [Documentation]    Removing weights an AIM deployment serves breaks it the next time it
    ...    reloads them, so the delete is refused and names what is holding the adapter.
    [Tags]    adapters    delete    negative    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    And an AIM deployment attaching the adapter artifact exists in the project
    When the user attempts to delete the adapter artifact
    Then the delete refusal should name the blocking AIM deployment
    And the delete refusal should say how to override it
    And the adapter artifact should still exist in the project
    [Teardown]    Remove blocking AIM deployment for adapter if present

Force-deleting an adapter a deployment still uses removes only the adapter
    [Documentation]    A user who accepts the consequences can delete an adapter a deployment
    ...    still attaches. The deployment is left in place rather than torn down with it -- a
    ...    running replica keeps serving the weights it already loaded and fails to reload them on
    ...    restart.
    [Tags]    adapters    delete    kubectl
    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    And an AIM deployment attaching the adapter artifact exists in the project
    When the user force-deletes the adapter artifact
    Then the delete should be accepted
    And the adapter artifact should no longer appear in the project list
    And the blocking AIM deployment should still exist
    [Teardown]    Remove blocking AIM deployment for adapter if present
