// Copyright © Advanced Micro Devices, Inc., or its affiliates.

// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';

/** Lifecycle phase of a custom (BYOM) model, sourced from the backend schema. */
export type OnboardPhase = components['schemas']['OnboardPhase'];

/**
 * Runtime values for {@link OnboardPhase}. The generated type is a bare string
 * union, so this mirrors the backend enum for comparisons that would otherwise
 * rely on magic strings. Keying `satisfies` on `Uppercase<OnboardPhase>` makes
 * the set exhaustive: adding a phase to the backend union (and thus a new
 * uppercase key requirement) without adding it here fails the build, and a
 * renamed or dropped phase does the same.
 */
export const OnboardPhase = {
  PENDING: 'Pending',
  IMPORTING: 'Importing',
  READY: 'Ready',
  FAILED: 'Failed',
} as const satisfies Record<Uppercase<OnboardPhase>, OnboardPhase>;

/** Label set on AIMService resources backed by a namespace-scoped fine-tuned AIMModel. */
export const FINE_TUNED_LABEL = 'aiwb.apps.eai.amd.com/fine-tuned';

/** Label set on AIMService resources backed by a namespace-scoped AIMModel (fine-tuned or custom-imported). */
export const NAMESPACE_AIM_MODEL_LABEL =
  'aiwb.apps.eai.amd.com/namespace-aim-model';

/** Metadata stamped on AIMModel CRs by the finetuning pipeline. */
export const AIM_MODEL_NAME_LABEL = 'aiwb.apps.eai.amd.com/model-name';
export const AIM_MODEL_WORKLOAD_ID_LABEL = 'airm.silogen.ai/workload-id';
export const AIM_MODEL_TRAINING_OUTPUT_ANNOTATION =
  'aiwb.apps.eai.amd.com/training-output';

/**
 * Annotation carrying the human-readable description supplied when a fine-tuned
 * model is created. Stamped on the AIMModel CR by the API as
 * `SOURCE_DESCRIPTION_ANNOTATION` (apps/api/aiwb/app/custom_models/constants.py).
 */
export const AIM_MODEL_SOURCE_DESCRIPTION_ANNOTATION =
  'aiwb.apps.eai.amd.com/source-description';

/**
 * Annotation on fine-tuned AIMService CRs carrying the slash-preserved canonical
 * (base model) name — e.g. `meta-llama/Llama-3.2-1B-Instruct`. Annotation rather
 * than label because K8s labels can't contain `/`. Used by the connect modal to
 * render copy-paste-able code samples that match what vLLM is actually serving as.
 */
export const AIM_CANONICAL_NAME_ANNOTATION =
  'aiwb.apps.eai.amd.com/canonical-name';

/**
 * Annotations stamped by the custom-model onboarding flow on AIMModel CRs.
 * Their presence on a catalog AIM marks it as user-imported (rather than a
 * stock AIM published to the cluster), which is what the Custom Models tab
 * filters on.
 *
 * Mirrors the API-side constants in `apps/api/aiwb/app/custom_models/constants.py`,
 * which build these from the default `AIWB_METADATA_PREFIX="aiwb.apps.eai.amd.com"`
 * and `EAI_APPS_METADATA_PREFIX="airm.silogen.ai"` (apps/api/aiwb/app/config.py).
 * Deployments that override either env var must keep the UI prefix in sync.
 */
export const AIM_DISPLAY_NAME_ANNOTATION = 'aiwb.apps.eai.amd.com/display-name';

export const SOURCE_URI_ANNOTATION = 'airm.silogen.ai/source-uri' as const;

/**
 * AimWorkloadStatus: Frontend-friendly deployment status for UI display
 *
 * Purpose: Simplified, high-level status used in the frontend for displaying
 * the deployment state of an AIM in the catalog UI.
 *
 * This status is derived from AIMServiceStatus by mapping Kubernetes states
 * to user-friendly values.
 */
export enum AIMWorkloadStatus {
  DEPLOYED = 'deployed',
  DEGRADED = 'degraded',
  NOT_DEPLOYED = 'not_deployed',
  PENDING = 'pending',
  STARTING = 'starting',
  FAILED = 'failed',
  DELETED = 'deleted',
}

/**
 * AIMStatus: Catalog status of the AIM model/image itself
 *
 * Purpose: Represents the availability and readiness of the AIM model
 * in the cluster catalog (not the deployment status).
 *
 * Values come from the Kubernetes AIMClusterModel CRD status field.
 *
 * This is about the model's availability, not whether it's deployed.
 */
