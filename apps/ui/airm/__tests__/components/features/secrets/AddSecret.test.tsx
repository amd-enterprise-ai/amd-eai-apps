// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import { createProjectSecret, createSecret } from '@/services/app';

import { generateMockProjects } from '@/__mocks__/utils/project-mock';

import { SecretScope } from '@/types/enums/secrets';
import { SecretStatus, SecretType } from '@/types/enums/secrets';
import { SecretUseCase } from '@amdenterpriseai/types';

import { AddSecret } from '@/components/features/secrets/AddSecret';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock } from 'vitest';

const mockValidExternalSecretYAML = `
# example-external-secret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: my-app-secrets
  namespace: <your project namespace> # or any namespace you want
spec:
  refreshInterval: 1m
  secretStoreRef:
    kind: ClusterSecretStore
    name: vault-backend-dev
  target:
    name: app-secrets
    creationPolicy: Owner
  data:
    - secretKey: secret1
      remoteRef:
        key: test # 'test' is the KV key path under local-testing/
        property: secret1
    - secretKey: secret2
      remoteRef:
        key: test
        property: secret2
 `;

const mockValidKubernetesSecretYAML = `
apiVersion: v1
kind: Secret
metadata:
  name: my-kubernetes-secret
type: Opaque
data:
  username: YWRtaW4=
  password: MWYyZDFlMmU2N2Rm
`;
const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
};
vi.mock('@amdenterpriseai/hooks', () => ({
  useSystemToast: () => ({ toast: mockToast }),
  __esModule: true,
}));

vi.mock('@/services/app', () => ({
  createSecret: vi.fn(),
  createProjectSecret: vi.fn(),
}));

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Test data
const projects = generateMockProjects(2);

const fillFormAndSubmit = async (
  secretYaml: string = mockValidExternalSecretYAML,
) => {
  // The type defaults to EXTERNAL_SECRET, so we don't need to change it
  // Just fill the manifest input directly

  // fill secret input
  await fireEvent.change(
    screen.getByRole('textbox', {
      name: /form.add.field.manifest.externalSecret.label/i,
    }),
    {
      target: { value: secretYaml },
    },
  );

  fireEvent.click(screen.getByText('form.add.action.add'));
};

