// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { Mock, vi } from 'vitest';

import { useRuntimeProfileCatalog } from '@/hooks/useRuntimeProfileCatalog';
import {
  customModelToAggregatedAIM,
  getCustomModel,
  listCustomModels,
  patchCustomModel,
} from '@/lib/app/custom-models';
import { onboardModel, previewModelSource } from '@/lib/app/model-import';
import { fetchProjectSecrets } from '@/lib/app/secrets';
import { fetchProjectStorages } from '@/lib/app/storages';
import type { components } from '@/types/api';

type CustomModelResponse = components['schemas']['CustomModelResponse'];

import CustomModelImportPage from '@/components/features/models/CustomModelImport';

import wrapper from '@/__tests__/ProviderWrapper';

vi.mock('@/hooks/useRuntimeProfileCatalog', () => ({
  useRuntimeProfileCatalog: vi.fn(),
}));

vi.mock('@/lib/app/model-import', async (importOriginal) => ({
  ...(await importOriginal()),
  previewModelSource: vi.fn(),
  onboardModel: vi.fn(),
}));

vi.mock('@/lib/app/custom-models', async (importOriginal) => ({
  ...(await importOriginal()),
  getCustomModel: vi.fn(),
  patchCustomModel: vi.fn(),
  listCustomModels: vi.fn(),
}));

vi.mock('@/lib/app/secrets', async (importOriginal) => ({
  ...(await importOriginal()),
  fetchProjectSecrets: vi.fn(),
}));

vi.mock('@/lib/app/storages', async (importOriginal) => ({
  ...(await importOriginal()),
  fetchProjectStorages: vi.fn(),
  createProjectStorage: vi.fn(),
}));

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => ({
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }),
}));

const catalogFixture = {
  imageFamilies: [
    {
      familyId: 'automatic',
      displayName: 'Automatic',
      repository: null,
      tags: [],
    },
    {
      familyId: 'aim-base',
      displayName: 'aim-base',
      repository: 'amdenterpriseai/aim-base',
      tags: ['0.11'],
    },
  ],
  accelerators: [
    {
      acceleratorType: 'gpu',
      acceleratorVendor: 'amd',
      deviceId: '74a1',
      productName: 'AMD Instinct MI300X',
      allocatableCount: 8,
      acceleratorModel: 'MI300X',
    },
  ],
  runtimeOptions: null,
  isLoading: false,
  isError: false,
  error: null,
  invalidateCatalog: vi.fn(),
};

const previewResponse = {
  sourceType: 'huggingFace' as const,
  repoId: 'meta-llama/Llama-3',
  revision: 'main',
  sha: 'abc123',
  displayName: 'Llama 3',
  description: 'Llama family base model',
  tags: ['llama', 'text-generation'],
  pipelineTag: 'text-generation',
  gated: false,
  hfTokenRecommended: false,
  weightFiles: [
    { path: 'model.safetensors', sizeBytes: 1024, role: 'primary' as const },
    { path: 'config.json', sizeBytes: 128, role: 'config' as const },
  ],
  layoutHint: 'safetensors',
};

/** Build an AggregatedAIM (as listCustomModels returns) with a given display name. */
const aggregatedCustomModel = (displayName: string, resourceName: string) =>
  customModelToAggregatedAIM({
    metadata: {
      name: resourceName,
      namespace: 'project1',
      labels: { 'aiwb.apps.eai.amd.com/model-source-type': 'custom' },
      annotations: {
        'aiwb.apps.eai.amd.com/model-display-name': displayName,
        'aiwb.apps.eai.amd.com/canonical-repo-id': 'some/repo',
        'airm.silogen.ai/revision': 'main',
      },
      creationTimestamp: '2026-06-08T21:00:00Z',
    },
    spec: { aimId: 'some/repo', image: '', modelSources: [], profiles: null },
    phase: {
      state: 'Ready',
      status: 'Ready',
      templateReady: true,
      artifactPhase: null,
      artifactLastError: null,
    },
    profiles: [],
  });

