// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  AIM_CANONICAL_NAME_ANNOTATION,
  AIM_DISPLAY_NAME_ANNOTATION,
  AIM_MODEL_NAME_LABEL,
  AIMClusterModel,
  AIMModel,
  AIMClusterProfile,
  AutoscalingPolicyConfig,
  SOURCE_URI_ANNOTATION,
} from '@/types/aims';
import { IconCircleCaretRight } from '@tabler/icons-react';
import { Intent, StatusBadgeVariant } from '@amdenterpriseai/types';
import {
  AcceleratorType,
  AIMProfile,
  AIMService,
  AIMServiceStatus,
  AIMWorkloadStatus,
  ParsedAIM,
  AggregatedAIM,
} from '@/types/aims';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import type { components } from '@/types/api';

type EnrichedAIMMetric =
  | components['schemas']['OptimizationMetric']
  | 'default';

type AIMAutoscaling = {
  metricQuery: string;
  operationOverTime: string;
  targetType: string;
  targetValue: number;
};
import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import { fetchAllPages } from './pagination';
import { translationKeyGenerator } from './i18n';

/** AIMModel/AIMClusterModel CRD resource as returned by the fine-tuning endpoints. */
type AIMModelResource = components['schemas']['AIMModelResource'];

// Autoscaling constants
export const AIM_MAX_REPLICAS = 30;

const isAcceleratorType = (value: unknown): value is AcceleratorType =>
  value === 'cpu' || value === 'gpu';

export const getMaxSupportedLoraRank = (
  spec: AIMService['spec'],
): number | undefined => {
  const maxRank = spec?.adapterRuntime?.maxRank;
  return typeof maxRank === 'number' && Number.isFinite(maxRank)
    ? maxRank
    : undefined;
};

/** Base model weights source on an AIMModel, regardless of which spec field carries it. */
type BaseModelSource = { modelId: string; sourceUri: string };

/**
 * Returns the AIMModel source carrying the base model's weights, or null.
 *
 * Mirrors the backend `_resolve_base_model_source`: the legacy flat
 * `spec.modelSources` is populated for official and fine-tuning-published
 * models, while v1alpha2 imported / re-finetuned models carry their weights
 * under `spec.profiles.overrides.modelSources`. Prefer the flat field and fall
 * back to the profiles override.
 *
 * Accepts the `AIMClusterModel | AIMModel` union so `aimParser` can call it for
 * either shape; cluster models carry neither field and resolve to null.
 *
 * TODO: drop the legacy flat `spec.modelSources` branch once all
 * models carry weights under `spec.profiles.overrides.modelSources`.
 */
export const resolveBaseModelSource = (
  aimModel: AIMClusterModel | AIMModel | AIMModelResource,
): BaseModelSource | null => {
  const spec = aimModel.spec;
  const flat = spec?.modelSources?.[0];
  if (flat) return flat;
  const override = spec?.profiles?.overrides?.modelSources?.[0];
  return override ?? null;
};

// Metric keys for vLLM
export const SCALING_METRIC_KEYS = [
  { key: 'vllm:num_requests_running', translationKey: 'runningRequests' },
  { key: 'vllm:num_requests_waiting', translationKey: 'waitingRequests' },
] as const;

// Aggregation option keys (KEDA-supported aggregation policies for autoscaling)
export const AGGREGATION_OPTION_KEYS = [
  { key: 'avg', translationKey: 'avg' },
  { key: 'max', translationKey: 'max' },
  { key: 'min', translationKey: 'min' },
] as const;

// Target type option keys
export const TARGET_TYPE_OPTION_KEYS = [
  { key: 'Value', translationKey: 'value' },
  { key: 'AverageValue', translationKey: 'averageValue' },
] as const;

export const PERFORMANCE_METRIC_KEYS = {
  latency: 'performanceMetrics.values.latency',
  throughput: 'performanceMetrics.values.throughput',
  default: 'performanceMetrics.values.default',
} as const satisfies Record<EnrichedAIMMetric, string>;

