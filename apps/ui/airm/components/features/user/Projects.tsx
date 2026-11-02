// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  FormSelect,
  SelectItem,
  ConfirmationModal,
  DrawerForm,
  FormFieldComponent,
  ActionButton,
} from '@amdenterpriseai/components';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';

import { useTranslation } from 'next-i18next';

import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';

import {
  addUsersToProject as addUserToProjectAPI,
  deleteUserFromProject as deleteUserFromProjectAPI,
} from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { AssignProjectFormData, ProjectInUser } from '@/types/users';
import { UserWithProjects } from '@/types/users';

import ProjectAndRoleEntry from './ProjectAndRoleEntry';

import { ZodType, z } from 'zod';

interface Props {
  user: UserWithProjects;
  projects: ProjectInUser[];
}

const translationSet = 'users';
export const Projects: React.FC<Props> = ({ user, projects }) => {
  const { t } = useTranslation(translationSet);
  const [selectedProject, setSelectedProject] = useState<ProjectInUser | null>(
    null,
  );

  const { toast } = useSystemToast();
  const {
    isOpen: isAddGroupOpen,
    onOpen: onAddGroupOpen,
    onOpenChange: onAddGroupOpenChange,
  } = useOverlayState();
  const {
    isOpen: isDeleteConfirmOpen,
    onOpen: onDeleteConfirmOpen,
    onOpenChange: onDeleteConfirmOpenChange,
  } = useOverlayState();

  const queryClient = useQueryClient();

  const projectFormSchema: ZodType<AssignProjectFormData> = useMemo(
    () =>
      z.object({
        project: z
          .string()
          .trim()
          .nonempty(
            t('detail.projectsAndRoles.projects.validation.project.selected') ||
              '',
          ),
      }),
    [t],
  );

  const { mutate: addUserToProject, isPending: isAddingUserToProject } =
    useMutation({
      mutationFn: addUserToProjectAPI,
      onSuccess: () => {
        onAddGroupOpenChange();
        queryClient.invalidateQueries({ queryKey: ['user'] });
        toast.success(
          t('detail.projectsAndRoles.projects.notification.add.success'),
        );
      },
      onError: (error) => {
        toast.error(
          t('detail.projectsAndRoles.projects.notification.add.error'),
          error as APIRequestError,
        );
        console.error('Error adding user to project:', error);
      },
    });

  const {
    mutate: deleteUserFromProject,
    isPending: isDeletingUserFromProject,
  } = useMutation({
    mutationFn: deleteUserFromProjectAPI,
    onSuccess: () => {
      onDeleteConfirmOpenChange();
      queryClient.invalidateQueries({ queryKey: ['user'] });
      toast.success(
        t('detail.projectsAndRoles.projects.notification.delete.success'),
      );
    },
    onError: () => {
      toast.error(
        t('detail.projectsAndRoles.projects.notification.delete.error'),
      );
    },
  });

  const candidateProjects = projects.filter(
    (g) => (user.projects || []).filter((p) => p.id == g.id).length === 0,
  );

  const handleAddUserToProject = useCallback(
    (data: { [x: string]: unknown }) => {
      addUserToProject({
        userIds: [user.id],
        projectId: data?.project as string,
      });
    },
    [addUserToProject, user],
  );

  const handleDeleteUserFromProject = useCallback(() => {
    if (user.id && selectedProject) {
      deleteUserFromProject({
        userId: user.id,
        projectId: selectedProject.id,
      });
    }
  }, [deleteUserFromProject, user?.id, selectedProject]);

  return (
    <div>
      <div className="mt-8 flex justify-between gap-4">
        <h3 className="uppercase">
          {t('detail.projectsAndRoles.projects.title')}
        </h3>
        <ActionButton
          tertiary
          aria-label={
            t('detail.projectsAndRoles.projects.actions.add.title') || ''
          }
          color="primary"
          size="sm"
          isDisabled={candidateProjects.length == 0}
          onPress={onAddGroupOpen}
        >
          {t('detail.projectsAndRoles.projects.actions.add.title')}
        </ActionButton>
      </div>
      <div className="mt-4">
        {user.projects && user.projects.length > 0
          ? user.projects.map((project) => (
              <ProjectAndRoleEntry
                key={project.id}
                name={project.name}
                description={project.description}
                onPress={() => {
                  setSelectedProject(project);
                  onDeleteConfirmOpen();
                }}
              />
            ))
          : t('detail.projectsAndRoles.projects.empty')}
      </div>

      <DrawerForm
        isOpen={isAddGroupOpen}
        isActioning={isAddingUserToProject}
        title={t('detail.projectsAndRoles.projects.actions.add.title')}
        cancelText={t('detail.projectsAndRoles.projects.actions.add.cancel')}
        confirmText={t('detail.projectsAndRoles.projects.actions.add.confirm')}
        validationSchema={projectFormSchema}
        onFormSuccess={handleAddUserToProject}
        onCancel={onAddGroupOpenChange}
        renderFields={(form) => {
          return (
            <div className="flex flex-col gap-4">
              <FormFieldComponent<AssignProjectFormData>
                formField={{
                  name: 'project',
                  label: t(
                    'detail.projectsAndRoles.projects.form.project.label',
                  ),
                  placeholder: t(
                    'detail.projectsAndRoles.projects.form.project.placeholder',
                  ),
                  isRequired: true,
                  component: (props) => (
                    <FormSelect aria-label={props.label} {...props}>
                      {candidateProjects.map((project) => (
                        <SelectItem key={project.id}>{project.name}</SelectItem>
                      ))}
                    </FormSelect>
                  ),
                }}
                form={form}
              />
            </div>
          );
        }}
      />

      <ConfirmationModal
        description={t(
          'detail.projectsAndRoles.projects.actions.delete.description',
          {
            project: selectedProject?.name,
          },
        )}
        title={t('detail.projectsAndRoles.projects.actions.delete.title')}
        isOpen={isDeleteConfirmOpen}
        loading={isDeletingUserFromProject}
        onConfirm={handleDeleteUserFromProject}
        onClose={onDeleteConfirmOpenChange}
        confirmationButtonColor="danger"
      />
    </div>
  );
};

export default Projects;
