// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconPlus } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';
import { useCallback, useMemo, useRef, useState } from 'react';
import { z } from 'zod';

import {
  ActionButton,
  FormInput,
  FormSelect,
  ManagedForm,
  Popover,
  Select,
  SelectItem,
  type Selection,
} from '@amdenterpriseai/components';
import { useSystemToast } from '@amdenterpriseai/hooks';
import { SecretUseCase } from '@amdenterpriseai/types';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import { fetchProjectSecrets } from '@/lib/app/secrets';
import { createProjectStorage, fetchProjectStorages } from '@/lib/app/storages';
import type { components } from '@/types/api';
import type { SecretResponseData } from '@/types/secrets';

type ProjectStorageResponse = components['schemas']['ProjectStorageResponse'];

// React Aria disables a Select trigger whose collection is empty, which would
// make the "Add new" affordance in bottomContent unreachable when the project
// has no storages yet. Rendering a single disabled placeholder item keeps the
// dropdown openable so the create flow stays reachable.
const NO_OPTIONS_KEY = '__no_s3_storages__';

export interface ProjectS3StorageSelectorProps {
  namespace: string;
  value: string | null | undefined;
  onChange: (name: string) => void;
  allowCreate?: boolean;
  isRequired?: boolean;
  isDisabled?: boolean;
  isInvalid?: boolean;
  errorMessage?: string;
}

const secretLabel = (secret: SecretResponseData): string =>
  secret.displayName ?? secret.metadata.name;

const storageDisplayName = (storage: ProjectStorageResponse): string => {
  const displayName =
    'displayName' in storage ? storage.displayName : undefined;
  return typeof displayName === 'string' && displayName.trim()
    ? displayName
    : storage.name;
};

const createStorageSchema = (
  t: (key: string) => string,
  existingStorages: ProjectStorageResponse[],
) =>
  z.object({
    displayName: z
      .string()
      .trim()
      .min(1, t('validation.nameRequired'))
      .max(253)
      .refine(
        (value) =>
          !existingStorages.some(
            (storage) => storageDisplayName(storage).trim() === value,
          ),
        t('validation.duplicateName'),
      ),
    secretName: z.string().trim().min(1, t('validation.secretRequired')),
    bucketUrl: z.string().trim(),
    region: z.string().trim(),
  });

type CreateStorageForm = z.infer<ReturnType<typeof createStorageSchema>>;

/**
 * Picks the S3 configuration (storage) a model import reads its source bucket
 * with. A storage binds an existing S3 secret to connection metadata (bucket
 * URL, region); downstream consumers address it by its Kubernetes resource
 * name, so that is what the selector emits.
 */