export type AIMStatus = components['schemas']['AIMModelStatus'];

/**
 * AIMServiceStatus: Runtime status of a deployed AIM service instance
 *
 * Purpose: Represents the current state of a running AIM deployment
 * (the AIMService Kubernetes resource).
 *
 * This is about the deployment's runtime state, not the model availability.
 * doc: https://github.com/amd-enterprise-ai/aim-engine/blob/main/docs/docs/concepts/services.md
 */
export type AIMServiceStatus = components['schemas']['AIMServiceStatus'];

export type AcceleratorType = components['schemas']['AcceleratorType'];

/**
 * Complete cluster-scoped AIM resource as returned by the catalog API — the
 * backend `AIMResponse` schema as-is. `spec`/`status` are optional on the wire
 * (the schema defaults them), so consumers read `spec?.image` /
 * `status?.status` defensively. Fine-tuned (namespace-scoped) models use
 * {@link AIMModel}.
 */
export type AIMClusterModel = components['schemas']['AIMResponse'];

/**
 * Project-scoped fine-tuned AIMModel as returned by both the single-item
 * GET /v1/projects/{project}/fine-tuning/models/{model_id} and the list
 * endpoint GET /v1/projects/{project}/fine-tuning/models. Same payload, single
 * type.
 *
 * v1alpha2 imported / re-finetuned models carry their weights under
 * `spec.profiles.overrides.modelSources`; official and fine-tuning-published
 * models use the legacy flat `spec.modelSources`. Read both via
 * `resolveBaseModelSource` (lib/app/aims.ts) rather than reaching into one
 * field directly.
 */
export type AIMModel = components['schemas']['AIMModelResource'];

/**
 * FE-known shape for a single AIMService status condition. The backend types
 * `AIMServiceStatusFields.conditions` as a loose `list[dict[str, Any]]` (no
 * generated schema to point at), so this captures just the fields the UI reads;
 * consumers cast the loose wire array to `AIMServiceCondition[]`.
 */
export type AIMServiceCondition = {
  lastTransitionTime?: string | null;
  message?: string | null;
  observedGeneration?: number | null;
  reason: string;
  status: string;
  type: string;
};

/**
 * AIMService represents a deployed AIM instance — the backend
 * `InferenceDeploymentResponse` schema as-is. Note the wire shape: `spec` and
 * `status` are optional, `id`/`endpoints`/`statusValue`
 * are read-only, `endpoints` is a plain `{ [key]: string }` map, and
 * `status.status` is the {@link AIMServiceStatus} string union.
 * Consumers must guard for the optional/nullable fields.
 */
export type AIMService = components['schemas']['InferenceDeploymentResponse'];

export type ParsedAIM = {
  model: string;
  /**
   * Canonical model architecture identifier (e.g. `CohereLabs/command-a-reasoning-08-2025`).
   * Sourced from the AIM's `status.aimId`; null until the engine has reconciled.
   */
  aimId: string | null;
  imageReference: string;
  annotations: Record<string, string>;
  description: {
    short: string;
    full: string;
  };
  title: string;
  imageVersion: string;
  canonicalName: string;
  tags: string[];
  acceleratorTypes?: AcceleratorType[];
  status: AIMStatus | string;
  workloadStatuses: AIMWorkloadStatus[];
  isPreview: boolean;
  isHfTokenRequired: boolean;
  isLatest?: boolean;
  /**
   * True when the AIM was onboarded by a user via the custom-model import
   * wizard (vs. a stock AIM published to the cluster). Derived from the
   * presence of the {@link MODEL_DISPLAY_NAME_ANNOTATION} or
   * {@link SOURCE_URI_ANNOTATION} on the AIMModel CR. Optional so existing
   * `ParsedAIM` test fixtures don't all need to set it; the parser always
   * populates it.
   */
  isCustomImport?: boolean;
  /** Source URI captured at onboarding (e.g. a Hugging Face URL), when known. */
  sourceUri?: string;
  // Deployment information
  /**
   * @deprecated Use deployedServices instead
   */
  deployedService?: AIMService;
  // Deployment information as one model can be deployed multiple times
  deployedServices?: AIMService[];
};

/**
 * AggregatedAIM represents a model family with multiple versions
 * grouped by their source repository.
 */