export const getMetricTranslationKey = translationKeyGenerator(
  PERFORMANCE_METRIC_KEYS,
  'default',
);

export const DEFAULT_AUTOSCALING: AutoscalingFieldValues = {
  minReplicas: 1,
  maxReplicas: 3,
  metricQuery: 'vllm:num_requests_running',
  operationOverTime: 'avg',
  targetType: 'Value',
  targetValue: 10,
};

export interface AutoscalingFieldValues {
  minReplicas: number;
  maxReplicas: number;
  metricQuery: string;
  operationOverTime: string;
  targetType: string;
  targetValue: number;
}
// We shouldn't do this manually. canonicalName.split('/')[0] is good enough.
const AI_LAB_NAMES: Record<string, string> = {
  'meta-llama': 'Meta',
  mistralai: 'Mistral AI',
  qwen: 'Alibaba Cloud',
  coherelabs: 'Cohere',
  openai: 'OpenAI',
};

/**
 * Resolves canonical name prefix to human-readable AI Lab name.
 * @param canonicalName - The canonical name (e.g., "meta-llama/Llama-3.1-8B")
 * @returns Human-readable AI Lab name (e.g., "Meta")
 */
export const resolveAILabName = (canonicalName: string): string => {
  const prefix = canonicalName.split('/')[0].toLowerCase();
  return AI_LAB_NAMES[prefix] || prefix;
};

export type AIMServiceDisplayInfo = {
  title: string; // Human-readable title (e.g., "Llama 3.1 8B Instruct")
  canonicalName: string; // Canonical name (e.g., "meta-llama/Llama-3.1-8B")
  imageVersion: string; // Image version (e.g., "1.2.3")
  name: string; // Resource name (e.g., "aim-llama-2-7b-v2")
  metric: EnrichedAIMMetric;
  tags?: string[];
};

/**
 * Resolves AIMService display information by combining the service spec with ParsedAIM metadata.
 * Extracts the model title, version, and optimization metric to create a user-friendly display name.
 *
 * @param {AIMService} aimService - The AIMService to resolve display info for.
 * @param {ParsedAIM[] | undefined} parsedAIMs - Optional array of parsed AIMs to match against.
 * @returns {AIMServiceDisplayInfo} Display information with title, version, resource name, metric, and formatted display name.
 */
export const resolveAIMServiceDisplay = (
  aimService: AIMService,
  parsedAIMs?: ParsedAIM[],
): AIMServiceDisplayInfo => {
  const resourceName = aimService.spec?.model?.name;
  const matchingAIM = resourceName
    ? parsedAIMs?.find((aim) => aim.model === resourceName)
    : undefined;
  const modelRef = resourceName;

  const displayName =
    aimService.metadata.annotations?.[AIM_DISPLAY_NAME_ANNOTATION] ||
    (matchingAIM?.model ?? modelRef ?? aimService.metadata.name);
  // The optimization metric is a profile *selector* value
  // (`spec.profile.selector.metric`), set from the deploy request. It is not a
  // profileOverride — that map carries post-selection overrides (GPU count,
  // engine args) and never the metric.
  const selectorMetric = aimService.spec?.profile?.selector?.metric;
  const metric = ['latency', 'throughput'].includes(
    selectorMetric as EnrichedAIMMetric,
  )
    ? (selectorMetric as EnrichedAIMMetric)
    : 'default';

  // Fine-tuned deployments aren't in the cluster catalog; the canonical and
  // user-given name live on AIMService annotations.
  const annotationCanonical =
    aimService.metadata.annotations?.[AIM_CANONICAL_NAME_ANNOTATION];
  const annotationTitle =
    aimService.metadata.annotations?.[AIM_MODEL_NAME_LABEL];

  return {
    title: matchingAIM?.title || annotationTitle || displayName,
    canonicalName:
      matchingAIM?.canonicalName || annotationCanonical || displayName,
    imageVersion: matchingAIM?.imageVersion || '',
    name: displayName,
    metric,
    tags: matchingAIM?.tags || [],
  };
};

/**
 * Maps an AIM Service status to the catalog-level AIMWorkloadStatus
 * used by AIM cards to display deployment state badges.
 */