export const ProjectS3StorageSelector = ({
  namespace,
  value,
  onChange,
  allowCreate = true,
  isRequired,
  isDisabled,
  isInvalid,
  errorMessage,
}: ProjectS3StorageSelectorProps) => {
  const { t } = useTranslation('models', { keyPrefix: 's3StorageSelector' });
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();
  const anchorRef = useRef<HTMLDivElement>(null);
  const [isSelectOpen, setIsSelectOpen] = useState(false);
  const [isPopoverOpen, setIsPopoverOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { data: storages, isLoading } = useQuery<ProjectStorageResponse[]>({
    queryKey: ['project', namespace, 'storages', 'S3'],
    queryFn: async () => {
      const response = await fetchProjectStorages(namespace, 'S3');
      return response.data;
    },
    enabled: !!namespace,
  });

  // Secrets feed the create dialog's secret picker; a storage references an
  // existing S3 secret rather than carrying credentials itself.
  const { data: secrets } = useQuery<SecretResponseData[]>({
    queryKey: ['project', namespace, 'secrets', SecretUseCase.S3],
    queryFn: async () => {
      const response = await fetchProjectSecrets(namespace, SecretUseCase.S3);
      return response.data;
    },
    enabled: !!namespace && isPopoverOpen,
  });

  const options = storages ?? [];
  const secretOptions = secrets ?? [];
  const hasOptions = options.length > 0;
  const selectedKeys = useMemo<Set<string>>(
    () => (value ? new Set([value]) : new Set()),
    [value],
  );

  const createMutation = useMutation({
    mutationFn: async (
      data: CreateStorageForm,
    ): Promise<ProjectStorageResponse> => {
      if (!namespace) {
        throw new APIRequestError(t('errors.missingNamespace'), 422);
      }
      const bucketUrl = data.bucketUrl.trim();
      const region = data.region.trim();
      const request = {
        displayName: data.displayName.trim(),
        type: 'S3',
        secretName: data.secretName,
        spec: {
          ...(bucketUrl ? { bucketUrl } : {}),
          ...(region ? { region } : {}),
        },
      } satisfies components['schemas']['ProjectStorageCreateRequest'];
      const created = await createProjectStorage(namespace, request);
      if (!created.name) {
        throw new APIRequestError(t('errors.invalidStorageResponse'), 502);
      }
      return created;
    },
    onSuccess: (created) => {
      queryClient.setQueryData<ProjectStorageResponse[]>(
        ['project', namespace, 'storages', 'S3'],
        (prev) => {
          const list = prev ?? [];
          if (list.some((storage) => storage.name === created.name)) {
            return list;
          }
          return [...list, created];
        },
      );
      void queryClient.invalidateQueries({
        queryKey: ['project', namespace, 'storages', 'S3'],
        refetchType: 'none',
      });
    },
  });

  const handleSelectionChange = useCallback(
    (keys: Selection) => {
      if (keys === 'all') return;
      const next = Array.from(keys)[0];
      if (typeof next === 'string' && next !== NO_OPTIONS_KEY) {
        onChange(next);
      }
    },
    [onChange],
  );

  const resetPopover = useCallback(() => {
    setSubmitError(null);
    setIsSubmitting(false);
  }, []);

  const handlePopoverClose = useCallback(() => {
    if (isSubmitting) return;
    setIsPopoverOpen(false);
    resetPopover();
    setIsSelectOpen(true);
  }, [isSubmitting, resetPopover]);

  const handlePopoverOpenChange = useCallback(
    (open: boolean) => {
      if (open) {
        setIsPopoverOpen(true);
        return;
      }
      handlePopoverClose();
    },
    [handlePopoverClose],
  );

  const handleAddNewClick = useCallback(() => {
    setIsSelectOpen(false);
    setIsPopoverOpen(true);
  }, []);

  const handleFormSuccess = useCallback(
    async (data: CreateStorageForm) => {
      setIsSubmitting(true);
      setSubmitError(null);
      try {
        const created = await createMutation.mutateAsync(data);
        onChange(created.name);
        setIsPopoverOpen(false);
        resetPopover();
        toast.success(
          t('notifications.createSuccess', { name: data.displayName.trim() }),
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setSubmitError(message);
        setIsSubmitting(false);
        toast.error(
          t('notifications.createError'),
          error instanceof Error ? error : undefined,
        );
      }
    },
    [createMutation, onChange, resetPopover, t, toast],
  );

  const placeholder = isLoading ? t('loading') : t('placeholder');
  // When empty but creation is allowed, keep the dropdown openable via a
  // disabled placeholder item so the "Add new" affordance stays reachable.
  const showEmptyPlaceholder = !isLoading && !hasOptions && allowCreate;
  const isSelectorDisabled = Boolean(
    isDisabled || !namespace || (!allowCreate && !hasOptions),
  );

  return (
    <div ref={anchorRef}>
      <Select
        label={t('label')}
        placeholder={placeholder}
        selectedKeys={selectedKeys}
        onSelectionChange={handleSelectionChange}
        isOpen={isSelectOpen}
        onOpenChange={setIsSelectOpen}
        isRequired={isRequired}
        isDisabled={isSelectorDisabled}
        isInvalid={isInvalid}
        errorMessage={errorMessage}
        description={t('description')}
        disabledKeys={showEmptyPlaceholder ? [NO_OPTIONS_KEY] : undefined}
        data-testid="project-s3-storage-selector"
        bottomContent={
          allowCreate ? (
            <button
              type="button"
              className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-accent hover:bg-default-100"
              data-testid="s3-storage-selector-add-new"
              onClick={handleAddNewClick}
            >
              <IconPlus size={16} aria-hidden />
              {t('addNew')}
            </button>
          ) : undefined
        }
      >
        {hasOptions
          ? options.map((storage) => (
              <SelectItem
                key={storage.name}
                textValue={storageDisplayName(storage)}
                data-testid={`s3-storage-option-${storage.name}`}
              >
                {storageDisplayName(storage)}
              </SelectItem>
            ))
          : showEmptyPlaceholder
            ? [
                <SelectItem key={NO_OPTIONS_KEY} textValue={t('empty')}>
                  {t('empty')}
                </SelectItem>,
              ]
            : []}
      </Select>

      <Popover isOpen={isPopoverOpen} onOpenChange={handlePopoverOpenChange}>
        <Popover.Content
          triggerRef={anchorRef}
          placement="bottom"
          className="w-80 overflow-visible border border-border"
        >
          <Popover.Arrow />
          <Popover.Dialog>
            <ManagedForm<CreateStorageForm>
              validationSchema={createStorageSchema(t, options)}
              defaultValues={{
                displayName: '',
                secretName: '',
                bucketUrl: '',
                region: '',
              }}
              isActioning={isSubmitting}
              onFormSuccess={handleFormSuccess}
              renderFields={(form) => (
                <div className="flex flex-col gap-4 p-1">
                  <Popover.Heading className="text-base font-semibold">
                    {t('dialog.title')}
                  </Popover.Heading>
                  <FormInput
                    form={form}
                    name="displayName"
                    label={t('dialog.nameLabel')}
                    placeholder={t('dialog.namePlaceholder')}
                    isDisabled={isSubmitting}
                    isRequired
                    data-testid="s3-storage-selector-dialog-name"
                  />
                  <FormSelect
                    form={form}
                    name="secretName"
                    label={t('dialog.secretLabel')}
                    placeholder={t('dialog.secretPlaceholder')}
                    isDisabled={isSubmitting}
                    isRequired
                    data-testid="s3-storage-selector-dialog-secret"
                  >
                    {secretOptions.map((secret) => (
                      <SelectItem
                        key={secret.metadata.name}
                        textValue={secretLabel(secret)}
                        data-testid={`s3-storage-secret-option-${secret.metadata.name}`}
                      >
                        {secretLabel(secret)}
                      </SelectItem>
                    ))}
                  </FormSelect>
                  <FormInput
                    form={form}
                    name="bucketUrl"
                    label={t('dialog.bucketUrlLabel')}
                    placeholder={t('dialog.bucketUrlPlaceholder')}
                    description={t('dialog.bucketUrlDescription')}
                    isDisabled={isSubmitting}
                    data-testid="s3-storage-selector-dialog-bucket-url"
                  />
                  <FormInput
                    form={form}
                    name="region"
                    label={t('dialog.regionLabel')}
                    placeholder={t('dialog.regionPlaceholder')}
                    isDisabled={isSubmitting}
                    data-testid="s3-storage-selector-dialog-region"
                  />
                  {submitError ? (
                    <p className="text-danger text-sm" role="alert">
                      {submitError}
                    </p>
                  ) : null}
                  <div className="flex w-full justify-between pt-1">
                    <ActionButton
                      tertiary
                      aria-label={t('dialog.cancel')}
                      onPress={handlePopoverClose}
                      isDisabled={isSubmitting}
                    >
                      {t('dialog.cancel')}
                    </ActionButton>
                    <ActionButton
                      primary
                      type="submit"
                      aria-label={t('dialog.submit')}
                      isLoading={isSubmitting}
                      isDisabled={!form.formState.isValid || isSubmitting}
                      data-testid="s3-storage-selector-dialog-submit"
                    >
                      {t('dialog.submit')}
                    </ActionButton>
                  </div>
                </div>
              )}
            />
          </Popover.Dialog>
        </Popover.Content>
      </Popover>
    </div>
  );
};

export default ProjectS3StorageSelector;
