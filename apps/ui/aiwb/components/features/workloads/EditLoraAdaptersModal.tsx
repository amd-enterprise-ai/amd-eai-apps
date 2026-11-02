// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ActionButton, Modal } from '@amdenterpriseai/components';
import { useSystemToast } from '@amdenterpriseai/hooks';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'next-i18next';

import { LoraAdapterSelectionTable } from '@/components/features/loras/LoraAdapterSelectionTable';
import { getMaxSupportedLoraRank } from '@/lib/app/aims';
import { isAdapterCapableProfileSpec } from '@/lib/app/aims/adapterCompatibility';
import {
  getDeploymentModelKind,
  resolveDeploymentAimId,
} from '@/lib/app/deployment-model';
import {
  invalidateAdapterQueries,
  updateInferenceAdapters,
} from '@/lib/app/inference';
import { listAllAdapterArtifacts } from '@/lib/app/artifacts';
import { type AIMProfileSpec, type AIMService } from '@/types/aims';

type EditLoraAdaptersModalProps = {
  deployment: AIMService;
  namespace: string;
  /** Spec of the profile the deployment resolved to; owns adapter eligibility. */
  resolvedProfileSpec: AIMProfileSpec | null | undefined;
  /** Whether the profile spec is still in flight. */
  isResolvedProfileLoading?: boolean;
  /** Whether fetching the profile spec failed. */
  isResolvedProfileError?: boolean;
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  onSuccess?: () => void;
};

