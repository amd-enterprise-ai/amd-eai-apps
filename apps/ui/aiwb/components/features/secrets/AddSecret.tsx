// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  SelectItem,
  DrawerPrimitive as Drawer,
  DrawerBody,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  ActionButton,
  FormInput,
  FormPasswordInput,
  FormSelect,
  FormTextarea,
  ManagedForm,
  Button,
} from '@amdenterpriseai/components';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useMemo } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { useFieldArray } from 'react-hook-form';

import { useTranslation } from 'next-i18next';

import { useSystemToast } from '@amdenterpriseai/hooks';

import { createS3SecretRequest } from '@/lib/app/s3-secret';
import { createProjectSecret } from '@/lib/app/secrets';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { SecretUseCase } from '@amdenterpriseai/types';

import { SecretResponseData, CreateSecretRequest } from '@/types/secrets';

import { z } from 'zod';

const secretDataEntrySchema = z.object({
  key: z.string(),
  value: z.string(),
});

const secretFormSchema = z.object({
  displayName: z.string(),
  useCase: z.nativeEnum(SecretUseCase),
  key: z.string().optional(),
  value: z.string().optional(),
  s3AccessKeyId: z.string().optional(),
  s3SecretAccessKey: z.string().optional(),
  dataEntries: z.array(secretDataEntrySchema).optional(),
});

type CreateSecretForm = z.infer<typeof secretFormSchema>;

const USE_CASE_OPTIONS = [
  SecretUseCase.HUGGING_FACE,
  SecretUseCase.S3,
  SecretUseCase.IMAGE_PULL_SECRET,
  SecretUseCase.GENERIC,
];

const PREDEFINED_KEYS: Partial<Record<SecretUseCase, string>> = {
  [SecretUseCase.HUGGING_FACE]: 'token',
  [SecretUseCase.IMAGE_PULL_SECRET]: '.dockerconfigjson',
};

type CreateSecretFormFieldPath = Parameters<
  UseFormReturn<CreateSecretForm>['register']
>[0];

function AddSecretKeyValueFields({
  form,
  t,
}: {
  form: UseFormReturn<CreateSecretForm>;
  t: (key: string) => string;
}) {
  const useCase = form.watch('useCase') as SecretUseCase | undefined;
  const isOther = useCase === SecretUseCase.GENERIC;
  const isS3 = useCase === SecretUseCase.S3;

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'dataEntries',
  });
  const previousUseCaseRef = useRef<SecretUseCase | undefined>(undefined);

  useEffect(() => {
    if (!useCase) {
      previousUseCaseRef.current = undefined;
      return;
    }

    // Only reset sibling fields when the user actually switches use case.
    if (previousUseCaseRef.current === useCase) {
      return;
    }
    previousUseCaseRef.current = useCase;

    const predefined = useCase ? PREDEFINED_KEYS[useCase] : undefined;
    form.clearErrors([
      'displayName',
      'key',
      'value',
      'dataEntries',
      's3AccessKeyId',
      's3SecretAccessKey',
    ]);
    if (isOther) {
      form.setValue('dataEntries', [{ key: '', value: '' }]);
      form.setValue('s3AccessKeyId', '');
      form.setValue('s3SecretAccessKey', '');
    } else if (isS3) {
      form.setValue('key', '');
      form.setValue('value', '');
      form.setValue('dataEntries', [{ key: '', value: '' }]);
    } else {
      form.setValue('value', '');
      form.setValue('key', predefined ?? '');
      form.setValue('s3AccessKeyId', '');
      form.setValue('s3SecretAccessKey', '');
    }
  }, [form, useCase, isOther, isS3]);

  if (isOther) {
    return (
      <div className="flex flex-col gap-4">
        {fields.map((field, index) => (
          <div
            key={field.id}
            className="flex flex-col gap-2 rounded-lg border border-default p-3"
          >
            <div className="flex items-end gap-2">
              <FormInput<CreateSecretForm>
                form={form}
                name={`dataEntries.${index}.key` as CreateSecretFormFieldPath}
                label={t('form.add.field.key')}
                placeholder={t('form.add.field.keyPlaceholder')}
                className="flex-1"
              />
              {fields.length > 1 && (
                <Button
                  type="button"
                  variant="light"
                  color="danger"
                  size="sm"
                  onPress={() => remove(index)}
                  aria-label={t('form.add.field.remove')}
                >
                  {t('form.add.field.remove')}
                </Button>
              )}
            </div>
            <FormTextarea<CreateSecretForm>
              form={form}
              name={`dataEntries.${index}.value` as CreateSecretFormFieldPath}
              label={t('form.add.field.value')}
              placeholder={t('form.add.field.valuePlaceholder')}
              minRows={3}
            />
          </div>
        ))}
        <Button
          type="button"
          variant="bordered"
          size="sm"
          onPress={() => append({ key: '', value: '' })}
        >
          {t('form.add.field.addEntry')}
        </Button>
      </div>
    );
  }

  if (isS3) {
    return (
      <div className="flex flex-col gap-4">
        <FormInput<CreateSecretForm>
          form={form}
          name="s3AccessKeyId"
          label={t('form.add.field.s3.accessKeyIdLabel')}
          placeholder={t('form.add.field.s3.accessKeyIdPlaceholder')}
          isRequired
        />
        <FormPasswordInput<CreateSecretForm>
          form={form}
          name="s3SecretAccessKey"
          label={t('form.add.field.s3.secretAccessKeyLabel')}
          placeholder={t('form.add.field.s3.secretAccessKeyPlaceholder')}
          isRequired
          preventPasswordManagerPrompt
          data-1p-ignore
          data-lpignore="true"
          data-bwignore
        />
      </div>
    );
  }

  const valuePlaceholder =
    useCase === SecretUseCase.HUGGING_FACE
      ? t('form.add.field.valuePlaceholderHuggingFace')
      : useCase === SecretUseCase.IMAGE_PULL_SECRET
        ? t('form.add.field.valuePlaceholderImagePull')
        : t('form.add.field.valuePlaceholder');

  return (
    <div className="flex flex-col gap-4">
      <FormInput<CreateSecretForm>
        form={form}
        name="key"
        label={t('form.add.field.key')}
        placeholder={t('form.add.field.keyPlaceholder')}
        isDisabled
      />
      <FormTextarea<CreateSecretForm>
        form={form}
        name="value"
        label={t('form.add.field.value')}
        placeholder={valuePlaceholder}
        minRows={15}
      />
      {useCase === SecretUseCase.HUGGING_FACE && (
        <p className="text-sm text-muted">
          <a
            href="https://huggingface.co/docs/hub/security-tokens"
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline"
          >
            {t('form.add.field.helpHuggingFace')}
          </a>
        </p>
      )}
      {useCase === SecretUseCase.IMAGE_PULL_SECRET && (
        <p className="text-sm text-muted">
          <a
            href="https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline"
          >
            {t('form.add.field.helpImagePull')}
          </a>
        </p>
      )}
    </div>
  );
}