describe('CustomModelImportPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (useRuntimeProfileCatalog as Mock).mockReturnValue(catalogFixture);
    (fetchProjectSecrets as Mock).mockResolvedValue({ data: [] });
    (previewModelSource as Mock).mockResolvedValue(previewResponse);
    (onboardModel as Mock).mockResolvedValue(undefined);
    (listCustomModels as Mock).mockResolvedValue([]);
  });

  const renderPage = () => render(<CustomModelImportPage />, { wrapper });

  const SOURCE_PLACEHOLDER = 'fields.source.placeholder';
  const DISPLAY_NAME_PLACEHOLDER = 'fields.displayName.placeholder';

  const enterSource = async (value: string) => {
    const sourceInput = screen.getByPlaceholderText(SOURCE_PLACEHOLDER);
    await act(async () => {
      fireEvent.change(sourceInput, { target: { value } });
    });
  };

  const clickNextOnSource = async () => {
    await act(async () => {
      fireEvent.click(screen.getByTestId('custom-model-import-next-source'));
    });
  };

  const advanceToRuntimeStep = async () => {
    await enterSource('https://huggingface.co/google/gemma-3-1b-it');
    await clickNextOnSource();
    const displayNameInput = await screen.findByPlaceholderText(
      DISPLAY_NAME_PLACEHOLDER,
    );
    await act(async () => {
      fireEvent.change(displayNameInput, {
        target: { value: 'test-custom-model' },
      });
    });
    await act(async () => {
      fireEvent.click(
        screen.getByTestId('custom-model-import-next-information'),
      );
    });
    await screen.findByTestId('custom-model-import-submit');
  };

  it('renders the wizard page rooted with the source step input', async () => {
    await act(async () => {
      renderPage();
    });
    expect(screen.getByTestId('custom-model-import-page')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(SOURCE_PLACEHOLDER)).toBeInTheDocument();
  });

  it('refuses to preview when the source is empty', async () => {
    await act(async () => {
      renderPage();
    });
    await clickNextOnSource();
    expect(previewModelSource).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText(SOURCE_PLACEHOLDER)).toBeInTheDocument();
  });

  it('previews the source and advances to the information step', async () => {
    await act(async () => {
      renderPage();
    });
    await enterSource('meta-llama/Llama-3');
    await clickNextOnSource();
    await waitFor(() => {
      expect(previewModelSource).toHaveBeenCalledWith('project1', {
        sourceType: 'huggingFace',
        source: 'meta-llama/Llama-3',
      });
    });
    await screen.findByPlaceholderText(DISPLAY_NAME_PLACEHOLDER);
  });

  it('seeds the display name from the model source preview', async () => {
    await act(async () => {
      renderPage();
    });
    await enterSource('meta-llama/Llama-3');
    await clickNextOnSource();
    const displayNameInput = await screen.findByTestId(
      'custom-model-import-display-name',
    );
    await waitFor(() => {
      expect(displayNameInput).toHaveValue('Llama 3');
    });
  });

  it('requires display name before advancing to the runtime step', async () => {
    await act(async () => {
      renderPage();
    });
    await enterSource('meta-llama/Llama-3');
    await clickNextOnSource();
    const displayNameInput = await screen.findByTestId(
      'custom-model-import-display-name',
    );
    // Clear the value seeded from the preview to exercise the required rule.
    await act(async () => {
      fireEvent.change(displayNameInput, { target: { value: '' } });
      fireEvent.blur(displayNameInput);
    });
    await act(async () => {
      fireEvent.click(
        screen.getByTestId('custom-model-import-next-information'),
      );
    });
    expect(
      screen.queryByTestId('custom-model-import-submit'),
    ).not.toBeInTheDocument();
  });

  it('accepts a free-form display name with spaces, uppercase, and punctuation', async () => {
    await act(async () => {
      renderPage();
    });
    await enterSource('meta-llama/Llama-3');
    await clickNextOnSource();
    const displayNameInput = await screen.findByTestId(
      'custom-model-import-display-name',
    );
    await act(async () => {
      fireEvent.change(displayNameInput, {
        target: { value: 'My Custom Model 3.1!' },
      });
      fireEvent.blur(displayNameInput);
    });
    await act(async () => {
      fireEvent.click(
        screen.getByTestId('custom-model-import-next-information'),
      );
    });
    expect(
      await screen.findByTestId('custom-model-import-submit'),
    ).toBeInTheDocument();
  });

  it('warns when the display name matches an existing custom model', async () => {
    // Existing model shares the preview-seeded display name ("Llama 3"), so the
    // information step must warn that saving would overwrite it.
    (listCustomModels as Mock).mockResolvedValue([
      aggregatedCustomModel('Llama 3', 'existing-llama-cr'),
    ]);
    await act(async () => {
      renderPage();
    });
    await enterSource('meta-llama/Llama-3');
    await clickNextOnSource();
    await screen.findByTestId('custom-model-import-display-name');
    expect(
      await screen.findByTestId('custom-model-import-duplicate-name-warning'),
    ).toBeInTheDocument();
  });

  it('does not warn when the display name is unique', async () => {
    (listCustomModels as Mock).mockResolvedValue([
      aggregatedCustomModel('Some Other Model', 'other-cr'),
    ]);
    await act(async () => {
      renderPage();
    });
    await enterSource('meta-llama/Llama-3');
    await clickNextOnSource();
    await screen.findByTestId('custom-model-import-display-name');
    // Ensure the existing-models query has resolved before asserting the
    // warning's absence, so the test cannot pass simply because the data has
    // not arrived yet.
    await waitFor(() => {
      expect(listCustomModels).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(
        screen.queryByTestId('custom-model-import-duplicate-name-warning'),
      ).not.toBeInTheDocument();
    });
  });

  describe('Tags help tooltip', () => {
    const goToInformationStep = async () => {
      await enterSource('meta-llama/Llama-3');
      await clickNextOnSource();
      await screen.findByTestId('custom-model-import-display-name');
    };

    it('renders a help tooltip trigger next to the Tags field', async () => {
      await act(async () => {
        renderPage();
      });
      await goToInformationStep();
      const trigger = screen.getByTestId('custom-model-import-tags-tooltip');
      expect(trigger).toBeInTheDocument();
      // The accessible label carries the tooltip copy so screen readers can
      // announce the guidance even without opening the tooltip.
      expect(trigger).toHaveAttribute('aria-label', 'fields.tags.tooltip');
    });

    it('reveals the tooltip content on keyboard focus', async () => {
      await act(async () => {
        renderPage();
      });
      await goToInformationStep();
      // The icon itself is not focusable; Tooltip wraps it in a trigger that
      // carries the button role, so keyboard users reach the guidance by tab.
      const trigger = screen.getByRole('button', {
        name: 'fields.tags.tooltip',
      });
      await act(async () => {
        trigger.focus();
      });
      expect(trigger).toHaveFocus();
      expect(await screen.findByRole('tooltip')).toHaveTextContent(
        'fields.tags.tooltip',
      );
    });

    it('allows onboarding with empty tags without warning or error', async () => {
      await act(async () => {
        renderPage();
      });
      await enterSource('meta-llama/Llama-3');
      await clickNextOnSource();
      const displayNameInput = await screen.findByTestId(
        'custom-model-import-display-name',
      );
      await act(async () => {
        fireEvent.change(displayNameInput, {
          target: { value: 'test-custom-model' },
        });
      });
      const tagsInput = screen.getByPlaceholderText('fields.tags.placeholder');
      await act(async () => {
        fireEvent.change(tagsInput, { target: { value: '' } });
        fireEvent.blur(tagsInput);
      });
      await act(async () => {
        fireEvent.click(
          screen.getByTestId('custom-model-import-next-information'),
        );
      });
      // Empty tags must not block progression to the runtime step.
      expect(
        await screen.findByTestId('custom-model-import-submit'),
      ).toBeInTheDocument();
    });
  });

  it('submits the default catalog image with precision and the canonical accelerator model', async () => {
    await act(async () => {
      renderPage();
    });
    await advanceToRuntimeStep();
    await act(async () => {
      fireEvent.click(screen.getByTestId('custom-model-import-submit'));
    });
    await waitFor(() => {
      expect(onboardModel).toHaveBeenCalledTimes(1);
    });
    const [project, body] = (onboardModel as Mock).mock.calls[0] as [
      string,
      {
        image?: string;
        customProfile?: { precision?: string; acceleratorModel?: string };
      },
    ];
    expect(project).toBe('project1');
    expect(body.image).toBe('amdenterpriseai/aim-base:0.11');
    // bf16 default must reach aim-engine, and the device id 74a1 must be sent
    // as the canonical MI300X so the profile is not stuck NotAvailable.
    expect(body.customProfile?.precision).toBe('bf16');
    expect(body.customProfile?.acceleratorModel).toBe('MI300X');
  });

  it('presets precision from the base-template runtime options', async () => {
    // Base template emits fp16; the wizard must align its precision selector
    // with that instead of its static bf16 default so onboarding sends what the
    // model will actually run at.
    (useRuntimeProfileCatalog as Mock).mockReturnValue({
      ...catalogFixture,
      runtimeOptions: {
        acceleratorModels: ['MI300X'],
        precisions: ['fp16'],
        acceleratorCounts: [1, 2, 4, 8],
        optimizationClasses: ['general'],
      },
    });
    await act(async () => {
      renderPage();
    });
    await advanceToRuntimeStep();
    await act(async () => {
      fireEvent.click(screen.getByTestId('custom-model-import-submit'));
    });
    await waitFor(() => {
      expect(onboardModel).toHaveBeenCalledTimes(1);
    });
    const body = (onboardModel as Mock).mock.calls[0][1] as {
      customProfile?: { precision?: string };
    };
    expect(body.customProfile?.precision).toBe('fp16');
  });

  it('defaults accelerator count to the first supported size when the static default is unsupported', async () => {
    // Base template supports {2,4,8} only; the static default of 1 is invalid,
    // so the wizard must snap to the first supported size and onboard with it.
    (useRuntimeProfileCatalog as Mock).mockReturnValue({
      ...catalogFixture,
      runtimeOptions: {
        acceleratorModels: ['MI300X'],
        precisions: ['fp16'],
        acceleratorCounts: [2, 4, 8],
        optimizationClasses: ['general'],
      },
    });
    await act(async () => {
      renderPage();
    });
    await advanceToRuntimeStep();
    await act(async () => {
      fireEvent.click(screen.getByTestId('custom-model-import-submit'));
    });
    await waitFor(() => {
      expect(onboardModel).toHaveBeenCalledTimes(1);
    });
    const body = (onboardModel as Mock).mock.calls[0][1] as {
      customProfile?: { acceleratorCount?: number };
    };
    expect(body.customProfile?.acceleratorCount).toBe(2);
  });

  it('parses engine args / env var YAML into canonical fields when provided', async () => {
    await act(async () => {
      renderPage();
    });
    await advanceToRuntimeStep();
    await act(async () => {
      fireEvent.change(
        screen.getByTestId('custom-model-import-engine-args-yaml'),
        {
          target: { value: 'attention-backend: TRITON_ATTN' },
        },
      );
      fireEvent.change(
        screen.getByTestId('custom-model-import-env-vars-yaml'),
        {
          target: { value: 'VLLM_ROCM_USE_AITER: 1' },
        },
      );
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('custom-model-import-submit'));
    });
    await waitFor(() => {
      expect(onboardModel).toHaveBeenCalledTimes(1);
    });
    const body = (onboardModel as Mock).mock.calls[0][1] as Record<
      string,
      {
        engineArgs?: Record<string, unknown>;
        engineEnv?: { name: string; value: string }[];
      }
    >;
    expect(body.customProfile?.engineArgs).toEqual({
      'attention-backend': 'TRITON_ATTN',
    });
    expect(body.customProfile?.engineEnv).toEqual([
      { name: 'VLLM_ROCM_USE_AITER', value: '1' },
    ]);
  });

  it('blocks submit when engine args YAML is invalid', async () => {
    await act(async () => {
      renderPage();
    });
    await advanceToRuntimeStep();
    await act(async () => {
      fireEvent.change(
        screen.getByTestId('custom-model-import-engine-args-yaml'),
        {
          target: { value: 'just a scalar, not a mapping' },
        },
      );
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('custom-model-import-submit'));
    });
    expect(onboardModel).not.toHaveBeenCalled();
  });

  it('disables submit while the runtime catalog is loading', async () => {
    (useRuntimeProfileCatalog as Mock).mockReturnValue({
      ...catalogFixture,
      isLoading: true,
    });
    await act(async () => {
      renderPage();
    });
    await advanceToRuntimeStep();
    expect(screen.getByTestId('custom-model-import-submit')).toBeDisabled();
  });

  it('disables submit when the accelerators catalog is empty', async () => {
    (useRuntimeProfileCatalog as Mock).mockReturnValue({
      ...catalogFixture,
      accelerators: [],
    });
    await act(async () => {
      renderPage();
    });
    await advanceToRuntimeStep();
    expect(screen.getByTestId('custom-model-import-submit')).toBeDisabled();
    await act(async () => {
      fireEvent.click(screen.getByTestId('custom-model-import-submit'));
    });
    expect(onboardModel).not.toHaveBeenCalled();
  });

  describe('S3 source', () => {
    const S3_SOURCE_PLACEHOLDER = 'fields.source.s3Placeholder';
    const S3_SECRET = {
      metadata: { name: 's3-creds', namespace: 'project1' },
      displayName: 'Team bucket credentials',
      useCase: 'S3',
    };

    const S3_STORAGE = {
      name: 's3-creds',
      type: 'S3',
      secretName: 's3-creds',
      spec: {},
    };

    const s3PreviewResponse = {
      ...previewResponse,
      sourceType: 's3' as const,
      repoId: 's3://my-bucket/models/llama',
      revision: 's3',
      sha: 's3',
      displayName: 'llama',
      description: '',
      tags: [],
    };

    const chooseSourceType = async (label: string) => {
      await act(async () => {
        fireEvent.click(screen.getByRole('radio', { name: label }));
      });
    };

    const chooseS3 = () => chooseSourceType('sourceTypes.s3.label');

    const enterS3Source = async (value: string) => {
      await act(async () => {
        fireEvent.change(screen.getByPlaceholderText(S3_SOURCE_PLACEHOLDER), {
          target: { value },
        });
      });
    };

    const selectS3Storage = async () => {
      const trigger = within(
        screen.getByTestId('project-s3-storage-selector'),
      ).getByRole('button');
      await waitFor(() => {
        expect(trigger).toBeEnabled();
      });
      await act(async () => {
        fireEvent.click(trigger);
      });
      const option = await screen.findByRole('option', {
        name: S3_STORAGE.name,
      });
      await act(async () => {
        fireEvent.click(option);
      });
    };

    beforeEach(() => {
      (fetchProjectSecrets as Mock).mockResolvedValue({ data: [S3_SECRET] });
      (fetchProjectStorages as Mock).mockResolvedValue({ data: [S3_STORAGE] });
      (previewModelSource as Mock).mockResolvedValue(s3PreviewResponse);
    });

    it('previews with the S3 secret and no Hugging Face token', async () => {
      await act(async () => {
        renderPage();
      });
      await chooseS3();
      await enterS3Source('s3://my-bucket/models/llama');
      await selectS3Storage();
      await clickNextOnSource();

      await waitFor(() => {
        expect(previewModelSource).toHaveBeenCalledWith('project1', {
          sourceType: 's3',
          source: 's3://my-bucket/models/llama',
          s3StorageName: 's3-creds',
        });
      });
      await screen.findByPlaceholderText(DISPLAY_NAME_PLACEHOLDER);
    });

    it('blocks preview until the source is a bucket URI with a prefix', async () => {
      await act(async () => {
        renderPage();
      });
      await chooseS3();
      await selectS3Storage();
      await enterS3Source('s3://my-bucket');
      await clickNextOnSource();
      expect(previewModelSource).not.toHaveBeenCalled();

      await enterS3Source('s3://my-bucket/models/llama');
      await clickNextOnSource();
      await waitFor(() => {
        expect(previewModelSource).toHaveBeenCalledTimes(1);
      });
    });

    it('blocks preview until a storage configuration is entered', async () => {
      await act(async () => {
        renderPage();
      });
      await chooseS3();
      await enterS3Source('s3://my-bucket/models/llama');
      await clickNextOnSource();
      expect(previewModelSource).not.toHaveBeenCalled();

      await selectS3Storage();
      await clickNextOnSource();
      await waitFor(() => {
        expect(previewModelSource).toHaveBeenCalledTimes(1);
      });
    });

    it('onboards with the S3 source type and credential', async () => {
      await act(async () => {
        renderPage();
      });
      await chooseS3();
      await enterS3Source('s3://my-bucket/models/llama');
      await selectS3Storage();
      await clickNextOnSource();

      const displayNameInput = await screen.findByPlaceholderText(
        DISPLAY_NAME_PLACEHOLDER,
      );
      await act(async () => {
        fireEvent.change(displayNameInput, { target: { value: 'llama-s3' } });
      });
      await act(async () => {
        fireEvent.click(
          screen.getByTestId('custom-model-import-next-information'),
        );
      });
      await screen.findByTestId('custom-model-import-submit');
      await act(async () => {
        fireEvent.click(screen.getByTestId('custom-model-import-submit'));
      });

      await waitFor(() => {
        expect(onboardModel).toHaveBeenCalledTimes(1);
      });
      const body = (onboardModel as Mock).mock.calls[0][1] as Record<
        string,
        unknown
      >;
      expect(body).toMatchObject({
        sourceType: 's3',
        s3StorageName: 's3-creds',
        repoId: 's3://my-bucket/models/llama',
        revision: 's3',
        sha: 's3',
      });
      expect(body).not.toHaveProperty('hfTokenSecretName');
    });

    it('clears the previous source and credential when switching source type', async () => {
      await act(async () => {
        renderPage();
      });
      await enterSource('meta-llama/Llama-3');
      await chooseS3();

      expect(screen.getByPlaceholderText(S3_SOURCE_PLACEHOLDER)).toHaveValue(
        '',
      );
      await enterS3Source('s3://my-bucket/models/llama');
      await selectS3Storage();

      await chooseSourceType('sourceTypes.huggingFace.label');
      expect(screen.getByPlaceholderText(SOURCE_PLACEHOLDER)).toHaveValue('');

      await enterSource('meta-llama/Llama-3');
      await clickNextOnSource();
      await waitFor(() => {
        expect(previewModelSource).toHaveBeenCalledWith('project1', {
          sourceType: 'huggingFace',
          source: 'meta-llama/Llama-3',
        });
      });
    });

    it('surfaces preview warnings without blocking the next step', async () => {
      (previewModelSource as Mock).mockResolvedValue({
        ...s3PreviewResponse,
        warnings: ['No tokenizer files found under the prefix.'],
      });
      await act(async () => {
        renderPage();
      });
      await chooseS3();
      await enterS3Source('s3://my-bucket/models/llama');
      await selectS3Storage();
      await clickNextOnSource();

      const warnings = await screen.findByTestId(
        'custom-model-import-preview-warnings',
      );
      expect(warnings).toHaveTextContent(
        'No tokenizer files found under the prefix.',
      );
      await act(async () => {
        fireEvent.click(
          screen.getByTestId('custom-model-import-next-information'),
        );
      });
      expect(
        await screen.findByTestId('custom-model-import-submit'),
      ).toBeInTheDocument();
    });
  });

  describe('edit mode', () => {
    const MODEL_ID = 'gemma3-1b-it-import-d41ec23c';

    const buildEditModel = (
      overrides: Partial<CustomModelResponse> = {},
    ): CustomModelResponse => ({
      metadata: {
        name: MODEL_ID,
        namespace: 'project1',
        labels: { 'aiwb.apps.eai.amd.com/model-source-type': 'custom' },
        annotations: {
          'aiwb.apps.eai.amd.com/model-display-name': 'gemma-3-1b-it',
          'aiwb.apps.eai.amd.com/canonical-repo-id': 'google/gemma-3-1b-it',
          'aiwb.apps.eai.amd.com/source-description': 'Gemma model',
          'aiwb.apps.eai.amd.com/source-tags': '["text-generation"]',
          'airm.silogen.ai/revision': 'main',
        },
        creationTimestamp: '2026-06-08T21:00:00Z',
      },
      spec: {
        aimId: 'google/gemma-3-1b-it',
        image: '',
        modelSources: [],
        profiles: {
          overrides: {
            image: 'amdenterpriseai/aim-base:0.11',
            modelSources: [
              { modelId: 'google/gemma-3-1b-it', sourceUri: 's3://bucket/w' },
            ],
          },
        },
      },
      phase: {
        state: 'Ready',
        status: 'Ready',
        templateReady: true,
        artifactPhase: null,
        artifactLastError: null,
      },
      status: undefined,
      profiles: [],
      ...overrides,
    });

    const renderEditPage = (model: CustomModelResponse = buildEditModel()) => {
      (getCustomModel as Mock).mockResolvedValue(model);
      (patchCustomModel as Mock).mockResolvedValue(undefined);
      return render(<CustomModelImportPage mode="edit" modelId={MODEL_ID} />, {
        wrapper,
      });
    };

    const editDisplayName = async (value: string) => {
      const input = await screen.findByTestId(
        'custom-model-import-display-name',
      );
      await act(async () => {
        fireEvent.change(input, { target: { value } });
        fireEvent.blur(input);
      });
    };

    const goToInformation = async () => {
      // Wait for the async model fetch + prefill to replace the loading spinner
      // with the (read-only) source step before advancing.
      const nextButton = await screen.findByTestId(
        'custom-model-import-next-source',
      );
      await act(async () => {
        fireEvent.click(nextButton);
      });
      await screen.findByTestId('custom-model-import-display-name');
    };

    const goToRuntime = async () => {
      await act(async () => {
        fireEvent.click(
          screen.getByTestId('custom-model-import-next-information'),
        );
      });
      await screen.findByTestId('custom-model-import-submit');
    };

    const setEngineArgs = async (value: string) => {
      await act(async () => {
        fireEvent.change(
          screen.getByTestId('custom-model-import-engine-args-yaml'),
          { target: { value } },
        );
      });
    };

    it('prefills the form and advances without calling preview', async () => {
      await act(async () => {
        renderEditPage();
      });
      await goToInformation();
      expect(
        screen.getByTestId('custom-model-import-display-name'),
      ).toHaveValue('gemma-3-1b-it');
      expect(previewModelSource).not.toHaveBeenCalled();
    });

    it('prefills engine args / env vars from persisted overrides', async () => {
      const withRuntime = buildEditModel({
        spec: {
          aimId: 'google/gemma-3-1b-it',
          image: '',
          modelSources: [],
          profiles: {
            overrides: {
              image: 'amdenterpriseai/aim-base:0.11',
              acceleratorModel: 'MI300X',
              precision: 'fp16',
              engineArgs: { 'max-model-len': 4096 },
              engineEnv: { VLLM_ROCM_USE_AITER: '1' },
            },
          },
        },
      });
      await act(async () => {
        renderEditPage(withRuntime);
      });
      await goToInformation();
      await goToRuntime();
      expect(
        screen.getByTestId('custom-model-import-engine-args-yaml'),
      ).toHaveValue('max-model-len: 4096');
      expect(
        screen.getByTestId('custom-model-import-env-vars-yaml'),
      ).toHaveValue('VLLM_ROCM_USE_AITER: "1"');
    });

    it('sends a metadata-only PATCH when only the display name changes', async () => {
      await act(async () => {
        renderEditPage();
      });
      await goToInformation();
      await editDisplayName('gemma-3-1b-it-v2');
      await goToRuntime();
      await act(async () => {
        fireEvent.click(screen.getByTestId('custom-model-import-submit'));
      });
      await waitFor(() => {
        expect(patchCustomModel).toHaveBeenCalledTimes(1);
      });
      const [project, modelId, body] = (patchCustomModel as Mock).mock
        .calls[0] as [string, string, Record<string, unknown>];
      expect(project).toBe('project1');
      expect(modelId).toBe(MODEL_ID);
      expect(body).toEqual({ displayName: 'gemma-3-1b-it-v2' });
    });

    it('allows metadata-only save when the accelerators catalog is empty', async () => {
      (useRuntimeProfileCatalog as Mock).mockReturnValue({
        ...catalogFixture,
        accelerators: [],
      });
      await act(async () => {
        renderEditPage();
      });
      await goToInformation();
      await editDisplayName('gemma-3-1b-it-v2');
      await goToRuntime();
      await act(async () => {
        fireEvent.click(screen.getByTestId('custom-model-import-submit'));
      });
      await waitFor(() => {
        expect(patchCustomModel).toHaveBeenCalledTimes(1);
      });
      const body = (patchCustomModel as Mock).mock.calls[0][2] as Record<
        string,
        unknown
      >;
      expect(body).toEqual({ displayName: 'gemma-3-1b-it-v2' });
    });

    it('allows a metadata-only save even when the runtime matrix is unusable', async () => {
      // The base emitted profiles but none resolves, so the runtime step is
      // blocked. A rename resolves no base profile and sends no runtime data, so
      // Save must stay enabled for a display-name-only edit.
      (useRuntimeProfileCatalog as Mock).mockReturnValue({
        ...catalogFixture,
        runtimeOptions: {
          acceleratorModels: ['MI300X'],
          precisions: ['fp16'],
          acceleratorCounts: [1],
          optimizationClasses: [],
          metrics: ['latency'],
          combinations: [],
          profilesAvailable: true,
        },
      });
      await act(async () => {
        renderEditPage();
      });
      await goToInformation();
      await editDisplayName('gemma-3-1b-it-v2');
      await goToRuntime();
      await act(async () => {
        fireEvent.click(screen.getByTestId('custom-model-import-submit'));
      });
      await waitFor(() => {
        expect(patchCustomModel).toHaveBeenCalledTimes(1);
      });
      const body = (patchCustomModel as Mock).mock.calls[0][2] as Record<
        string,
        unknown
      >;
      expect(body).toEqual({ displayName: 'gemma-3-1b-it-v2' });
    });

    it('sends a runtime-profile PATCH when only the runtime changes', async () => {
      await act(async () => {
        renderEditPage();
      });
      await goToInformation();
      await goToRuntime();
      await setEngineArgs('attention-backend: TRITON_ATTN');
      await act(async () => {
        fireEvent.click(screen.getByTestId('custom-model-import-submit'));
      });
      await waitFor(() => {
        expect(patchCustomModel).toHaveBeenCalledTimes(1);
      });
      const body = (patchCustomModel as Mock).mock.calls[0][2] as {
        displayName?: string;
        image?: string;
        customProfile?: Record<string, unknown>;
      };
      expect(body.displayName).toBeUndefined();
      expect(body.image).toBe('amdenterpriseai/aim-base:0.11');
      expect(body.customProfile).toMatchObject({
        imageFamilyId: 'aim-base',
        engineArgs: { 'attention-backend': 'TRITON_ATTN' },
      });
    });

    it('prefills precision from the annotation, not the pruned overrides fallback', async () => {
      // The AIMModel CRD prunes overrides.precision, so it is absent here; the
      // durable annotation carries the chosen 'fp8'. Without the annotation read
      // the prefill would fall back to 'bf16'. Changing engine args makes the
      // runtime dirty so the full profile (including the prefilled precision)
      // reaches the PATCH body.
      const withPrecisionAnnotation = buildEditModel({
        metadata: {
          name: MODEL_ID,
          namespace: 'project1',
          labels: { 'aiwb.apps.eai.amd.com/model-source-type': 'custom' },
          annotations: {
            'aiwb.apps.eai.amd.com/model-display-name': 'gemma-3-1b-it',
            'aiwb.apps.eai.amd.com/canonical-repo-id': 'google/gemma-3-1b-it',
            'airm.silogen.ai/revision': 'main',
            'aiwb.apps.eai.amd.com/precision': 'fp8',
          },
          creationTimestamp: '2026-06-08T21:00:00Z',
        },
      });
      await act(async () => {
        renderEditPage(withPrecisionAnnotation);
      });
      await goToInformation();
      await goToRuntime();
      await setEngineArgs('attention-backend: TRITON_ATTN');
      await act(async () => {
        fireEvent.click(screen.getByTestId('custom-model-import-submit'));
      });
      await waitFor(() => {
        expect(patchCustomModel).toHaveBeenCalledTimes(1);
      });
      const body = (patchCustomModel as Mock).mock.calls[0][2] as {
        customProfile?: { precision?: string };
      };
      expect(body.customProfile?.precision).toBe('fp8');
    });

    it('sends a combined PATCH when metadata and runtime both change', async () => {
      await act(async () => {
        renderEditPage();
      });
      await goToInformation();
      await editDisplayName('gemma-3-1b-it-v2');
      await goToRuntime();
      await setEngineArgs('attention-backend: TRITON_ATTN');
      await act(async () => {
        fireEvent.click(screen.getByTestId('custom-model-import-submit'));
      });
      await waitFor(() => {
        expect(patchCustomModel).toHaveBeenCalledTimes(1);
      });
      const body = (patchCustomModel as Mock).mock.calls[0][2] as {
        displayName?: string;
        image?: string;
        customProfile?: Record<string, unknown>;
      };
      expect(body.displayName).toBe('gemma-3-1b-it-v2');
      expect(body.image).toBe('amdenterpriseai/aim-base:0.11');
      expect(body.customProfile).toMatchObject({
        engineArgs: { 'attention-backend': 'TRITON_ATTN' },
      });
    });

    it('does not warn for the edited model own name but warns when renamed to another existing model', async () => {
      // The list includes the model being edited (its own name must not count)
      // plus a second model whose name the user renames into.
      (listCustomModels as Mock).mockResolvedValue([
        aggregatedCustomModel('gemma-3-1b-it', MODEL_ID),
        aggregatedCustomModel('taken-name', 'other-cr'),
      ]);
      await act(async () => {
        renderEditPage();
      });
      await goToInformation();
      expect(
        screen.queryByTestId('custom-model-import-duplicate-name-warning'),
      ).not.toBeInTheDocument();
      await editDisplayName('taken-name');
      expect(
        await screen.findByTestId('custom-model-import-duplicate-name-warning'),
      ).toBeInTheDocument();
    });

    it('blocks runtime editing until the profile is ready', async () => {
      const notReady = buildEditModel({
        phase: {
          state: 'Importing',
          status: 'Progressing',
          templateReady: false,
          artifactPhase: 'Progressing',
          artifactLastError: null,
        },
        profiles: [],
      });
      await act(async () => {
        renderEditPage(notReady);
      });
      await goToInformation();
      await goToRuntime();
      expect(
        screen.getByTestId('custom-model-import-runtime-disabled-notice'),
      ).toBeInTheDocument();
    });
  });
});
