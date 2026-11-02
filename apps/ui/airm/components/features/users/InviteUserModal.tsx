// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  SelectItem,
  DrawerForm,
  Alert,
  FormFieldComponent,
  FormPasswordInput,
  FormSelect,
  type SelectRenderItem,
} from '@amdenterpriseai/components';
import React, { useCallback, useMemo } from 'react';

import { IconAt } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useTranslation } from 'next-i18next';

import { useAccessControl } from '@/hooks/useAccessControl';
import { useSystemToast } from '@amdenterpriseai/hooks';

import { fetchProjects } from '@/services/app';
import {
  fetchInvitedUsers,
  fetchUsers,
  inviteUser as inviteUserAPI,
} from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { UserRole } from '@amdenterpriseai/types';
import { FormField } from '@amdenterpriseai/types';
import { ProjectsResponse } from '@/types/projects';
import { InviteUserFormData } from '@/types/users';
import {
  InvitedUser,
  InviteUserRequest,
  InvitedUsersResponse,
  User,
  UsersResponse,
} from '@/types/users';

import { ZodType, z } from 'zod';

interface Props {
  isOpen: boolean;
  selectedProjectIds?: string[];
  onOpenChange: () => void;
  onSuccess?: () => void;
  invitedUsersInitialData?: InvitedUsersResponse;
  usersInitialData?: UsersResponse;
}