interface Props {
  isOpen: boolean;
  namespace: string;
  secrets?: SecretResponseData[];
  onClose: () => void;
}

export const AddSecret: React.FC<Props> = ({
  isOpen,
  namespace,
  secrets,
  onClose,
}) => {
  const { t } = useTranslation('secrets');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();
  const formRef = useRef<HTMLFormElement>(null);
  const defaultFormValues = useMemo<Partial<CreateSecretForm>>(
    () => ({
      displayName: '',
      key: '',
      value: '',
      s3AccessKeyId: '',
      s3SecretAccessKey: '',
      dataEntries: [{ key: '', value: '' }],
    }),
    [],
  );

  const formSchema = useMemo(
    () =>
      secretFormSchema
        .extend({
          displayName: z
            .string()
            .trim()
            .min(1, { message: '' })
            .min(2, { message: t('form.add.validation.nameTooShort') })
            .max(253, { message: t('form.add.validation.nameTooLong') }),
          useCase: z.nativeEnum(SecretUseCase, { required_error: '' }),
          dataEntries: z
            .array(
              z.object({
                key: z.string(),
                value: z.string(),
              }),
            )
            .optional()
            .default([]),
        })
        .refine(
          (data) =>
            !secrets?.some((s) => s.displayName === data.displayName.trim()),
          {
            message: t('form.add.validation.duplicateName'),
            path: ['displayName'],
          },
        )
        .refine(
          (data) => {
            if (
              data.useCase !== SecretUseCase.GENERIC &&
              data.useCase !== SecretUseCase.S3
            ) {
              return (data.value ?? '').trim().length > 0;
            }
            return true;
          },
          {
            message: t('form.add.validation.dataRequired'),
            path: ['value'],
          },
        )
        .refine(
          (data) => {
            if (data.useCase === SecretUseCase.GENERIC) {
              const entries = (data.dataEntries ?? []).filter(
                (e): e is { key: string; value: string } =>
                  typeof e?.key === 'string' && typeof e?.value === 'string',
              );
              return (
                entries.length > 0 &&
                entries.some(
                  (e) => e.key.trim().length > 0 && e.value.trim().length > 0,
                )
              );
            }
            return true;
          },
          {
            message: t('form.add.validation.keyRequired'),
            path: ['dataEntries'],
          },
        )
        .refine(
          (data) => {
            if (data.useCase !== SecretUseCase.IMAGE_PULL_SECRET) return true;
            const raw = (data.value ?? '').trim();
            if (!raw) return true;
            try {
              JSON.parse(raw);
              return true;
            } catch {
              return false;
            }
          },
          {
            message: t('form.add.validation.dockerConfigJsonInvalid'),
            path: ['value'],
          },
        )
        .refine(
          (data) => {
            if (data.useCase !== SecretUseCase.S3) return true;
            return (data.s3AccessKeyId ?? '').trim().length > 0;
          },
          {
            message: t('form.add.validation.s3AccessKeyRequired'),
            path: ['s3AccessKeyId'],
          },
        )
        .refine(
          (data) => {
            if (data.useCase !== SecretUseCase.S3) return true;
            return (data.s3SecretAccessKey ?? '').trim().length > 0;
          },
          {
            message: t('form.add.validation.s3SecretKeyRequired'),
            path: ['s3SecretAccessKey'],
          },
        ),
    [t, secrets],
  );

  const { mutate: createSecret, isPending } = useMutation({
    mutationFn: (data: CreateSecretRequest) =>
      createProjectSecret(namespace, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['project', namespace, 'secrets'],
      });
      toast.success(t('form.add.notification.success'));
      onClose();
    },
    onError: (error: APIRequestError) => {
      toast.error(t('form.add.notification.error'), error);
    },
  });

  const handleFormSuccess = useCallback(
    (values: CreateSecretForm) => {
      let secretData: Record<string, string> = {};
      switch (values.useCase) {
        case SecretUseCase.IMAGE_PULL_SECRET:
          secretData = {
            '.dockerconfigjson': Buffer.from(
              values.value ?? '',
              'utf-8',
            ).toString('base64'),
          };
          break;
        case SecretUseCase.HUGGING_FACE:
          secretData = {
            token: Buffer.from(values.value ?? '', 'utf-8').toString('base64'),
          };
          break;
        case SecretUseCase.S3: {
          secretData = createS3SecretRequest({
            name: values.displayName,
            accessKeyId: values.s3AccessKeyId ?? '',
            secretAccessKey: values.s3SecretAccessKey ?? '',
          }).data;
          break;
        }
        case SecretUseCase.GENERIC: {
          const entries = values.dataEntries ?? [];
          for (const entry of entries) {
            const k = (entry.key ?? '').trim();
            const v = (entry.value ?? '').trim();
            if (k && v) {
              secretData[k] = Buffer.from(v, 'utf-8').toString('base64');
            }
          }
          break;
        }
        default: {
          const key = (values.key ?? '').trim();
          const value = values.value ?? '';
          if (key && value) {
            secretData[key] = Buffer.from(value, 'utf-8').toString('base64');
          }
        }
      }
      const payload: CreateSecretRequest = {
        displayName: values.displayName,
        useCase: values.useCase,
        data: secretData,
      };
      createSecret(payload);
    },
    [createSecret],
  );

  const handleSubmitClick = useCallback(() => {
    formRef.current?.requestSubmit();
  }, []);

  return (
    <Drawer
      isOpen={isOpen}
      onOpenChange={onClose}
      onClose={onClose}
      isDismissable={!isPending}
    >
      <DrawerContent hideCloseButton={isPending}>
        <DrawerHeader>
          {t(`form.add.title.${namespace ? 'project' : 'general'}`)}
        </DrawerHeader>
        <DrawerBody>
          <ManagedForm<CreateSecretForm>
            formRef={formRef}
            validationSchema={formSchema}
            defaultValues={defaultFormValues}
            onFormSuccess={handleFormSuccess}
            isActioning={isPending}
            renderFields={(form) => (
              <div className="flex flex-col gap-4">
                <FormInput<CreateSecretForm>
                  form={form}
                  name="displayName"
                  label="Display Name"
                  placeholder="My HuggingFace Token"
                  isRequired
                />
                <FormSelect<CreateSecretForm>
                  form={form}
                  name="useCase"
                  label="Use Case"
                  placeholder="Select use case"
                  isRequired
                  data-testid="useCaseSelect"
                >
                  {USE_CASE_OPTIONS.map((secretUseCase) => (
                    <SelectItem
                      key={secretUseCase}
                      textValue={t(`useCase.${secretUseCase}`)}
                      data-testid={`use-case-option-${secretUseCase}`}
                    >
                      {t(`useCase.${secretUseCase}`)}
                    </SelectItem>
                  ))}
                </FormSelect>
                <AddSecretKeyValueFields form={form} t={t} />
              </div>
            )}
          />
        </DrawerBody>
        <DrawerFooter>
          <ActionButton
            tertiary
            aria-label={t('form.add.action.cancel')}
            type="button"
            onPress={onClose}
          >
            {t('form.add.action.cancel')}
          </ActionButton>
          <ActionButton
            primary
            aria-label={t('form.add.action.add')}
            isLoading={isPending}
            type="button"
            onPress={handleSubmitClick}
          >
            {t('form.add.action.add')}
          </ActionButton>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
};

export default AddSecret;