const mapAIMServiceStatusToAIMWorkloadStatus = (
  status: AIMServiceStatus | undefined,
): AIMWorkloadStatus => {
  switch (status) {
    case 'Running':
      return AIMWorkloadStatus.DEPLOYED;
    case 'Pending':
      return AIMWorkloadStatus.PENDING;
    case 'Starting':
      return AIMWorkloadStatus.STARTING;
    case 'Degraded':
      return AIMWorkloadStatus.DEGRADED;
    case 'Failed':
      return AIMWorkloadStatus.FAILED;
    case 'Deleted':
      return AIMWorkloadStatus.DELETED;
    default:
      return AIMWorkloadStatus.NOT_DEPLOYED;
  }
};

/**
 * Parses an Aim object to extract structured information from its metadata.
 *
 * @param {AIMClusterModel} aim - The aim object to parse.
 * @param {AIMService[] | undefined} deployedServices - Optional array of all deployed services for this AIM (multiple services may share the same model name).
 * @returns {ParsedAIM} The parsed aim data with extracted description, version, tags, and status.
 */
export const aimParser = (
  aim: AIMClusterModel | AIMModel | AIMModelResource,
  deployedServices?: AIMService[],
): ParsedAIM => {
  // Fine-tuned AIMModels carry no spec.image, so status.imageMetadata is absent;
  // every read below tolerates the missing block via optional chaining.
  const imageMetadata = aim.status?.imageMetadata;
  const model = imageMetadata?.model;
  const oci = imageMetadata?.oci;

  // Check if model has a 'preview' tag
  const isPreview = model?.tags?.includes('preview') || false;

  // Fine-tuned AIMModels have no spec.image, so status.imageMetadata is empty.
  // Fall back to authoritative spec/labels so callers don't need to special-case.
  // - canonicalName: the base model id from the resolved weights source
  // - title: the user-given fine-tune name from the model-name label, then metadata.name
  const baseModelId = resolveBaseModelSource(aim)?.modelId;
  const userGivenName = aim.metadata.labels?.[AIM_MODEL_NAME_LABEL];

  const annotations = aim.metadata.annotations ?? {};
  const sourceUri = annotations[SOURCE_URI_ANNOTATION];
  const isCustomImport =
    !!annotations[AIM_DISPLAY_NAME_ANNOTATION] || !!sourceUri;

  const discoveredProfiles = aim.status?.discoveredProfiles ?? null;
  const acceleratorTypes = Array.from(
    new Set(
      (discoveredProfiles?.byHardware ?? [])
        .map((group) => group.acceleratorType?.toLowerCase())
        .filter(isAcceleratorType),
    ),
  ).sort();

  const parsedAim: ParsedAIM = {
    annotations,
    model: aim.metadata.name,
    aimId: aim.status?.aimId ?? null,
    imageReference: aim.spec?.image ?? '',
    description: {
      short: oci?.description || '',
      full: model?.descriptionFull || '',
    },
    imageVersion:
      oci?.version || annotations['aim.eai.amd.com/source-tag'] || '',
    title: model?.title || oci?.title || userGivenName || aim.metadata.name,
    tags: model?.tags || [],
    acceleratorTypes,
    canonicalName: model?.canonicalName || baseModelId || '',
    status: aim.status?.status ?? '',
    workloadStatuses:
      deployedServices && deployedServices.length > 0
        ? deployedServices.map((s) =>
            mapAIMServiceStatusToAIMWorkloadStatus(s.status?.status),
          )
        : [AIMWorkloadStatus.NOT_DEPLOYED],
    isPreview,
    isHfTokenRequired: model?.hfTokenRequired === true,
    isCustomImport,
    sourceUri,
    deployedService: deployedServices?.[0],
    deployedServices,
  };

  return parsedAim;
};

/** Inference capability a deployment's Connect snippet should target. */
export type InferenceCapability = 'chat' | 'transcription';

