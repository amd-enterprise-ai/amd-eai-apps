// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';

import { ModelStepSummary } from '@/components/features/models/DeployAIMWizard/steps/ModelStep';
import type { SecretResponseData } from '@/types/secrets';
import { SecretUseCase } from '@amdenterpriseai/types';

import { createMockParsedAIM, formValues } from './fixtures';

describe('ModelStepSummary', () => {
  it('shows the model name under Model and the resolved version under Container version', () => {
    const selectedAim = createMockParsedAIM({
      title: 'Llama 3.1 8B Instruct',
      isLatest: true,
    });

    render(
      <ModelStepSummary
        data={{
          ...formValues,
          model: selectedAim.model,
          imagePullSecrets: [],
        }}
        selectedAim={selectedAim}
        hfTokens={[]}
        imagePullSecrets={[]}
      />,
    );

    expect(screen.getByText('deployAIM.summary.model')).toBeInTheDocument();
    expect(screen.getByText('Llama 3.1 8B Instruct')).toBeInTheDocument();
    expect(
      screen.getByText('deployAIM.summary.containerVersion'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('1.2.0 (deployAIM.fields.version.latest)'),
    ).toBeInTheDocument();
  });

  it('shows the Hugging Face token display name when required', () => {
    const selectedAim = createMockParsedAIM({ isHfTokenRequired: true });
    const hfTokens: SecretResponseData[] = [
      {
        metadata: {
          name: 'my-token-secret',
          namespace: 'default',
          creationTimestamp: '',
        },
        useCase: SecretUseCase.HUGGING_FACE,
        displayName: 'My HF Token',
      },
    ];

    render(
      <ModelStepSummary
        data={{
          ...formValues,
          model: selectedAim.model,
          hfTokenSecretName: 'my-token-secret',
          imagePullSecrets: [],
        }}
        selectedAim={selectedAim}
        hfTokens={hfTokens}
        imagePullSecrets={[]}
      />,
    );

    expect(screen.getByText('My HF Token')).toBeInTheDocument();
  });

  it('lists selected image pull secrets by display name', () => {
    const selectedAim = createMockParsedAIM();
    const imagePullSecrets: SecretResponseData[] = [
      'Registry A',
      'Registry B',
    ].map((displayName, index) => ({
      metadata: {
        name: `wb-secret-${index}`,
        namespace: 'default',
        creationTimestamp: '',
      },
      useCase: SecretUseCase.IMAGE_PULL_SECRET,
      displayName,
    }));

    render(
      <ModelStepSummary
        data={{
          ...formValues,
          model: selectedAim.model,
          imagePullSecrets: 'wb-secret-0,wb-secret-1',
        }}
        selectedAim={selectedAim}
        hfTokens={[]}
        imagePullSecrets={imagePullSecrets}
      />,
    );

    expect(screen.getByText('Registry A, Registry B')).toBeInTheDocument();
    expect(screen.queryByText(/wb-secret-/)).not.toBeInTheDocument();
  });

  it('falls back to the secret name when no display name is known', () => {
    const selectedAim = createMockParsedAIM();

    render(
      <ModelStepSummary
        data={{
          ...formValues,
          model: selectedAim.model,
          imagePullSecrets: ['legacy-pull-secret'],
        }}
        selectedAim={selectedAim}
        hfTokens={[]}
        imagePullSecrets={[]}
      />,
    );

    expect(screen.getByText('legacy-pull-secret')).toBeInTheDocument();
  });
});