export const EditLoraAdaptersModal = ({
  deployment,
  namespace,
  resolvedProfileSpec,
  isResolvedProfileLoading = false,
  isResolvedProfileError = false,
  isOpen,
  onOpenChange,
  onSuccess,
}: EditLoraAdaptersModalProps) => {
  const { t } = useTranslation('workloads');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();
  const [selectedNames, setSelectedNames] = useState<string[]>([]);
  const wasOpen = useRef(false);
  const attachedNames = useMemo(
    () => deployment.spec?.adapters?.map((adapter) => adapter.name) ?? [],
    [deployment.spec?.adapters],
  );
  // `deployment.id` is the API's own name for the workload-id label the artifacts
  // endpoint resolves against; re-deriving it from the label here would break
  // wherever the platform runs under a non-default metadata prefix.
  const deploymentId = deployment.id ?? undefined;
  const maxRank = getMaxSupportedLoraRank(deployment.spec);
  const {
    data: adapters = [],
    isLoading: areAdaptersLoading,
    isError: isAdaptersError,
  } = useQuery({
    queryKey: ['project', namespace, 'artifacts', deploymentId],
    queryFn: () => listAllAdapterArtifacts(namespace, deploymentId),
    enabled: isOpen,
  });
  const {
    data: modelAimId,
    isLoading: isModelLoading,
    isError: isModelError,
  } = useQuery({
    queryKey: [
      'lora-editor-model',
      namespace,
      deployment.spec?.model?.name,
      getDeploymentModelKind(deployment.metadata.labels ?? {}),
    ],
    queryFn: () => resolveDeploymentAimId(namespace, deployment),
    enabled: isOpen && !!deployment.spec?.model?.name,
  });
  // Everything the deployment's rank budget and the adapter's own readiness
  // allow; whether the running profile can actually serve them is a separate
  // verdict the artifacts API owns.
  const candidateAdapters = useMemo(
    () =>
      adapters.filter(
        (adapter) =>
          adapter.readiness === 'Ready' &&
          adapter.rank != null &&
          maxRank != null &&
          adapter.rank <= maxRank,
      ),
    [adapters, maxRank],
  );
  const eligibleAdapters = useMemo(
    () => candidateAdapters.filter((adapter) => adapter.servable === true),
    [candidateAdapters],
  );
  // `servable` has three states and the third is not a rejection: the API
  // answers null when it could not resolve the deployment's current serving
  // profile, which says nothing about the adapter itself. Leaving such a row
  // out of the offer costs nothing, but doing the same to one the user has
  // already attached turns an unanswered question into a removal — an untouched
  // Apply would submit the detachment, unasked for and unannounced. An unknown
  // verdict over an attachment is unresolved eligibility, and gates the action
  // the way a still-loading lookup does.
  const unresolvedAttachedNames = useMemo(
    () =>
      new Set(
        candidateAdapters
          .filter(
            (adapter) =>
              adapter.servable == null && attachedNames.includes(adapter.name),
          )
          .map((adapter) => adapter.name),
      ),
    [attachedNames, candidateAdapters],
  );
  const isServabilityUnknown = unresolvedAttachedNames.size > 0;
  // `candidateAdapters` answers "what may be offered", and readiness is one of
  // its terms — so an attachment whose weights are still importing, or whose
  // readiness could not be checked, never reached the guard above and was
  // dropped from every set below, including the one Apply submits. Closing the
  // servability route alone left this one open onto the same detachment.
  //
  // Readiness is not a verdict about this pairing the way the rank budget is:
  // it is transient, and an unknown reading is an unanswered question rather
  // than a no. Neither may decide a detachment on the user's behalf, so such an
  // attachment is listed and stays checked. Rank is deliberately not consulted
  // here — an adapter still importing has no trustworthy rank yet, and letting
  // an absent one condemn it would reinstate the loss by a third route.
  const unreadyAttachedNames = useMemo(
    () =>
      new Set(
        adapters
          .filter(
            (adapter) =>
              adapter.readiness !== 'Ready' &&
              attachedNames.includes(adapter.name),
          )
          .map((adapter) => adapter.name),
      ),
    [adapters, attachedNames],
  );
  // Without the resolved profile's spec the modal cannot tell an ineligible
  // adapter from an undetermined one, so it is as much a precondition for
  // listing adapters as the deployed model's identity.
  //
  // The profile spec is fetched by the page, whose loading gate does not cover
  // that query, so the modal can be opened while the spec is still in flight or
  // after the fetch failed. Neither means the model's identity is unresolvable,
  // and three outcomes need telling apart: still arriving, failed to arrive, and
  // arrived to say there is nothing to resolve. Collapsing them made the modal
  // claim the identity could not be resolved while it was merely still loading,
  // and claim it permanently whenever that fetch errored.
  //
  // A model lookup that succeeded without yielding an aimId names nothing the
  // adapter list can be trusted against, so it belongs with the spec that
  // resolved to nothing rather than with the two transport outcomes above.
  const isEligibilityPending = isModelLoading || isResolvedProfileLoading;
  const isEligibilityUnreadable =
    !isEligibilityPending && (isModelError || isResolvedProfileError);
  const isModelUnresolved =
    !isEligibilityPending &&
    !isEligibilityUnreadable &&
    (!modelAimId || !resolvedProfileSpec);
  const isModelUnavailable = isEligibilityUnreadable || isModelUnresolved;
  // A profile can arrive intact and still be unable to host an adapter: its
  // runtime may not advertise the capability at all, or it may name no weights
  // lineage for an adapter to be matched against. Either way the eligibility
  // predicate rejects every adapter, which is indistinguishable from "nothing
  // matches" — yet the model is perfectly resolved, so the guards above stay
  // false and Apply would submit an empty list over whatever is attached.
  //
  // Unlike the lookup states above this is a stable property of the profile the
  // deployment is running, not something that resolves by waiting or retrying,
  // so it is named to the user rather than shown as an empty table.
  const isProfileAdapterIncapable =
    !isEligibilityPending &&
    !isEligibilityUnreadable &&
    !isModelUnresolved &&
    !isAdapterCapableProfileSpec(resolvedProfileSpec);
  const isProfileWeightsUnknown =
    !isEligibilityPending &&
    !isEligibilityUnreadable &&
    !isModelUnresolved &&
    !isProfileAdapterIncapable &&
    !resolvedProfileSpec?.modelId &&
    !resolvedProfileSpec?.aimId;
  const cannotServeAdapters =
    isProfileAdapterIncapable || isProfileWeightsUnknown;
  // An attachment whose verdict is unknown stays on screen and stays checked:
  // hiding it would read as "already detached" for a decision nobody has made.
  const eligibleNames = useMemo(
    () => new Set(eligibleAdapters.map((adapter) => adapter.name)),
    [eligibleAdapters],
  );
  // Drawn from the full list rather than from the candidates, so an attachment
  // the candidate filter excluded is still on screen to be seen and cleared.
  const listedAdapters = adapters.filter(
    (adapter) =>
      eligibleNames.has(adapter.name) ||
      unresolvedAttachedNames.has(adapter.name) ||
      unreadyAttachedNames.has(adapter.name),
  );
  const ineligibleAttachedNames = useMemo(() => {
    if (
      areAdaptersLoading ||
      isAdaptersError ||
      isModelLoading ||
      !modelAimId ||
      !resolvedProfileSpec ||
      cannotServeAdapters ||
      isServabilityUnknown ||
      maxRank == null
    )
      return [];
    // An unready attachment is not "no longer eligible" — it is not yet
    // judged, and Apply is gated on it below, so promising its detachment here
    // would announce a removal that cannot currently happen.
    return attachedNames.filter(
      (name) => !eligibleNames.has(name) && !unreadyAttachedNames.has(name),
    );
  }, [
    areAdaptersLoading,
    attachedNames,
    cannotServeAdapters,
    eligibleNames,
    isAdaptersError,
    isModelLoading,
    isServabilityUnknown,
    maxRank,
    modelAimId,
    resolvedProfileSpec,
    unreadyAttachedNames,
  ]);

  // Until eligibility has been established the eligible set is empty, so the
  // filter below reduces an untouched selection to nothing and the submission
  // reads as "detach everything" rather than as "unchanged". Applying in that
  // window silently drops the user's attached adapters, so a pending lookup
  // disables the action for the same reason an unavailable one does.
  //
  // The table only renders eligible adapters, so a name a user never toggled
  // (including an initially-attached but now ineligible one) can still be
  // sitting in selectedNames. Strip anything outside the eligible set before
  // submitting so the warning below ("will be detached") is actually true.
  const submittedNames = selectedNames.filter((name) =>
    eligibleNames.has(name),
  );
  // Gating on the selection rather than on the attachment is what the table's
  // own `selection.notReady` copy already promises: the row stays visible and
  // stays checked, and clearing it is how the user says the detachment is
  // meant. So an untouched Apply cannot remove it, while a deliberate one —
  // including clearing every row — still can.
  const retainedUnreadyNames = selectedNames.filter((name) =>
    unreadyAttachedNames.has(name),
  );
  const hasRetainedUnreadyAttachments = retainedUnreadyNames.length > 0;
  const isSelectionUnchanged =
    submittedNames.length === attachedNames.length &&
    submittedNames.every((name) => attachedNames.includes(name));
  useEffect(() => {
    if (isOpen && !wasOpen.current) setSelectedNames(attachedNames);
    wasOpen.current = isOpen;
  }, [attachedNames, isOpen]);

  const updateMutation = useMutation({
    mutationFn: (names: string[]) =>
      updateInferenceAdapters(namespace, deployment.id!, names),
    onSuccess: async () => {
      await invalidateAdapterQueries(queryClient, namespace);
      onSuccess?.();
      toast.success(t('details.loraAdapters.edit.success'));
      onOpenChange(false);
    },
    onError: () => {
      toast.error(t('details.loraAdapters.edit.error'));
    },
  });

  const handleClose = () => {
    if (!updateMutation.isPending) onOpenChange(false);
  };

  if (!isOpen) return null;

  return (
    <Modal
      title={t('details.loraAdapters.edit.title')}
      size="lg"
      onClose={handleClose}
      footer={
        <>
          <ActionButton secondary onPress={handleClose}>
            {t('details.loraAdapters.edit.cancel')}
          </ActionButton>
          <ActionButton
            primary
            data-testid="apply-lora-adapters-button"
            isLoading={updateMutation.isPending}
            isDisabled={
              areAdaptersLoading ||
              isAdaptersError ||
              isEligibilityPending ||
              isModelUnavailable ||
              cannotServeAdapters ||
              isServabilityUnknown ||
              hasRetainedUnreadyAttachments ||
              isSelectionUnchanged
            }
            onPress={() => updateMutation.mutate(submittedNames)}
          >
            {t('details.loraAdapters.edit.apply')}
          </ActionButton>
        </>
      }
    >
      <div className="space-y-4" data-testid="edit-lora-adapters-modal">
        <p className="text-sm text-muted">
          {t('details.loraAdapters.edit.description', { rank: maxRank })}
        </p>
        {isEligibilityUnreadable ? (
          <p className="text-sm text-danger">
            {t('details.loraAdapters.edit.modelUnreadable')}
          </p>
        ) : null}
        {isModelUnresolved ? (
          <p className="text-sm text-danger">
            {t('details.loraAdapters.edit.modelUnavailable')}
          </p>
        ) : null}
        {isProfileAdapterIncapable ? (
          <p className="text-sm text-warning" data-testid="profile-no-adapters">
            {t('details.loraAdapters.edit.profileCannotServeAdapters')}
          </p>
        ) : null}
        {isProfileWeightsUnknown ? (
          <p
            className="text-sm text-warning"
            data-testid="profile-weights-unknown"
          >
            {t('details.loraAdapters.edit.profileWeightsUnknown')}
          </p>
        ) : null}
        {isServabilityUnknown ? (
          <p className="text-sm text-warning" data-testid="servability-unknown">
            {t('details.loraAdapters.edit.servabilityUnknown')}
          </p>
        ) : null}
        {hasRetainedUnreadyAttachments ? (
          <p
            className="text-sm text-warning"
            data-testid="attachments-not-ready"
          >
            {t('details.loraAdapters.edit.attachmentsNotReady', {
              names: retainedUnreadyNames.join(', '),
            })}
          </p>
        ) : null}
        {ineligibleAttachedNames.length > 0 ? (
          <p className="text-sm text-warning">
            {t('details.loraAdapters.edit.willDetach', {
              names: ineligibleAttachedNames.join(', '),
            })}
          </p>
        ) : null}
        {cannotServeAdapters ? null : (
          <LoraAdapterSelectionTable
            adapters={listedAdapters}
            isLoading={areAdaptersLoading || isEligibilityPending}
            selectedNames={selectedNames}
            onSelectionChange={setSelectedNames}
          />
        )}
      </div>
    </Modal>
  );
};