export type AggregatedAIM = {
  repository: string;
  parsedAIMs: ParsedAIM[];
  /**
   * Latest official release that is READY, or null when none available.
   * Best default for deployment when non-null.
   */
  latestAim: ParsedAIM | null;
  /**
   * True if at least one version has a 'Ready' status.
   */
  isSupported: boolean;
  /**
   * Counts of deployments for each status.
   */
  deploymentCounts: Record<AIMWorkloadStatus, number>;
  aggregated: {
    title: string;
    aiLabName: string;
    canonicalName: string;
    latestImageVersion: string;
    isHfTokenRequired: boolean;
    /**
     * True when at least one version in the family is user-onboarded.
     * Optional for the same reason as {@link ParsedAIM.isCustomImport};
     * `transformToAggregatedAIMs` always populates it.
     */
    isCustomImport?: boolean;
    tags: string[];
    acceleratorTypes?: AcceleratorType[];
    description: {
      short: string;
      full: string;
    };
    /**
     * Onboarding lifecycle phase for user-imported (BYOM) custom models.
     * Absent for stock AIM catalog models.
     */
    onboardPhase?: OnboardPhase;
    /**
     * Onboard-chosen runtime precision for user-imported (BYOM) custom models,
     * used to seed the deploy drawer's precision default. Absent for stock AIM
     * catalog models and for models onboarded before precision was tracked.
     */
    preferredPrecision?: string;
    /**
     * Number of profile rows the custom model exposes (its Default plus any
     * named profiles), so the card can show a count without a per-model
     * profiles request. Absent for stock AIM catalog models.
     */
    profileCount?: number;
    /**
     * The custom model's Default profile row (selected by its isDefault flag),
     * so the card can summarise the Default without a per-model profiles
     * request. Absent for stock AIM catalog models and until the engine has
     * emitted the Default profile set.
     */
    defaultProfile?: components['schemas']['CustomProfileResponse'];
  };
};

export type AIMDeployPayload = Omit<
  components['schemas']['InferenceDeployRequest'],
  'autoScaling'
> & {
  autoScaling?: AutoscalingPolicyConfig;
};

/**
 * Autoscaling policy payload structure sent to the Kubernetes API.
 *
 * IMPORTANT: Keys must match the CRD-native format exactly because the backend
 * passes this dict through as-is to Kubernetes (dict[str, Any]).
 * - `podmetric` (all lowercase, NOT camelCase)
 * - `metricNames`, `operationOverTime` (standard camelCase)
 * - `target.value` must be string (Go CRD struct expects string)
 */
export type AutoscalingPolicyConfig = {
  metrics: Array<{
    type: 'PodMetric';
    podmetric: {
      metric: {
        backend: 'opentelemetry';
        metricNames: string[];
        query: string;
        operationOverTime: string;
      };
      target: {
        type: string;
        value: string;
      };
    };
  }>;
};

/** Canonical `spec.type` value on AIMClusterProfile/AIMProfile. Only 'optimized' is treated as optimized. */
export const AIM_PROFILE_TYPE_OPTIMIZED = 'optimized' as const;

/**
 * AIMClusterProfile / AIMProfile spec — flat metadata on the profile resource itself.
 * Mirrors the backend `AIMProfileSpec` (see apps/api/aiwb/app/aims/crds.py).
 *
 * Field renames vs. v1alpha1: `gpu` → `acceleratorModel`, `gpuCount` → `acceleratorCount`.
 * New: `acceleratorType` ('gpu' | 'cpu') and `primary` (preferred profile flag).
 */
export type AIMProfileSpec = components['schemas']['AIMProfileSpec'];

export type ModelProfileSummaryFields = {
  metric?: AIMProfileSpec['metric'] | null;
  gpu?: AIMProfileSpec['acceleratorModel'] | null;
  templateGpuCount?: AIMProfileSpec['acceleratorCount'] | null;
  acceleratorType?: AIMProfileSpec['acceleratorType'] | null;
  precision?: AIMProfileSpec['precision'] | null;
  maxLoraRank?: number | null;
  /** Authored profile label, set only for custom-model deployments. */
  profileDisplayName?: string | null;
};

/**
 * Cluster-scoped AIMClusterProfile CRD resource — the backend
 * `AIMProfileResource` schema as-is. `spec`/`status` are optional on the wire;
 * consumers read them defensively.
 * Returned by GET /inference/models/{name}/profiles.
 */
export type AIMClusterProfile = components['schemas']['AIMProfileResource'];

/**
 * Namespace-scoped AIMProfile CRD resource.
 * Returned by GET /projects/{project}/models/{model_name}/profiles.
 */
export type AIMProfile = components['schemas']['AIMProfileResource'];
