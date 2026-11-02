// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { NoDataDisplay, Tooltip } from '@amdenterpriseai/components';
import { ProjectSecret } from '@/types/secrets';
import { Secret } from '@/types/secrets';

interface Props {
  secret?: Secret;
}

export const SecretProjectAssignedTo: React.FC<Props> = ({ secret }) => {
  const projectSecretCount = secret?.projectSecrets.length ?? 0;

  if (!secret || !secret?.projectSecrets || projectSecretCount === 0) {
    return <NoDataDisplay />;
  }

  if (projectSecretCount === 1) {
    return <span>{secret.projectSecrets[0]?.project?.name}</span>;
  }

  return (
    <Tooltip
      content={
        <ul className="p-2 list-disc list-inside">
          {secret.projectSecrets.map((projectSecret: ProjectSecret) => (
            <li key={projectSecret.id}>{projectSecret.project?.name}</li>
          ))}
        </ul>
      }
      placement="top"
    >
      {/* biome-ignore lint/a11y/useSemanticElements: the element reveals supplemental text rather than performing an action. */}
      <span
        className="cursor-pointer underline"
        role="button"
        tabIndex={0}
      >{`${projectSecretCount} projects`}</span>
    </Tooltip>
  );
};

export default SecretProjectAssignedTo;
