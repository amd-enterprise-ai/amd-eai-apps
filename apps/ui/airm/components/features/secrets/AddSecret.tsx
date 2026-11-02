// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  SelectItem,
  DrawerForm,
  FormFieldComponent,
  FormSelect,
  Textarea,
  cn,
} from '@amdenterpriseai/components';
import { useMutation } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { useSystemToast } from '@amdenterpriseai/hooks';

import { createProjectSecret, createSecret } from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { FormField } from '@amdenterpriseai/types';
import { AddSecretFormData } from '@/types/secrets';
import { SecretScope, SecretType } from '@/types/enums/secrets';
import { SecretUseCase } from '@amdenterpriseai/types';
import { Project } from '@/types/projects';
import {
  CreateProjectSecretRequest,
  CreateSecretRequest,
  Secret,
} from '@/types/secrets';

import { createAddSecretFormSchema } from './addSecretFormSchema';
import { createManifestYamlValidators } from './secretManifestYaml';

import { parseAllDocuments } from 'yaml';

interface Props {
  isOpen: boolean;
  projects: Project[];
  secrets: Secret[];
  defaultScope: SecretScope;
  scopeSelectDisabled: boolean;
  projectSelectDisabled: boolean;
  disabledProjectIds?: string[];
  onCreateSuccess: () => void;
  onClose: () => void;
  restrictToUseCases?: SecretUseCase[];
}

