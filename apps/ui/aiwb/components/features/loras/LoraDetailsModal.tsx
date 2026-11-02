// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Chip,
  DateDisplay,
  Modal,
  NoDataDisplay,
  Spinner,
} from '@amdenterpriseai/components';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';

import AIMConditionsList from '@/components/shared/AIMConditionsList';
import { useProject } from '@/contexts/ProjectContext';
import { getAdapterArtifact } from '@/lib/app/artifacts';
import { translationKeyGenerator } from '@/lib/app/i18n';
import { AIM_DISPLAY_NAME_ANNOTATION } from '@/types/aims';
import {
  ARTIFACT_DESCRIPTION_ANNOTATION,
  SUBMITTER_ANNOTATION,
} from '@/types/artifacts';

type Props = {
  name: string | undefined;
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
};

type DetailsFieldProps = {
  label: string;
  children: React.ReactNode;
  className?: string;
};

const DetailsField = ({
  label,
  children,
  className = '',
}: DetailsFieldProps) => (
  <div className={className}>
    <p className="font-semibold text-foreground">{label}</p>
    <div>{children}</div>
  </div>
);

// Shared by the readiness chip (Ready/NotReady/Unknown) and the artifact
// status chip, whose CRD enum also includes Degraded/Failed/Pending/
// Progressing/NotAvailable — Degraded and Failed must stay 'danger' there.
const getStatusColor = (status: string): 'success' | 'danger' | 'warning' =>
  status === 'Ready'
    ? 'success'
    : status === 'Degraded' || status === 'Failed' || status === 'NotReady'
      ? 'danger'
      : 'warning';

const READINESS_KEYS = {
  Ready: 'readiness.ready',
  NotReady: 'readiness.notReady',
  Unknown: 'readiness.unknown',
} as const;

const getReadinessTranslationKey = translationKeyGenerator(
  READINESS_KEYS,
  'Unknown',
);

export function LoraDetailsModal({ name, isOpen, onOpenChange }: Props) {
  const { t } = useTranslation('loras');
  const { activeProject } = useProject();
  const { data, error, isLoading } = useQuery({
    queryKey: ['project', activeProject, 'artifacts', name],
    queryFn: () => getAdapterArtifact(activeProject!, name!),
    enabled: isOpen && !!activeProject && !!name,
    // Skip retries on 404 so the not-found state below shows immediately
    // instead of waiting through the retry backoff.
    retry: (failureCount, error) =>
      !(error instanceof APIRequestError && error.statusCode === 404) &&
      failureCount < 3,
  });

  if (!isOpen) return null;

  const artifact = data?.artifact;
  const annotations = artifact?.metadata.annotations ?? {};
  const displayName =
    annotations[AIM_DISPLAY_NAME_ANNOTATION] ?? artifact?.metadata.name ?? name;
  const description = annotations[ARTIFACT_DESCRIPTION_ANNOTATION];
  const conditions = artifact?.status?.conditions ?? [];

  return (
    <Modal
      onClose={() => onOpenChange(false)}
      title={t('details.modal.title', { name: displayName })}
      size="lg"
    >
      <div data-testid="lora-details-modal">
        {isLoading ? (
          <div
            className="flex min-h-32 items-center justify-center"
            data-testid="lora-details-loading"
          >
            <Spinner size="lg" color="primary" />
          </div>
        ) : error ? (
          <p role="alert" className="p-4 text-foreground">
            {error instanceof APIRequestError && error.statusCode === 404
              ? t('details.modal.notFound')
              : t('details.error')}
          </p>
        ) : artifact && data ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <DetailsField label={t('details.modal.fields.name')}>
                {displayName}
              </DetailsField>
              <DetailsField label={t('details.modal.fields.resourceName')}>
                <span className="font-mono text-xs">
                  {artifact.metadata.name}
                </span>
              </DetailsField>
              <DetailsField label={t('details.modal.fields.adapterModelId')}>
                {artifact.spec?.modelId ? (
                  <span className="font-mono">{artifact.spec.modelId}</span>
                ) : (
                  <NoDataDisplay />
                )}
              </DetailsField>
              <DetailsField label={t('details.modal.fields.compatibleWith')}>
                {artifact.spec?.compatibleWith?.length ? (
                  <ul className="space-y-1">
                    {artifact.spec.compatibleWith.map((model) => (
                      <li className="font-mono" key={model}>
                        {model}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <NoDataDisplay />
                )}
              </DetailsField>
              <DetailsField label={t('details.modal.fields.rank')}>
                {artifact.spec?.rank ?? <NoDataDisplay />}
              </DetailsField>
              <DetailsField label={t('details.modal.fields.createdBy')}>
                {annotations[SUBMITTER_ANNOTATION] ?? <NoDataDisplay />}
              </DetailsField>
              <DetailsField label={t('details.modal.fields.createdAt')}>
                {artifact.metadata.creationTimestamp ? (
                  <DateDisplay date={artifact.metadata.creationTimestamp} />
                ) : (
                  <NoDataDisplay />
                )}
              </DetailsField>
              <DetailsField label={t('details.modal.fields.readiness')}>
                <Chip
                  size="sm"
                  color={getStatusColor(data.storage.readiness)}
                  variant="flat"
                >
                  {t(getReadinessTranslationKey(data.storage.readiness))}
                </Chip>
              </DetailsField>
              <DetailsField label={t('details.modal.fields.storageUri')}>
                {data.storage.uri ? (
                  <span className="break-all font-mono text-xs">
                    {data.storage.uri}
                  </span>
                ) : (
                  <NoDataDisplay />
                )}
              </DetailsField>
              <DetailsField label={t('details.modal.fields.status')}>
                {artifact.status?.status ? (
                  <Chip
                    size="sm"
                    color={getStatusColor(artifact.status.status)}
                    variant="flat"
                  >
                    {artifact.status.status}
                  </Chip>
                ) : (
                  <NoDataDisplay />
                )}
              </DetailsField>
              {description && (
                <DetailsField
                  label={t('details.modal.fields.description')}
                  className="col-span-2"
                >
                  <p className="whitespace-pre-wrap break-words">
                    {description}
                  </p>
                </DetailsField>
              )}
            </div>
            {conditions.length > 0 && (
              <div>
                <p className="mb-2 font-semibold text-foreground">
                  {t('details.modal.fields.conditions')}
                </p>
                <AIMConditionsList conditions={conditions} />
              </div>
            )}
          </div>
        ) : (
          <div className="p-4 text-foreground">
            {t('details.modal.notFound')}
          </div>
        )}
      </div>
    </Modal>
  );
}
