// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconArrowLeft, IconPlus } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';

import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';

import { ActionButton } from '@amdenterpriseai/components';

import { useProject } from '@/contexts/ProjectContext';
import {
  customModelDeployTarget,
  customModelToAggregatedAIM,
  getCustomModel,
} from '@/lib/app/custom-models';
import type { CustomProfileResponse } from '@/lib/app/custom-profiles';
import { OnboardPhase } from '@/types/aims';

import { DeployCustomAIMDrawer } from '../DeployCustomAIMDrawer';
import { CustomProfileDrawer } from './CustomProfileDrawer';
import { CustomProfilesTable } from './CustomProfilesTable';

/**
 * What the drawer is open for: a new profile when `profileName` is absent, or an
 * edit of that profile when it is set.
 */
type DrawerTarget = { profileName?: string };

interface Props {
  modelId: string;
}

export const CustomProfilesPage = ({ modelId }: Props) => {
  const { t } = useTranslation('models', {
    keyPrefix: 'customModels.profiles',
  });
  const { t: tActions } = useTranslation('common', { keyPrefix: 'actions' });
  const router = useRouter();
  const { activeProject } = useProject();

  // ProjectContext resolves a tick after the first render, so fall back to the
  // route segment to avoid a flash of the no-project state on a direct load.
  const projectFromRoute =
    typeof router.query.project === 'string' ? router.query.project : undefined;
  const project = activeProject ?? projectFromRoute;

  // Read the single model directly rather than the cached custom-models list:
  // deployability keys off the onboard phase, and the bulk list is populated by
  // the models tab, so on a direct load (or after the phase advances to Ready)
  // its cache can still say the model is importing and greys out deploy. Left
  // stale (no staleTime) so revisiting the page refetches and reflects a phase
  // that advanced to Ready since the last visit.
  const { data: customModel } = useQuery({
    queryKey: ['project', project, 'custom-model', modelId],
    queryFn: async () =>
      customModelToAggregatedAIM(await getCustomModel(project!, modelId)),
    enabled: Boolean(project),
    refetchOnWindowFocus: false,
  });
  const modelName = customModel?.aggregated.title ?? modelId;
  const deployTarget = useMemo(
    () => (customModel ? customModelDeployTarget(customModel) : null),
    [customModel],
  );
  // The same bar the model card sets for its own deploy action: the API turns
  // down a model whose weights are still importing or have failed, whichever
  // profile it is asked to serve.
  const isModelDeployable =
    customModel?.aggregated.onboardPhase === OnboardPhase.READY &&
    Boolean(deployTarget);

  const [drawerTarget, setDrawerTarget] = useState<DrawerTarget | null>(null);
  // The profile itself, not its name: a deploy started right after a save must
  // not depend on the profile list having caught up with the create.
  const [profileToDeploy, setProfileToDeploy] =
    useState<CustomProfileResponse | null>(null);

  const returnToList = useCallback(() => {
    if (!project) return;
    router.push(`/${encodeURIComponent(project)}/models/custom-models`);
  }, [router, project]);

  const handleNewProfile = useCallback(() => setDrawerTarget({}), []);
  const handleEditProfile = useCallback(
    (profileName: string) => setDrawerTarget({ profileName }),
    [],
  );
  const closeDrawer = useCallback(() => setDrawerTarget(null), []);
  const handleDeployProfile = useCallback(
    (profile: CustomProfileResponse) => setProfileToDeploy(profile),
    [],
  );
  const closeDeployDrawer = useCallback(() => setProfileToDeploy(null), []);

  return (
    <div className="flex flex-col w-full py-6">
      <header className="flex flex-row items-center justify-between gap-4 mb-6">
        <div className="flex flex-row items-center gap-3">
          <ActionButton
            tertiary
            size="sm"
            aria-label={tActions('back.title')}
            icon={<IconArrowLeft size={16} />}
            onPress={returnToList}
            data-testid="custom-profiles-back"
          />
          <h1 className="text-xl font-semibold">
            {t('title')}{' '}
            <span className="font-normal text-muted">
              {t('titleForModel', { modelName })}
            </span>
          </h1>
        </div>
        <ActionButton
          primary
          icon={<IconPlus size={16} stroke={2} />}
          onPress={handleNewProfile}
          data-testid="custom-profiles-new-profile"
        >
          {t('actions.newProfile.label')}
        </ActionButton>
      </header>
      {project && (
        <CustomProfilesTable
          project={project}
          modelId={modelId}
          onEditProfile={handleEditProfile}
          onDeployProfile={handleDeployProfile}
          isModelDeployable={isModelDeployable}
        />
      )}
      {project && drawerTarget && (
        <CustomProfileDrawer
          // Remounts per target so the form starts from that profile's values
          // rather than whichever one the drawer was last opened for.
          key={drawerTarget.profileName ?? 'new'}
          isOpen
          onClose={closeDrawer}
          project={project}
          modelId={modelId}
          modelName={modelName}
          profileName={drawerTarget.profileName}
          onSaveAndDeploy={isModelDeployable ? setProfileToDeploy : undefined}
        />
      )}
      {project && profileToDeploy && deployTarget && (
        <DeployCustomAIMDrawer
          isOpen
          onClose={closeDeployDrawer}
          model={deployTarget.model}
          namespace={project}
          sourceUri={deployTarget.aim.sourceUri}
          supportsProfileSelection
          initialProfile={profileToDeploy}
        />
      )}
    </div>
  );
};

CustomProfilesPage.displayName = 'CustomProfilesPage';