/**
 * Catalog tag values that mark a model as speech-to-text capable. Mirrors the
 * backend's `TRANSCRIPTION_TAG_VALUES` (apps/api/aiwb/app/aims/constants.py): a
 * model advertising any of these serves `/v1/audio/transcriptions` rather than
 * chat completions. Implementation detail of `getModelCapability`.
 */
const TRANSCRIPTION_TAG_VALUES: readonly string[] = [
  'transcription',
  'speech-to-text',
  'automatic-speech-recognition',
];

/**
 * Derives the inference capability a catalog model exposes from its image
 * metadata tags. Namespace-scoped models (custom-onboarded / fine-tuned) carry
 * no catalog tags, so they fall through to chat — matching the backend, which
 * classifies them as chat by label until their source tags are read separately.
 * Tag matching is exact (case- and separator-sensitive), mirroring the backend.
 */
export const getModelCapability = (
  tags: string[] | undefined,
): InferenceCapability =>
  (tags ?? []).some((tag) => TRANSCRIPTION_TAG_VALUES.includes(tag))
    ? 'transcription'
    : 'chat';

/**
 * OpenAI-compatible request path a deployment serves for the given capability.
 * Shared by the Connect modal and the deployment detail page so the copyable
 * endpoint URL never disagrees with the generated snippet.
 */
export const getInferenceApiPath = (capability: InferenceCapability): string =>
  capability === 'transcription'
    ? '/v1/audio/transcriptions'
    : '/v1/chat/completions';

