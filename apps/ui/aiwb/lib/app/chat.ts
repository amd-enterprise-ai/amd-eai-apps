// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  AIM_DISPLAY_NAME_ANNOTATION,
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
  ParsedAIM,
} from '@/types/aims';
import type { Workload } from '@/types/workloads';
import { APIRequestError, getErrorMessage } from '@amdenterpriseai/utils/app';
import {
  aimParser,
  getAimClusterProfilesByAimIds,
  getProjectAimProfilesByAimIds,
  mapAIMServiceStatusToWorkloadWireStatus,
  resolveAIMServiceDisplay,
} from './aims';
import {
  customModelNamesFromServices,
  resolveCustomProfileDeployments,
} from './custom-profiles';
import { getInferenceModel, listAllInferenceDeployments } from './inference';
import { listAllProjectFineTunedModels } from './models';
import { toProfileSummaryFields } from '@/components/shared/ModelProfileSummary';
import type { AIMProfileSpec } from '@/types/aims';
import { resolveModelDeploymentName } from './modelDeploymentDisplay';

export type WorkloadDisplayInfo = {
  imageVersion: string;
  metric: string;
  tags: string[];
  gpu?: string | null;
  templateGpuCount?: number | null;
  acceleratorType?: string | null;
  precision?: string | null;
  /** Authored profile label, set only for custom-model deployments. */
  profileDisplayName?: string | null;
};

export type ChattableWorkloadsResult = {
  workloads: Workload[];
  workloadDisplayInfo: Record<string, WorkloadDisplayInfo>;
};

export const listChattableWorkloads = async (
  projectId: string,
): Promise<ChattableWorkloadsResult> => {
  if (!projectId) {
    throw new APIRequestError(`No project selected`, 422);
  }

  // The legacy /chattable endpoint that combined chattable AIM services + fine-tuning
  // workloads was removed when inference was split into its own capability.
  // The new equivalent is GET /v1/projects/{project}/inference?capability=chat,
  // which returns chat-ready AIM services only. Pre-deployment fine-tuning workloads
  // are no longer surfaced here — once finished and deployed they appear via inference.
  const aimServices = await listAllInferenceDeployments(projectId, {
    capability: 'chat',
  });

  // Best-effort fetch of cluster-catalog models to resolve display names.
  // Namespace-scoped AIMModel services (fine-tuned and custom-imported) aren't
  // in the cluster catalog, so we skip those names and rely on
  // resolveAIMServiceDisplay's annotation fallback instead. Per-name 404/error
  // responses are tolerated (allSettled) so a single bad name doesn't blank
  // every row.
  const clusterAimNames = Array.from(
    new Set(
      aimServices
        .filter(
          (s) =>
            s.metadata.labels?.[FINE_TUNED_LABEL] !== 'true' &&
            s.metadata.labels?.[NAMESPACE_AIM_MODEL_LABEL] !== 'true',
        )
        .map((s) => s.spec?.model?.name)
        .filter((name): name is string => !!name),
    ),
  );
  const settled = await Promise.allSettled(
    clusterAimNames.map((name) => getInferenceModel(name)),
  );
  const parsedAIMs: ParsedAIM[] = settled
    .filter(
      (
        r,
      ): r is PromiseFulfilledResult<
        Awaited<ReturnType<typeof getInferenceModel>>
      > => r.status === 'fulfilled',
    )
    .map((r) => aimParser(r.value));

  const workloadDisplayInfo: Record<string, WorkloadDisplayInfo> = {};
  const chattableWorkloads: Workload[] = aimServices.map((s) => {
    const displayInfo = resolveAIMServiceDisplay(s, parsedAIMs);
    const modelRef = s.status?.resolvedModel?.name;
    const isFineTuned = s.metadata.labels?.[FINE_TUNED_LABEL] === 'true';
    const isNamespaceModel =
      s.metadata.labels?.[NAMESPACE_AIM_MODEL_LABEL] === 'true';
    const deployDisplayName =
      s.metadata.annotations?.[AIM_DISPLAY_NAME_ANNOTATION];
    const baseFallback = modelRef || s.metadata.name;
    let displayName: string;
    if (isFineTuned) {
      // Prefer the user-entered deploy name; displayInfo.title resolves to the
      // base model name for fine-tuned services, so fall back to it only when
      // no deploy name was set.
      displayName =
        deployDisplayName && deployDisplayName !== s.metadata.name
          ? deployDisplayName
          : displayInfo.title || baseFallback;
    } else if (isNamespaceModel && deployDisplayName) {
      displayName = deployDisplayName;
    } else {
      displayName = resolveModelDeploymentName({
        displayName: deployDisplayName ?? s.metadata.name,
        resourceName: s.metadata.name,
        canonicalName: displayInfo.canonicalName,
      });
    }
    workloadDisplayInfo[s.id as string] = {
      imageVersion: displayInfo.imageVersion,
      metric: displayInfo.metric,
      tags: displayInfo.tags ?? [],
    };
    return {
      id: s.id as string,
      type: 'INFERENCE',
      name: modelRef || s.metadata.name,
      displayName,
      createdBy: '',
      updatedBy: null,
      namespace: '',
      description: null,
      endpoints: {},
      createdAt: s.metadata.creationTimestamp ?? '',
      updatedAt: s.metadata.creationTimestamp ?? '',
      status: mapAIMServiceStatusToWorkloadWireStatus(s.status?.status),
    };
  });

  // Join profile specs from the cluster + project AIMProfile catalogs by
  // status.resolvedProfile.name (the engine writes only the name;
  // AIWB no longer enriches the service response with the spec). aimIds
  // come straight off the v1alpha2 `status.aimId` of the per-name cluster
  // models and fine-tuned AIMModel CRs.
  const profileSpecByName = new Map<string, AIMProfileSpec>();
  try {
    const fineTunedModels = await listAllProjectFineTunedModels(projectId);
    const clusterAimIds = parsedAIMs
      .map((p) => p.aimId)
      .filter((id): id is string => !!id);
    const namespaceAimIds = fineTunedModels
      .map((m) => m.status?.aimId)
      .filter((id): id is string => !!id);
    const [clusterProfiles, projectProfiles] = await Promise.all([
      getAimClusterProfilesByAimIds(clusterAimIds),
      getProjectAimProfilesByAimIds(projectId, namespaceAimIds),
    ]);
    for (const p of clusterProfiles) {
      if (p.metadata.name && p.spec)
        profileSpecByName.set(p.metadata.name, p.spec);
    }
    for (const p of projectProfiles) {
      if (p.metadata.name && p.spec)
        profileSpecByName.set(p.metadata.name, p.spec);
    }
  } catch (error) {
    console.warn('Failed to fetch profile catalogs for chat display:', error);
  }

  // The dropdown names a custom model's profile rather than describing its
  // hardware, because that label is what distinguishes two deployments of the
  // same model. It comes from the per-model profiles endpoint, which the catalog
  // join above cannot supply.
  const customProfileByServiceId = await resolveCustomProfileDeployments(
    projectId,
    customModelNamesFromServices(aimServices),
  );

  for (const s of aimServices) {
    const id = s.id as string;
    const existing = workloadDisplayInfo[id];
    if (!existing) continue;
    const customProfile = customProfileByServiceId.get(id);
    if (customProfile) {
      workloadDisplayInfo[id] = {
        ...existing,
        profileDisplayName: customProfile.displayName,
      };
      continue;
    }
    const profile = toProfileSummaryFields(s, profileSpecByName);
    if (!profile) continue;
    workloadDisplayInfo[id] = {
      ...existing,
      ...(profile.metric != null && profile.metric !== ''
        ? { metric: profile.metric }
        : {}),
      ...(profile.gpu != null && profile.gpu !== ''
        ? { gpu: profile.gpu }
        : {}),
      ...(profile.templateGpuCount != null
        ? { templateGpuCount: profile.templateGpuCount }
        : {}),
      ...(profile.acceleratorType != null
        ? { acceleratorType: profile.acceleratorType }
        : {}),
      ...(profile.precision != null && profile.precision !== ''
        ? { precision: profile.precision }
        : {}),
    };
  }

  // The chattable API can include AIM services still starting or legacy workloads
  // that are not ready to chat; keep only what ChatView can use.
  const readyToChatWorkloads = chattableWorkloads.filter(
    (w) => w.status === 'Running' && w.type === 'INFERENCE' && !!w.id,
  );

  return {
    workloads: readyToChatWorkloads,
    workloadDisplayInfo,
  };
};