const InviteUserModal: React.FC<Props> = ({
  isOpen,
  onOpenChange,
  selectedProjectIds,
  onSuccess,
  invitedUsersInitialData,
  usersInitialData,
}) => {
  const i18nKeySet = 'users';
  const { t } = useTranslation(i18nKeySet);
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();
  const { isTempPasswordRequired } = useAccessControl();

  const { data: userData } = useQuery<UsersResponse>({
    queryKey: ['users'],
    queryFn: fetchUsers,
    initialData: usersInitialData,
  });

  const { data: invitedUserData } = useQuery<InvitedUsersResponse>({
    queryKey: ['invited-users'],
    queryFn: fetchInvitedUsers,
    initialData: invitedUsersInitialData,
  });

  const { data: projectData } = useQuery<ProjectsResponse>({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  });

  const allUsers = useMemo(
    () => [...(userData?.data || []), ...(invitedUserData?.data || [])],
    [userData, invitedUserData],
  );

  const allProjects = useMemo(() => projectData?.data || [], [projectData]);

  const renderProjectSelectValue = useCallback(
    (items: SelectRenderItem[]) => {
      if (items.length === 0) {
        return null;
      }
      const names = items.map((item) => {
        const id = String(item.key);
        const project = allProjects.find((p) => p.id === id);
        return project?.name ?? id;
      });
      return names.join(', ');
    },
    [allProjects],
  );

  const formSchema: ZodType<InviteUserFormData> = useMemo(
    () =>
      z.object({
        email: z
          .string()
          .nonempty(t('modal.addUser.form.email.validation.required') || '')
          .email(t('modal.addUser.form.email.validation.format') || '')
          .refine(
            (value) => {
              if (
                allUsers.some(
                  (user: User | InvitedUser) =>
                    user.email.toLowerCase() ===
                    (value as string).trim().toLowerCase(),
                )
              ) {
                return false;
              }
              return true;
            },
            {
              message: t('modal.addUser.form.email.validation.unique') || '',
            },
          ),
        projectIds: z
          .string()
          .optional()
          .transform((val) => (val ? val.split(',') : [])),
        roles: z
          .string()
          .nonempty(t('modal.addUser.form.roles.validation.required') || ''),
        tempPassword: z
          .union([
            z
              .string()
              .min(
                8,
                t('modal.addUser.form.tempPassword.validation.minLength') || '',
              )
              .max(
                256,
                t('modal.addUser.form.tempPassword.validation.maxLength') || '',
              )
              .refine((val) => val === val.trim(), {
                message:
                  t(
                    'modal.addUser.form.tempPassword.validation.noLeadingTrailingSpaces',
                  ) || '',
              }),
            z.literal(''), // allow empty string = "no temp password"
          ])
          .optional(),
      }),
    [t, allUsers],
  );

  const { mutate: inviteUser, isPending: isInvitingUser } = useMutation<
    User,
    Error,
    InviteUserRequest
  >({
    mutationFn: inviteUserAPI,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['invited-users'] });
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.invalidateQueries({ queryKey: ['project'] });
      toast.success(t('modal.addUser.notification.success'));
      onOpenChange();

      if (onSuccess) {
        onSuccess();
      }
    },
    onError: (error) => {
      toast.error(
        t('modal.addUser.notification.error'),
        error as APIRequestError,
      );

      console.error('Error inviting user:', error);
    },
  });

  const emailField: FormField<InviteUserFormData> = useMemo(
    () => ({
      name: 'email',
      label: t('modal.addUser.form.email.label'),
      isRequired: true,
      icon: (props) => <IconAt size="14" {...props} />,
    }),
    [t],
  );

  return (
    <DrawerForm<InviteUserFormData>
      isOpen={isOpen}
      isActioning={isInvitingUser}
      title={t('modal.addUser.title')}
      onOpenChange={onOpenChange}
      onFormSuccess={(data) => {
        inviteUser({
          email: data.email,
          roles:
            data.roles === UserRole.PLATFORM_ADMIN
              ? [UserRole.PLATFORM_ADMIN]
              : [],
          projectIds: data.projectIds,
          temporaryPassword: data.tempPassword,
        } as InviteUserRequest);
      }}
      defaultValues={{
        email: '',
        roles: UserRole.PLATFORM_ADMIN,
        projectIds: selectedProjectIds?.join(',') || '',
      }}
      validationSchema={formSchema}
      renderFields={(form) => (
        <div className="flex flex-col gap-4">
          <FormFieldComponent<InviteUserFormData>
            formField={emailField}
            errorMessage={form.formState.errors.email?.message}
            register={form.register}
          />
          <FormSelect<InviteUserFormData>
            form={form}
            name="roles"
            label={t('modal.addUser.form.roles.label')}
            placeholder={t('modal.addUser.form.roles.placeholder')}
            disallowEmptySelection
            isRequired
          >
            <SelectItem key={UserRole.PLATFORM_ADMIN}>
              {t('modal.addUser.form.roles.options.platformAdmin')}
            </SelectItem>
            <SelectItem key={UserRole.TEAM_MEMBER}>
              {t('modal.addUser.form.roles.options.teamMember')}
            </SelectItem>
          </FormSelect>
          <FormSelect<InviteUserFormData>
            form={form}
            name="projectIds"
            data-testid="project-select"
            label={t('modal.addUser.form.projects.label')}
            placeholder={t('modal.addUser.form.projects.placeholder')}
            selectionMode="multiple"
            renderValue={renderProjectSelectValue}
          >
            {allProjects.map((project) => (
              <SelectItem
                key={project.id}
                textValue={project.name}
                data-testid={`project-${project.id}`}
              >
                {project.name}
              </SelectItem>
            ))}
          </FormSelect>
          {isTempPasswordRequired ? (
            <>
              <FormPasswordInput
                form={form}
                name="tempPassword"
                label={t('modal.addUser.form.tempPassword.label')}
                placeholder={t('modal.addUser.form.tempPassword.placeholder')}
                isRequired
              />
              <Alert
                status="warning"
                description={t('modal.addUser.instructionTempPassword')}
              />
            </>
          ) : (
            <p className="text-sm">{t('modal.addUser.instruction')}</p>
          )}
        </div>
      )}
      onCancel={onOpenChange}
      cancelText={t('modal.addUser.actions.cancel')}
      confirmText={t('modal.addUser.actions.confirm')}
    />
  );
};

export default InviteUserModal;