export const getProjectFineTunedModel = async (
  resourceName: string,
  projectId: string,
): Promise<AIMModel> => {
  if (!resourceName) {
    throw new APIRequestError('No AIM model resource name provided', 422);
  }

  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/fine-tuning/models/{model_id}',
    { params: { path: { project: projectId, model_id: resourceName } } },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch AIM model: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

/**
 * Fetches a single page of cluster-scoped AIMClusterProfile resources. Pass
 * `aimIds` to narrow the result; the backend accepts repeated `?aimId=` query
 * params so multiple aimIds are batched into a single round-trip.
 *
 * This is the single-page primitive — UI consumers walking every page for a given
 * filter should call {@link getAimClusterProfilesByAimIds}.
 */
export const listAimClusterProfilesPage = async (
  page: number,
  pageSize: number,
  options: { aimIds?: string[] } = {},
): Promise<components['schemas']['InferenceProfilesList']> => {
  const { data, error, response } = await apiClient.GET(
    '/api/inference/profiles',
    {
      params: {
        query: { page, pageSize, aimId: options.aimIds?.filter(Boolean) },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch AIM cluster profiles: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

/**
 * Fetches cluster-scoped AIMClusterProfile resources for one or more aimIds,
 * paginated under the hood so the caller gets the full filtered set in a
 * single Promise. Returns `[]` when `aimIds` is empty (no fetch issued) —
 * callers can pass the unique-aimId set derived from displayed services
 * without short-circuiting upstream.
 */
export const getAimClusterProfilesByAimIds = (
  aimIds: string[],
): Promise<AIMClusterProfile[]> => {
  // Drop empties (avoid unfiltered full-catalog fan-out) and dedupe
  // (callers passing repeats inflate the query string and create distinct
  // React Query cache keys for the same logical aimId set).
  const filtered = Array.from(new Set(aimIds.filter(Boolean)));
  if (filtered.length === 0) return Promise.resolve([]);
  return fetchAllPages<AIMClusterProfile>((page, pageSize) =>
    listAimClusterProfilesPage(page, pageSize, { aimIds: filtered }),
  );
};

/**
 * Convenience: cluster profiles for a single aimId. Used by the deploy modal
 * where the AIM is already selected.
 */
export const getAimClusterProfiles = async (
  aimId: string,
): Promise<AIMClusterProfile[]> => {
  if (!aimId) {
    throw new APIRequestError('No aimId provided', 422);
  }
  return getAimClusterProfilesByAimIds([aimId]);
};

/**
 * Fetches a single cluster-scoped AIMClusterProfile by resource name.
 *
 * Calls the targeted `GET /api/inference/profiles/{name}` endpoint — direct
 * K8s GET by `metadata.name`, no listing or aimId derivation. Used when the
 * caller already knows the profile name (typically from
 * `AIMService.status.resolvedProfile.name`).
 *
 * @throws {APIRequestError} 404 when no profile with that name exists.
 */
export const getAimClusterProfileByName = async (
  name: string,
): Promise<AIMClusterProfile> => {
  if (!name) {
    throw new APIRequestError('No profile name provided', 422);
  }
  const { data, error, response } = await apiClient.GET(
    '/api/inference/profiles/{name}',
    { params: { path: { name } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch AIM cluster profile '${name}': ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

/**
 * Fetches a single page of project-scoped AIMProfile resources. Pass
 * `aimIds` to narrow the result (repeated `?aimId=` query params).
 */
export const listProjectAimProfilesPage = async (
  project: string,
  page: number,
  pageSize: number,
  options: { aimIds?: string[] } = {},
): Promise<components['schemas']['InferenceProfilesList']> => {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/profiles',
    {
      params: {
        path: { project },
        query: { page, pageSize, aimId: options.aimIds?.filter(Boolean) },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch project AIM profiles: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

/**
 * Fetches namespace-scoped AIMProfile resources for one or more aimIds,
 * paginated under the hood. Returns `[]` when `aimIds` is empty (no fetch).
 */
export const getProjectAimProfilesByAimIds = (
  project: string,
  aimIds: string[],
): Promise<AIMProfile[]> => {
  // See getAimClusterProfilesByAimIds — drop empties (avoid unfiltered
  // full-catalog fan-out) and dedupe (stable React Query cache keys).
  const filtered = Array.from(new Set(aimIds.filter(Boolean)));
  if (filtered.length === 0) return Promise.resolve([]);
  return fetchAllPages<AIMProfile>((page, pageSize) =>
    listProjectAimProfilesPage(project, page, pageSize, { aimIds: filtered }),
  );
};

/**
 * Convenience: namespace-scoped AIMProfiles for a single aimId.
 */
export const getProjectModelProfiles = async (
  project: string,
  aimId: string,
): Promise<AIMProfile[]> => {
  if (!aimId) {
    throw new APIRequestError('No aimId provided', 422);
  }
  return getProjectAimProfilesByAimIds(project, [aimId]);
};

/**
 * Fetches a single namespace-scoped AIMProfile by resource name.
 *
 * Calls the targeted `GET /api/projects/{project}/profiles/{name}` endpoint —
 * direct K8s GET by `metadata.name`. Used by the AIM detail page for
 * fine-tuned deployments where the profile name is already known from
 * `AIMService.status.resolvedProfile.name`.
 *
 * @throws {APIRequestError} 404 when no profile with that name exists in
 *   the project.
 */
export const getProjectAimProfileByName = async (
  project: string,
  name: string,
): Promise<AIMProfile> => {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }
  if (!name) {
    throw new APIRequestError('No profile name provided', 422);
  }
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/profiles/{name}',
    { params: { path: { project, name } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch project AIM profile '${name}': ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

/**
 * Generates a Kubernetes HPA policy using OpenTelemetry metrics from vLLM.
 *
 * @param {Partial<AIMAutoscaling>} config - Autoscaling configuration parameters
 * @param {string} [config.metricQuery] - OpenTelemetry metric query to monitor (default: 'vllm:num_requests_running')
 * @param {string} [config.operationOverTime] - Aggregation operation for metric values (default: 'avg')
 * @param {string} [config.targetType] - Target type for scaling ('Value', 'AverageValue', or 'Utilization', default: 'Value')
 * @param {number} [config.targetValue] - Target metric value that triggers scaling (default: 10)
 * @returns {AutoscalingPolicyConfig} Kubernetes autoscaling policy configuration
 *
 * @see {@link https://github.com/amd-enterprise-ai/aim-engine/blob/main/docs/docs/guides/scaling-and-autoscaling.md}
 */
export const createAimScalingPolicyConfig = ({
  metricQuery = DEFAULT_AUTOSCALING.metricQuery,
  operationOverTime = DEFAULT_AUTOSCALING.operationOverTime,
  targetType = DEFAULT_AUTOSCALING.targetType,
  targetValue = DEFAULT_AUTOSCALING.targetValue,
}: Partial<AIMAutoscaling> = {}): AutoscalingPolicyConfig => {
  // Keys MUST match CRD-native format exactly because the backend passes
  // this dict through as-is to Kubernetes (dict[str, Any]):
  // - "podmetric" (all lowercase, NOT camelCase — CRD spec)
  // - "metricNames", "operationOverTime" (standard camelCase — CRD spec)
  // - target.value must be string (Go struct expects string, not number)
  return {
    metrics: [
      {
        type: 'PodMetric',
        podmetric: {
          metric: {
            backend: 'opentelemetry',
            metricNames: [
              'vllm:num_requests_running',
              'vllm:num_requests_waiting',
            ],
            query: metricQuery,
            operationOverTime: operationOverTime,
          },
          target: {
            type: targetType,
            value: String(targetValue),
          },
        },
      },
    ],
  };
};

/**
 * Returns status badge variants for AIM service statuses with localized labels.
 * Maps each AIMServiceStatus to its corresponding display properties (label, intent, color, icon).
 *
 * @param t - Translation function to localize status labels
 * @returns A mapping of AIMServiceStatus values to their display variants
 */
export const getAIMServiceStatusVariants = (
  t: (key: string) => string,
): Record<AIMServiceStatus, StatusBadgeVariant> => ({
  Pending: {
    label: t('models:status.pending'),
    intent: Intent.PENDING,
  },
  Degraded: {
    label: t('models:status.degraded'),
    intent: Intent.WARNING,
  },
  Running: {
    label: t('models:status.running'),
    color: 'primary',
    icon: IconCircleCaretRight,
  },
  Failed: {
    label: t('models:status.failed'),
    intent: Intent.DANGER,
  },
  Starting: {
    label: t('models:status.starting'),
    intent: Intent.PENDING,
  },
  Deleted: {
    label: t('models:status.deleted'),
    intent: Intent.DANGER,
  },
});

/**
 * Maps an AIM service status onto the workload wire contract, which has no
 * `Degraded` state (an AIM-service-only status folded to `Unknown` here). Used
 * by the chat workload builder, whose synthetic workloads are wire-typed. The
 * deployed-models table keeps a local mapper instead, to preserve `Degraded`.
 */
export const mapAIMServiceStatusToWorkloadWireStatus = (
  status: AIMServiceStatus | undefined,
): components['schemas']['WorkloadStatus'] => {
  switch (status) {
    case 'Pending':
      return 'Pending';
    case 'Starting':
      return 'Starting';
    case 'Running':
      return 'Running';
    case 'Failed':
      return 'Failed';
    default:
      return 'Unknown';
  }
};

/**
 * Transforms aggregated AIMs into an array of AggregatedAIM objects.
 * Sorts versions by image version (descending) and computes aggregated properties.
 *
 * @param {ParsedAIM[] | undefined} aims - Optional array of parsed AIMs to aggregate.
 * @returns {AggregatedAIM[]} An array of aggregated AIMs.
 */
export const transformToAggregatedAIMs = (
  aims?: ParsedAIM[],
): AggregatedAIM[] => {
  if (!aims) {
    return [];
  }

  const aggregated = aims.reduce(
    (result, aim) => {
      // Use the repository as the key to aggregate the AIMs
      const key = aim.annotations['aim.eai.amd.com/source-repository'];

      if (!result[key]) {
        result[key] = [];
      }

      result[key].push(aim);

      return result;
    },
    {} as Record<string, ParsedAIM[]>,
  );

  // Convert `major.minor.patch` to a sortable number; ignore suffixes like `-preview-3` or `+build.1`.
  const versionStringToNumber = (v: string) => {
    const m = v.match(/(\d+)\.(\d+)\.(\d+)/);
    if (!m) return 0;
    return Number(`${m[1]}${m[2].padStart(3, '0')}${m[3].padStart(3, '0')}`);
  };

  // Match official versions like `1.2.3` or `v1.2.3`, and allow optional `+build` metadata.
  // Any prerelease suffix (for example `-preview`, `-beta`, `-rc`) is excluded.
  const officialReleaseRegex = /^v?\d+\.\d+\.\d+(\+[0-9A-Za-z.-]+)?$/;

  const result = Object.entries(aggregated).map(([repository, aims]) => {
    // Sort aims by imageVersion in descending order (latest first)
    const sortedAims = [...aims].sort((a, b) => {
      return (
        versionStringToNumber(b.imageVersion) -
        versionStringToNumber(a.imageVersion)
      );
    });

    const latestAim =
      sortedAims.find(
        (aim) =>
          officialReleaseRegex.test(aim.imageVersion.trim()) &&
          aim.status === 'Ready',
      ) ?? null;

    const metaSource = latestAim ?? sortedAims[0];
    const { title, canonicalName, imageVersion, description, tags } =
      metaSource;

    let isHfTokenRequired = false;
    let isCustomImport = false;
    let isSupported = false;
    const acceleratorTypeSet = new Set<AcceleratorType>();
    const deploymentCounts: Record<AIMWorkloadStatus, number> = {
      [AIMWorkloadStatus.DEPLOYED]: 0,
      [AIMWorkloadStatus.DEGRADED]: 0,
      [AIMWorkloadStatus.PENDING]: 0,
      [AIMWorkloadStatus.STARTING]: 0,
      [AIMWorkloadStatus.FAILED]: 0,
      [AIMWorkloadStatus.NOT_DEPLOYED]: 0,
      [AIMWorkloadStatus.DELETED]: 0,
    };

    sortedAims.forEach((aim) => {
      // Counting the number of deployments for each status.
      aim.workloadStatuses.forEach((status) => {
        deploymentCounts[status]++;
      });

      aim.isLatest =
        latestAim !== null && aim.imageVersion === latestAim.imageVersion;

      // Check whether it requires hf token
      isHfTokenRequired = isHfTokenRequired || aim.isHfTokenRequired;

      // Mark the family as custom-imported if any version was onboarded by a user.
      isCustomImport = isCustomImport || aim.isCustomImport === true;

      // At least one version with Ready status makes the model supported
      isSupported = isSupported || aim.status === 'Ready';

      aim.acceleratorTypes?.forEach((type) => {
        acceleratorTypeSet.add(type);
      });
    });

    return {
      repository,
      parsedAIMs: sortedAims,
      latestAim,
      isSupported,
      deploymentCounts,
      aggregated: {
        title,
        aiLabName: resolveAILabName(canonicalName),
        canonicalName,
        latestImageVersion: imageVersion,
        isHfTokenRequired,
        isCustomImport,
        tags,
        acceleratorTypes: Array.from(acceleratorTypeSet).sort(),
        description: {
          short: description.short,
          full: description.full,
        },
      },
    };
  });

  // Supported models appear first, unsupported last
  result.sort((a, b) => Number(b.isSupported) - Number(a.isSupported));
  return result;
};

/**
 * Filters the catalog while preserving every family-level aggregate.
 *
 * Accelerator filters operate on individual ParsedAIM versions. Re-aggregating
 * the filtered subset would recompute family-level state (support status,
 * deployment counts, ordering) from whatever versions survived the filter — so a
 * family whose only Ready or only deployed version is hidden would lose its
 * supported flag, drop its "Has deployments" count, and get reshuffled within the
 * supported group. The filter should only decide which families are visible, not
 * mutate their canonical state. We therefore aggregate the full catalog once and
 * keep the families whose repository still has at least one version after filtering.
 */
export const buildFilteredCatalog = (
  allAims: ParsedAIM[],
  filteredAims: ParsedAIM[],
): AggregatedAIM[] => {
  const visibleRepos = new Set(
    filteredAims.map((a) => a.annotations['aim.eai.amd.com/source-repository']),
  );
  return transformToAggregatedAIMs(allAims).filter((family) =>
    visibleRepos.has(family.repository),
  );
};
