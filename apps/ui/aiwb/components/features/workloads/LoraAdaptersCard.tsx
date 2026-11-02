// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Button,
  Card,
  CardBody,
  CardHeader,
  CopySnippet,
  NoDataDisplay,
  Skeleton,
} from '@amdenterpriseai/components';
import {
  IconEdit,
  IconSquareRotatedAsterisk,
  IconStack2,
} from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';
import { useState, type FC } from 'react';

import { getAdapterArtifacts } from '@/lib/app/artifacts';
import { getMaxSupportedLoraRank } from '@/lib/app/aims';
import type { AIMProfileSpec, AIMService } from '@/types/aims';

import { EditLoraAdaptersModal } from './EditLoraAdaptersModal';

type LoraAdaptersCardProps = {
  namespace: string;
  deployment: AIMService;
  /** Spec of the profile the deployment resolved to; owns adapter eligibility. */
  resolvedProfileSpec: AIMProfileSpec | null | undefined;
  /** Whether the profile spec is still in flight. */
  isResolvedProfileLoading?: boolean;
  /** Whether fetching the profile spec failed. */
  isResolvedProfileError?: boolean;
  onAdaptersUpdated?: () => void;
};

export const LoraAdaptersCard: FC<LoraAdaptersCardProps> = ({
  namespace,
  deployment,
  resolvedProfileSpec,
  isResolvedProfileLoading,
  isResolvedProfileError,
  onAdaptersUpdated,
}) => {
  const { t } = useTranslation('workloads');
  const [isEditOpen, setIsEditOpen] = useState(false);
  const adapterNames =
    deployment.spec?.adapters?.map((adapter) => adapter.name) ?? [];
  const maxRank = getMaxSupportedLoraRank(deployment.spec);
  const canEdit =
    deployment.spec?.adapterMode === 'dynamic' &&
    !!deployment.id &&
    maxRank != null;
  const {
    data: adapters = [],
    isLoading,
    isError: isAdaptersError,
  } = useQuery({
    queryKey: ['project', namespace, 'artifacts', adapterNames],
    queryFn: () => getAdapterArtifacts(namespace, adapterNames),
    enabled: adapterNames.length > 0,
  });

  return (
    <>
      <Card
        className="break-inside-avoid mb-6"
        data-testid="lora-adapters-card"
      >
        <CardHeader className="flex flex-row items-center justify-between">
          <h4 className="flex items-center gap-2 font-semibold">
            <IconStack2 size={16} className="text-muted" />
            {t('details.sections.loraAdapters')}
          </h4>
          {canEdit ? (
            <Button
              data-testid="edit-lora-adapters-button"
              size="sm"
              variant="light"
              startContent={<IconEdit size={14} />}
              onPress={() => setIsEditOpen(true)}
            >
              {t('details.loraAdapters.edit.action')}
            </Button>
          ) : null}
        </CardHeader>
        <CardBody className="space-y-4">
          <div>
            <h5 className="text-sm text-foreground">
              {t('details.fields.maxSupportedLoraRank')}
            </h5>
            {maxRank == null ? (
              <NoDataDisplay />
            ) : (
              <p className="font-mono text-sm">{maxRank}</p>
            )}
          </div>

          {isLoading ? (
            <div className="space-y-3">
              {adapterNames.map((name) => (
                <Skeleton key={name} className="h-6 w-full rounded-lg" />
              ))}
            </div>
          ) : isAdaptersError ? (
            <p className="text-sm text-warning">
              {t('details.loraAdapters.metadataUnavailable')}
            </p>
          ) : adapterNames.length === 0 ? (
            <p className="text-sm text-muted">
              {t('details.loraAdapters.empty')}
            </p>
          ) : (
            <div className="space-y-3">
              {adapterNames.map((name) => {
                const adapter = adapters.find((item) => item.name === name);
                const displayName = adapter?.displayName ?? name;
                const rank = adapter?.rank;

                return (
                  <div
                    key={name}
                    className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3"
                  >
                    <div className="text-muted flex flex-col items-center gap-1">
                      <IconSquareRotatedAsterisk size={18} aria-hidden />
                      <span aria-hidden className="font-mono text-xs">
                        {rank ?? '—'}
                      </span>
                      {/* The icon carries the meaning visually; without this a
                          screen reader would announce a bare digit. */}
                      <span className="sr-only">
                        {rank == null
                          ? t('details.loraAdapters.rankUnavailable')
                          : t('details.loraAdapters.rank', { rank })}
                      </span>
                    </div>
                    <div className="flex flex-col gap-0.5">
                      <div className="truncate text-sm">{displayName}</div>
                      <div className=" text-muted text-xs flex items-center gap-1">
                        <span className="truncate">{name}</span>
                      </div>
                    </div>
                    <CopySnippet
                      buttonOnly
                      value={name}
                      copyButtonAriaLabel={t('details.loraAdapters.copyName')}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </CardBody>
      </Card>
      {canEdit ? (
        <EditLoraAdaptersModal
          deployment={deployment}
          namespace={namespace}
          resolvedProfileSpec={resolvedProfileSpec}
          isResolvedProfileLoading={isResolvedProfileLoading}
          isResolvedProfileError={isResolvedProfileError}
          isOpen={isEditOpen}
          onOpenChange={setIsEditOpen}
          onSuccess={onAdaptersUpdated}
        />
      ) : null}
    </>
  );
};
