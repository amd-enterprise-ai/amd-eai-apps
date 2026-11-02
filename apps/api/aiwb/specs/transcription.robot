# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       End-to-end coverage for the catalog speech-to-text (STT) flow: deploy a
...                 published Whisper-style AIM from the catalog, confirm it is discoverable as
...                 a transcription capability, and exercise the audio transcription and
...                 translation endpoints through the gateway. Verifies Stream A end-to-end.
...
...                 Requires a transcription-tagged AIM image in the cluster catalog. Where none
...                 is published the scenarios skip (the model selector skips, and the whole suite
...                 is gated by needs-aim-images), so a cluster without a Whisper AIM reports
...                 skipped rather than failing.
Resource            resources/aiwb_transcription.resource
Resource            resources/aiwb_aims.resource
Resource            resources/airm_keywords.resource
Resource            resources/airm_projects.resource
Suite Teardown      Clean Up All Tracked Resources
Test Tags           aims    transcription    gpu    needs-aim-images


*** Test Cases ***
Catalog speech-to-text deployment is discoverable as a transcription capability
    [Documentation]    A deployed catalog Whisper AIM is surfaced by the inference list filtered
    ...    to capability=transcription.
    Given a ready project with user access exists
    And a transcription-capable AIM exists in the catalog
    And the project has GPU quota available
    And the transcription AIM is deployed and running with an API key
    When transcription-capable AIM services are listed
    Then response status should be 200
    And the running AIM should appear in the transcription list

Catalog speech-to-text deployment transcribes audio to text
    [Documentation]    Uploading audio to /v1/audio/transcriptions on the deployment returns text.
    Given a ready project with user access exists
    And a transcription-capable AIM exists in the catalog
    And the project has GPU quota available
    And the transcription AIM is deployed and running with an API key
    When audio is transcribed via the external endpoint
    Then the transcription response should return text

Catalog speech-to-text deployment translates audio to English
    [Documentation]    Uploading audio to /v1/audio/translations on the deployment returns text.
    Given a ready project with user access exists
    And a transcription-capable AIM exists in the catalog
    And the project has GPU quota available
    And the transcription AIM is deployed and running with an API key
    When audio is translated to English via the external endpoint
    Then the translation response should return text