import { ChatBody } from '@/types/chat';
import { INFERENCE_CHUNK_DELIMITER, InferenceChunk } from '@/types/chat';
import { MutableRefObject } from 'react';
import { useSystemToast } from '@amdenterpriseai/hooks';

export const streamChatResponse = async (
  aimServiceId: string,
  chatBody: ChatBody,
  projectId: string,
  stopConversationRef: MutableRefObject<boolean>,
) => {
  const { toast } = useSystemToast();

  const chatController = new AbortController();
  const data = await sendChatRequest(
    aimServiceId,
    chatBody,
    projectId,
    chatController,
  );

  if (!data) {
    toast.error('No response received');
    throw new Error('No response received from chat request');
  }
  const decoder = new TextDecoder();

  let resolveContextPromise: (arg: any) => void;
  const chatContextPromise = new Promise<any>((resolve, _reject) => {
    resolveContextPromise = resolve;
  });

  let context = {};
  const responseStream = new ReadableStream({
    async start(controller) {
      let done = false;
      const reader = data.getReader();
      let currentChunk = '';
      while (!done) {
        if (stopConversationRef.current === true) {
          chatController.abort();
          done = true;
          break;
        }
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        if (value) {
          const decoded = decoder.decode(value);
          const chunks = decoded
            .split(INFERENCE_CHUNK_DELIMITER)
            .filter((c) => c !== '');
          for (const chunk of chunks) {
            let chunkValue: InferenceChunk;
            currentChunk += chunk;
            try {
              chunkValue = JSON.parse(currentChunk) as InferenceChunk;
            } catch (error) {
              continue;
            }
            currentChunk = '';

            if (chunkValue.content) {
              controller.enqueue(chunkValue.content);
            }
            if (chunkValue.context) {
              context = { ...context, ...chunkValue.context };
            }
          }
        }
      }
      controller.close();
      resolveContextPromise(Object.keys(context).length ? context : undefined);
    },
  });

  return {
    responseStream,
    context: chatContextPromise,
  };
};

export const sendChatRequest = async (
  aimServiceId: string,
  chatBody: ChatBody,
  projectId: string,
  chatController: AbortController,
) => {
  const body = JSON.stringify(chatBody);

  // Workload chat was removed with the workloads router cleanup;
  // AIM service chat moved off the AIWB backend onto the UI-side bypass,
  // so every chat now goes through /api/ui/projects/.../chat.
  // The bypass calls GET /v1/projects/{project}/inference/{id} to resolve
  // the AIM internal URL, so this id must be an AIM service id — a raw
  // workload-table id would 404 there.
  const response = await fetch(
    `/api/ui/projects/${projectId}/inference/${aimServiceId}/chat`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      signal: chatController.signal,
      body,
    },
  );

  if (!response.ok) {
    const errorMessage = await getErrorMessage(response);
    throw new APIRequestError(
      `Failed to send chat request: ${errorMessage}`,
      response.status,
    );
  }
  return response.body;
};