export const AddSecret: React.FC<Props> = ({
  isOpen,
  defaultScope,
  scopeSelectDisabled,
  projectSelectDisabled,
  projects,
  secrets,
  onCreateSuccess,
  onClose,
  disabledProjectIds = [],
  restrictToUseCases,
}) => {
  const { t } = useTranslation('secrets');
  const { toast } = useSystemToast();

  const { validateExternalSecretYaml, validateKubernetesSecretYaml } = useMemo(
    () => createManifestYamlValidators(),
    [],
  );

  const { mutate: addSecret, isPending } = useMutation({
    mutationFn: async (data: CreateSecretRequest) => {
      if (data.scope === SecretScope.PROJECT) {
        return createProjectSecret(
          data.projectIds[0],
          data as CreateProjectSecretRequest,
        );
      }
      return createSecret(data as CreateSecretRequest);
    },
    onSuccess: () => {
      onCreateSuccess();
      toast.success(t('form.add.notification.success'));
    },
    onError: (error) => {
      toast.error(t('form.add.notification.error'), error as APIRequestError);
    },
  });

  const handleAddSecretSubmit = useCallback(
    async (data: AddSecretFormData): Promise<void> => {
      const yamls = parseAllDocuments(data.manifest);
      const yamlDoc = yamls[0];

      const manifest = yamlDoc?.toJSON?.() ?? {};
      const name = manifest.metadata?.name ?? '';

      addSecret({
        type: data.type,
        name,
        useCase: data.useCase ?? SecretUseCase.GENERIC,
        scope: data.scope,
        projectIds: data.projectIds,
        manifest: data.manifest,
      });
    },
    [addSecret],
  );

  const formSchema = useMemo(
    () =>
      createAddSecretFormSchema({
        t,
        secrets,
        validateExternalSecretYaml,
        validateKubernetesSecretYaml,
      }),
    [t, validateExternalSecretYaml, validateKubernetesSecretYaml, secrets],
  );

  const formScopeContent: FormField<AddSecretFormData> = useMemo(
    () => ({
      name: 'scope',
      label: t('form.add.field.scope.label'),
      placeholder: t('form.add.field.scope.placeholder'),
      isRequired: true,
      component: (formElemProps) => (
        <FormSelect
          defaultSelectedKeys={[defaultScope]}
          {...formElemProps}
          isDisabled={scopeSelectDisabled}
        >
          <SelectItem key={SecretScope.ORGANIZATION}>
            {t(`secretScope.Organization`)}
          </SelectItem>
          <SelectItem key={SecretScope.PROJECT}>
            {t(`secretScope.Project`)}
          </SelectItem>
        </FormSelect>
      ),
    }),
    [t, defaultScope, scopeSelectDisabled],
  );

  const getFormTypeContent = useCallback(
    (scope: SecretScope): FormField<AddSecretFormData> => {
      return {
        name: 'type',
        label: t('form.add.field.type.label'),
        placeholder: t('form.add.field.type.placeholder'),
        isRequired: true,
        component: (formElemProps) => (
          <FormSelect
            defaultSelectedKeys={[SecretType.EXTERNAL_SECRET]}
            {...formElemProps}
          >
            {scope === SecretScope.PROJECT ? (
              Object.values(SecretType).map((type) => (
                <SelectItem key={type}>{t(`secretType.${type}`)}</SelectItem>
              ))
            ) : (
              <SelectItem key={SecretType.EXTERNAL_SECRET}>
                {t(`secretType.${SecretType.EXTERNAL_SECRET}`)}
              </SelectItem>
            )}
          </FormSelect>
        ),
      };
    },
    [t],
  );

  const getFormUseCaseContent = useCallback(
    (scope: SecretScope): FormField<AddSecretFormData> => {
      return {
        name: 'useCase',
        label: t('form.add.field.useCase.label'),
        placeholder: t('form.add.field.useCase.placeholder'),
        isRequired: true,
        component: (formElemProps) => (
          <FormSelect
            defaultSelectedKeys={
              restrictToUseCases && restrictToUseCases.length > 0
                ? [restrictToUseCases[0]]
                : [SecretUseCase.GENERIC]
            }
            {...formElemProps}
            disabledKeys={
              scope === SecretScope.PROJECT ? [SecretUseCase.S3] : []
            }
            isDisabled={restrictToUseCases && restrictToUseCases.length === 1}
          >
            {restrictToUseCases && restrictToUseCases.length > 0
              ? restrictToUseCases.map((useCase) => (
                  <SelectItem key={useCase}>
                    {t(`useCase.${useCase}`)}
                  </SelectItem>
                ))
              : Object.values(SecretUseCase).map((type) => (
                  <SelectItem key={type}>{t(`useCase.${type}`)}</SelectItem>
                ))}
          </FormSelect>
        ),
      };
    },
    [t, restrictToUseCases],
  );

  const getFormProjectContent = useCallback(
    (scope: SecretScope): FormField<AddSecretFormData> => {
      return {
        name: 'projectIds',
        label: t('form.add.field.projectIds.label'),
        placeholder: t('form.add.field.projectIds.placeholder'),
        description: t('form.add.field.projectIds.description'),
        isRequired: scope === SecretScope.PROJECT,
        component: ({ className: fieldClassName, ...rest }) => (
          <FormSelect
            selectionMode={
              scope === SecretScope.PROJECT ? 'single' : 'multiple'
            }
            disallowEmptySelection={scope === SecretScope.PROJECT}
            defaultSelectedKeys={
              scope === SecretScope.PROJECT && projects.length >= 1
                ? [projects[0].id]
                : []
            }
            {...rest}
            className={cn('**:data-[slot=label]:pb-2', fieldClassName)}
            disabledKeys={disabledProjectIds}
            isDisabled={projectSelectDisabled}
          >
            {projects.map((proj) => (
              <SelectItem key={proj.id}>{proj.name}</SelectItem>
            ))}
          </FormSelect>
        ),
      };
    },
    [t, disabledProjectIds, projects, projectSelectDisabled],
  );

  const externalSecretManifestField: FormField<AddSecretFormData> = useMemo(
    () => ({
      name: 'manifest',
      label: t('form.add.field.manifest.externalSecret.label'),
      placeholder: t('form.add.field.manifest.externalSecret.placeholder'),
      description: t('form.add.field.manifest.externalSecret.description'),
      isRequired: true,
      component: (formElemProps) => (
        <Textarea
          minRows={15}
          {...formElemProps}
          onChange={(event) => {
            formElemProps.onChange({
              target: {
                value: event.target.value,
                name: formElemProps.name,
              },
            });
          }}
          onBlur={(event) => {
            formElemProps.onBlur({
              target: {
                value: event.target.value,
                name: formElemProps.name,
              },
            });
          }}
        />
      ),
    }),
    [t],
  );

  const secretManifestField: FormField<AddSecretFormData> = useMemo(
    () => ({
      name: 'manifest',
      label: t('form.add.field.manifest.secret.label'),
      placeholder: t('form.add.field.manifest.secret.placeholder'),
      description: t('form.add.field.manifest.secret.description'),
      isRequired: true,
      component: (formElemProps) => (
        <Textarea
          minRows={15}
          {...formElemProps}
          onChange={(event) => {
            formElemProps.onChange({
              target: {
                value: event.target.value,
                name: formElemProps.name,
              },
            });
          }}
          onBlur={(event) => {
            formElemProps.onBlur({
              target: {
                value: event.target.value,
                name: formElemProps.name,
              },
            });
          }}
        />
      ),
    }),
    [t],
  );

  return (
    <DrawerForm<AddSecretFormData>
      isOpen={isOpen}
      isActioning={isPending}
      onFormSuccess={(values) => {
        handleAddSecretSubmit(values);
        onClose();
      }}
      defaultValues={{
        scope: defaultScope,
        type: SecretType.EXTERNAL_SECRET,
        useCase:
          restrictToUseCases && restrictToUseCases.length > 0
            ? restrictToUseCases[0]
            : SecretUseCase.GENERIC,
        projectIds: projects.length === 1 ? [projects[0].id] : [],
      }}
      onCancel={onClose}
      title={t('form.add.title')}
      confirmText={t('form.add.action.add')}
      cancelText={t('form.add.action.cancel')}
      renderFields={(form) => {
        const watchType = form.watch('type');
        const watchScope = form.watch('scope');

        const manifestField =
          watchType === SecretType.EXTERNAL_SECRET
            ? externalSecretManifestField
            : secretManifestField;

        const formContent = [
          formScopeContent,
          getFormTypeContent(watchScope),
          getFormUseCaseContent(watchScope),
          manifestField,
          getFormProjectContent(watchScope),
        ];
        return (
          <div className="flex flex-col gap-4">
            {formContent.map((field) => (
              <FormFieldComponent<AddSecretFormData>
                key={field.name}
                formField={field}
                errorMessage={form.formState.errors[field.name]?.message}
                register={form.register}
                form={form}
              />
            ))}
          </div>
        );
      }}
      validationSchema={formSchema}
    />
  );
};

export default AddSecret;