describe('AddSecret', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders when open and displays form fields', () => {
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={vi.fn()}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.ORGANIZATION}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    expect(screen.getByText('form.add.title')).toBeInTheDocument();
    expect(
      screen.getByText('form.add.field.manifest.externalSecret.label'),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('form.add.field.type.label')[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('form.add.field.projectIds.label')[0],
    ).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    const { container } = render(
      <AddSecret
        secrets={[]}
        isOpen={false}
        projects={projects}
        onClose={vi.fn()}
        onCreateSuccess={vi.fn()}
        defaultScope={SecretScope.ORGANIZATION}
        scopeSelectDisabled={false}
        projectSelectDisabled={false}
      />,
      { wrapper },
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('calls onClose when cancel is clicked', () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={onClose}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.ORGANIZATION}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });
    fireEvent.click(screen.getByText('form.add.action.cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('checks for invalid ExternalSecrets api version', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={onClose}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.ORGANIZATION}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit(
      mockValidExternalSecretYAML.replace(
        'apiVersion: external-secrets.io/v1beta1',
        'apiVersion: external-secrets.com/v1alpha1',
      ),
    );

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.manifest.error.yaml.incorrectGroup'),
      ).toBeInTheDocument();
    });
  });

  it('checks for invalid ExternalSecrets no name specified', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={onClose}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.ORGANIZATION}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit(
      mockValidExternalSecretYAML.replace('name: my-app-secrets', ''),
    );

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.manifest.error.yaml.noName'),
      ).toBeInTheDocument();
    });
  });

  it('checks for invalid ExternalSecrets invalid name specified', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={onClose}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.ORGANIZATION}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit(
      mockValidExternalSecretYAML.replace(
        'name: my-app-secrets',
        'name: My-app-secrets',
      ),
    );

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.manifest.error.yaml.invalidName'),
      ).toBeInTheDocument();
    });
  });

  it('checks for invalid ExternalSecrets wrong resource kind', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={onClose}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.ORGANIZATION}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit(
      mockValidExternalSecretYAML.replace(
        'kind: ExternalSecret',
        'kind: OtherResourceKind',
      ),
    );

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.manifest.error.yaml.incorrectKind'),
      ).toBeInTheDocument();
    });
  });

  it('checks for invalid Kubernetes Secret wrong resource kind', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={[projects[0]]}
          onClose={onClose}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.PROJECT}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    // Change to Kubernetes Secret type (scope is already Project)
    const typeButton = screen.getByRole('button', {
      name: /form.add.field.type.label/i,
    });
    await fireEvent.click(typeButton);
    const kubernetesOption = await screen.findByRole('option', {
      name: 'secretType.KubernetesSecret',
    });
    await fireEvent.click(kubernetesOption);

    await waitFor(() => {
      expect(
        screen.getByRole('textbox', {
          name: /form.add.field.manifest.secret.label/i,
        }),
      ).toBeInTheDocument();
    });

    await fireEvent.change(
      screen.getByRole('textbox', {
        name: /form.add.field.manifest.secret.label/i,
      }),
      {
        target: {
          value: mockValidKubernetesSecretYAML.replace(
            'kind: Secret',
            'kind: ConfigMap',
          ),
        },
      },
    );

    fireEvent.click(screen.getByText('form.add.action.add'));

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.manifest.error.yaml.incorrectKind'),
      ).toBeInTheDocument();
    });
  });

  it('checks for duplicate secret name with same type (organization scope)', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[
            {
              name: 'my-app-secrets',
              displayName: '',
              id: '',
              type: SecretType.EXTERNAL_SECRET,
              status: SecretStatus.UNASSIGNED,
              statusReason: null,
              scope: SecretScope.ORGANIZATION,
              projectSecrets: [],
              createdAt: '',
              updatedAt: '',
              createdBy: 'test@amd.com',
              updatedBy: 'test@amd.com',
            },
          ]}
          isOpen
          projects={projects}
          onClose={onClose}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.ORGANIZATION}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit(mockValidExternalSecretYAML);

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.manifest.error.yaml.duplicateName'),
      ).toBeInTheDocument();
    });
  });

  it('allows duplicate secret name with different type (organization scope)', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[
            {
              name: 'my-app-secrets',
              displayName: '',
              id: '',
              type: SecretType.KUBERNETES_SECRET,
              status: SecretStatus.UNASSIGNED,
              statusReason: null,
              scope: SecretScope.ORGANIZATION,
              projectSecrets: [],
              createdAt: '',
              updatedAt: '',
              createdBy: 'test@amd.com',
              updatedBy: 'test@amd.com',
            },
          ]}
          isOpen
          projects={projects}
          onClose={onClose}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.ORGANIZATION}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit(mockValidExternalSecretYAML);

    await waitFor(() => {
      expect(createSecret).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('checks for duplicate secret name and type in same project (project scope)', async () => {
    const onClose = vi.fn();
    const project = projects[0];
    act(() => {
      render(
        <AddSecret
          secrets={[
            {
              name: 'my-app-secrets',
              displayName: '',
              id: '',
              type: SecretType.EXTERNAL_SECRET,
              status: SecretStatus.UNASSIGNED,
              statusReason: null,
              scope: SecretScope.PROJECT,
              projectSecrets: [
                {
                  id: 'ps1',
                  project: {
                    id: project.id,
                    name: project.name,
                    description: project.description,
                    status: project.status,
                    statusReason: project.statusReason,
                    clusterId: project.clusterId,
                    gpuPreemption: project.gpuPreemption,
                  },
                  scope: SecretScope.PROJECT,
                  status: 'Synced' as any,
                  statusReason: null,
                  createdAt: '',
                  createdBy: 'test@amd.com',
                  updatedAt: '',
                  updatedBy: 'test@amd.com',
                },
              ],
              createdAt: '',
              updatedAt: '',
              createdBy: 'test@amd.com',
              updatedBy: 'test@amd.com',
            },
          ]}
          isOpen
          projects={[project]}
          onClose={onClose}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.PROJECT}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit(mockValidExternalSecretYAML);

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.manifest.error.yaml.duplicateName'),
      ).toBeInTheDocument();
    });
  });

  it('on submit success calls API, shows toast and invokes callbacks', async () => {
    (createSecret as Mock).mockResolvedValueOnce({});

    const onClose = vi.fn();
    const onCreateSuccess = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={onClose}
          onCreateSuccess={onCreateSuccess}
          defaultScope={SecretScope.ORGANIZATION}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit();

    await waitFor(() => {
      expect(createSecret).toHaveBeenCalledWith({
        projectIds: [],
        name: 'my-app-secrets',
        scope: SecretScope.ORGANIZATION,
        manifest: mockValidExternalSecretYAML,
        type: SecretType.EXTERNAL_SECRET,
        useCase: 'Generic',
      });
      expect(mockToast.success).toHaveBeenCalledWith(
        'form.add.notification.success',
      );
      expect(onCreateSuccess).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls mutate with correct project id when project scope and project selected', async () => {
    const onClose = vi.fn();
    const project = projects[0];
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={[project]}
          onClose={onClose}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.PROJECT}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit();

    await waitFor(() => {
      expect(createProjectSecret).toHaveBeenCalledWith(project.id, {
        name: 'my-app-secrets',
        manifest: mockValidExternalSecretYAML,
        type: SecretType.EXTERNAL_SECRET,
        useCase: 'Generic',
        scope: SecretScope.PROJECT,
        projectIds: [project.id],
      });
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('project scope uses single select and submit sends single project id', async () => {
    (createProjectSecret as Mock).mockResolvedValueOnce({});
    const onClose = vi.fn();
    const onCreateSuccess = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={onClose}
          onCreateSuccess={onCreateSuccess}
          defaultScope={SecretScope.PROJECT}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    fireEvent.click(
      screen.getByRole('button', { name: /form.add.field.projectIds.label/i }),
    );
    const option = await screen.findByRole('option', {
      name: projects[0].name,
    });
    fireEvent.click(option);

    await fillFormAndSubmit();

    await waitFor(() => {
      expect(createProjectSecret).toHaveBeenCalledWith(projects[0].id, {
        name: 'my-app-secrets',
        manifest: mockValidExternalSecretYAML,
        type: SecretType.EXTERNAL_SECRET,
        useCase: 'Generic',
        scope: SecretScope.PROJECT,
        projectIds: [projects[0].id],
      });
      const [, payload] = (createProjectSecret as Mock).mock.calls[0];
      expect(payload.projectIds).toHaveLength(1);
      expect(onCreateSuccess).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('project scope with projectSelectDisabled submits with pre-selected project', async () => {
    (createProjectSecret as Mock).mockResolvedValueOnce({});
    const onClose = vi.fn();
    const onCreateSuccess = vi.fn();
    const project = projects[0];
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={[project]}
          onClose={onClose}
          onCreateSuccess={onCreateSuccess}
          defaultScope={SecretScope.PROJECT}
          scopeSelectDisabled={false}
          projectSelectDisabled={true}
        />,
        { wrapper },
      );
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: /form.add.field.projectIds.label/i,
      }),
    );
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    await fillFormAndSubmit();

    await waitFor(() => {
      expect(createProjectSecret).toHaveBeenCalledWith(project.id, {
        name: 'my-app-secrets',
        manifest: mockValidExternalSecretYAML,
        type: SecretType.EXTERNAL_SECRET,
        useCase: 'Generic',
        scope: SecretScope.PROJECT,
        projectIds: [project.id],
      });
      expect(onCreateSuccess).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('shows error toast on mutation error', async () => {
    (createSecret as Mock).mockRejectedValueOnce(new Error('fail'));

    const onClose = vi.fn();
    const onCreateSuccess = vi.fn();
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={onClose}
          onCreateSuccess={onCreateSuccess}
          defaultScope={SecretScope.ORGANIZATION}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit();

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'form.add.notification.error',
        expect.any(Error),
      );
    });
    expect(onCreateSuccess).not.toHaveBeenCalled();
  });

  it('blocks submit when project scope and no project selected', async () => {
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={vi.fn()}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.PROJECT}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fillFormAndSubmit();
    await waitFor(() => {
      expect(createSecret).not.toHaveBeenCalled();
      expect(createProjectSecret).not.toHaveBeenCalled();
    });
  });

  // Integration: manifest error must appear even when projectIds is also invalid.
  // Both issues together are asserted in __tests__/components/features/secrets/
  // addSecretFormSchema.test.ts (HeroUI Select does not always expose projectIds
  // field errors as queryable text).
  it('reports manifest YAML errors together with project selection errors', async () => {
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={projects}
          onClose={vi.fn()}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.PROJECT}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByRole('textbox', {
        name: /form.add.field.manifest.externalSecret.label/i,
      }),
      {
        target: {
          value: mockValidExternalSecretYAML.replace(
            'apiVersion: external-secrets.io/v1beta1',
            'apiVersion: external-secrets.com/v1alpha1',
          ),
        },
      },
    );
    fireEvent.click(screen.getByText('form.add.action.add'));

    await waitFor(() => {
      expect(createSecret).not.toHaveBeenCalled();
      expect(createProjectSecret).not.toHaveBeenCalled();
      expect(
        screen.getByText('form.add.field.manifest.error.yaml.incorrectGroup'),
      ).toBeInTheDocument();
    });
  });

  it('shows useCase error when project scope and S3 selected', async () => {
    act(() => {
      render(
        <AddSecret
          secrets={[]}
          isOpen
          projects={[projects[0]]}
          onClose={vi.fn()}
          onCreateSuccess={vi.fn()}
          defaultScope={SecretScope.PROJECT}
          scopeSelectDisabled={false}
          projectSelectDisabled={false}
          restrictToUseCases={[SecretUseCase.S3]}
        />,
        { wrapper },
      );
    });
    await fillFormAndSubmit();
    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.useCase.error.s3NotAllowedForProject'),
      ).toBeInTheDocument();
    });
  });

  describe('restrictToUseCases prop', () => {
    it('restricts context field to S3 when restrictToUseCases is [S3]', () => {
      act(() => {
        render(
          <AddSecret
            secrets={[]}
            isOpen
            projects={projects}
            onClose={vi.fn()}
            onCreateSuccess={vi.fn()}
            defaultScope={SecretScope.ORGANIZATION}
            scopeSelectDisabled={false}
            projectSelectDisabled={false}
            restrictToUseCases={[SecretUseCase.S3]}
          />,
          { wrapper },
        );
      });

      // Should display S3 as the context
      expect(screen.getAllByText('useCase.S3').length).toBeGreaterThan(0);
    });

    it('restricts context field to HUGGING_FACE when restrictToUseCases is [HUGGING_FACE]', () => {
      act(() => {
        render(
          <AddSecret
            secrets={[]}
            isOpen
            projects={projects}
            onClose={vi.fn()}
            onCreateSuccess={vi.fn()}
            defaultScope={SecretScope.ORGANIZATION}
            scopeSelectDisabled={false}
            projectSelectDisabled={false}
            restrictToUseCases={[SecretUseCase.HUGGING_FACE]}
          />,
          { wrapper },
        );
      });

      expect(screen.getAllByText('useCase.HuggingFace').length).toBeGreaterThan(
        0,
      );
    });

    it('submits with S3 use case when restricted to [S3] (org scope)', async () => {
      (createSecret as Mock).mockResolvedValueOnce({});
      const onClose = vi.fn();

      act(() => {
        render(
          <AddSecret
            secrets={[]}
            isOpen
            projects={projects}
            onClose={onClose}
            onCreateSuccess={vi.fn()}
            defaultScope={SecretScope.ORGANIZATION}
            scopeSelectDisabled={false}
            projectSelectDisabled={false}
            restrictToUseCases={[SecretUseCase.S3]}
          />,
          { wrapper },
        );
      });

      await fillFormAndSubmit();

      await waitFor(() => {
        expect(createSecret).toHaveBeenCalledWith({
          projectIds: [],
          name: 'my-app-secrets',
          scope: SecretScope.ORGANIZATION,
          manifest: mockValidExternalSecretYAML,
          type: SecretType.EXTERNAL_SECRET,
          useCase: SecretUseCase.S3,
        });
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('allows all use cases when restrictToUseCases is not provided', () => {
      act(() => {
        render(
          <AddSecret
            secrets={[]}
            isOpen
            projects={projects}
            onClose={vi.fn()}
            onCreateSuccess={vi.fn()}
            defaultScope={SecretScope.ORGANIZATION}
            scopeSelectDisabled={false}
            projectSelectDisabled={false}
          />,
          { wrapper },
        );
      });

      // Should show default Generic use case
      expect(screen.getAllByText('useCase.Generic').length).toBeGreaterThan(0);
    });

    it('allows multiple use cases when restrictToUseCases has multiple values', async () => {
      await act(async () => {
        render(
          <AddSecret
            secrets={[]}
            isOpen
            projects={projects}
            onClose={vi.fn()}
            onCreateSuccess={vi.fn()}
            defaultScope={SecretScope.ORGANIZATION}
            scopeSelectDisabled={false}
            projectSelectDisabled={false}
            restrictToUseCases={[SecretUseCase.S3, SecretUseCase.DB]}
          />,
          { wrapper },
        );
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /useCase/i }));
      });

      expect(
        screen.getByRole('option', { name: 'useCase.S3' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('option', { name: 'useCase.Database' }),
      ).toBeInTheDocument();
    });

    it('submits with restricted use case for project secrets', async () => {
      (createProjectSecret as Mock).mockResolvedValueOnce({});
      const onClose = vi.fn();
      const project = projects[0];

      act(() => {
        render(
          <AddSecret
            secrets={[]}
            isOpen
            projects={[project]}
            onClose={onClose}
            onCreateSuccess={vi.fn()}
            defaultScope={SecretScope.PROJECT}
            scopeSelectDisabled={false}
            projectSelectDisabled={false}
            restrictToUseCases={[SecretUseCase.GENERIC]}
          />,
          { wrapper },
        );
      });

      await fillFormAndSubmit();

      await waitFor(() => {
        expect(createProjectSecret).toHaveBeenCalledWith(project.id, {
          name: 'my-app-secrets',
          manifest: mockValidExternalSecretYAML,
          type: SecretType.EXTERNAL_SECRET,
          useCase: SecretUseCase.GENERIC,
          scope: SecretScope.PROJECT,
          projectIds: [project.id],
        });
        expect(onClose).toHaveBeenCalled();
      });
    });
  });
});
