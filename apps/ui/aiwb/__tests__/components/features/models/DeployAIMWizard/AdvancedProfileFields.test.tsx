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
import React from 'react';
import { useForm, FormProvider } from 'react-hook-form';
import { vi } from 'vitest';

import { AdvancedProfileFields } from '@/components/features/models/DeployAIMWizard/AdvancedProfileFields';
import type { DeployAIMFormValues } from '@/components/features/models/DeployAIMWizard/types';
import { ADVANCED_PARAM_AUTOMATIC } from '@/lib/app/aims/filterProfilesByAdvancedParams';
import type { AIMClusterProfile } from '@/types/aims';
import wrapper from '@/__tests__/ProviderWrapper';

import { createMockProfile, formValues } from './fixtures';

const mockProfiles: AIMClusterProfile[] = [
  createMockProfile(
    { acceleratorModel: 'MI300X', acceleratorCount: 2, precision: 'fp16' },
    'profile-latency',
  ),
  createMockProfile(
    {
      acceleratorModel: 'MI250X',
      acceleratorCount: 1,
      metric: 'throughput',
      precision: 'bf16',
    },
    'profile-throughput',
  ),
];

const defaultAdvancedOptions = {
  optimizationClasses: ['optimized'],
  gpuModels: ['MI250X', 'MI300X'],
  precisions: ['bf16', 'fp16'],
  gpuCounts: ['1', '2'],
  profiles: mockProfiles,
};

const FormWrapper = ({
  defaultValues,
  filteredProfiles = mockProfiles,
  noProfileMatches = false,
  children,
}: {
  defaultValues?: Partial<DeployAIMFormValues>;
  filteredProfiles?: AIMClusterProfile[];
  noProfileMatches?: boolean;
  children?: (
    form: ReturnType<typeof useForm<DeployAIMFormValues>>,
  ) => React.ReactNode;
}) => {
  const form = useForm<DeployAIMFormValues>({
    defaultValues: {
      ...formValues,
      optimizationClass: ADVANCED_PARAM_AUTOMATIC,
      gpuModel: ADVANCED_PARAM_AUTOMATIC,
      precision: ADVANCED_PARAM_AUTOMATIC,
      gpuCount: ADVANCED_PARAM_AUTOMATIC,
      profileName: ADVANCED_PARAM_AUTOMATIC,
      ...defaultValues,
    },
    shouldUnregister: true,
  });

  return (
    <FormProvider {...form}>
      <AdvancedProfileFields
        form={form}
        advancedProfileOptions={defaultAdvancedOptions}
        filteredProfiles={filteredProfiles}
        noProfileMatches={noProfileMatches}
      />
      {children?.(form)}
    </FormProvider>
  );
};

describe('AdvancedProfileFields', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the four filter selects and profile table', () => {
    render(<FormWrapper />, { wrapper });

    expect(
      screen.getByRole('button', {
        name: /deployAIM\.fields\.advancedProfileParams\.optimizationClass/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole('button', {
        name: /deployAIM\.fields\.advancedProfileParams\.gpu$/,
      }).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole('button', {
        name: /deployAIM\.fields\.advancedProfileParams\.precision/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: /deployAIM\.fields\.advancedProfileParams\.gpuCount/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('deployAimAdvancedProfileTable'),
    ).toBeInTheDocument();
  });

  it('renders sortable column headers and profile rows', () => {
    render(<FormWrapper />, { wrapper });

    expect(
      screen.getByRole('columnheader', {
        name: /deployAIM\.fields\.advancedProfileParams\.gpu/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', {
        name: /deployAIM\.fields\.advancedProfileParams\.precision/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', {
        name: /deployAIM\.fields\.advancedProfileParams\.metric/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', {
        name: /deployAIM\.fields\.advancedProfileParams\.class/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('MI300X × 2')).toBeInTheDocument();
    expect(screen.getByText('MI250X × 1')).toBeInTheDocument();
    expect(
      screen.getByRole('radio', {
        name: 'deployAIM.fields.advancedProfileParams.automaticSelection',
      }),
    ).toBeChecked();
  });

  it('selects Automatic by default when profileName is ADVANCED_PARAM_AUTOMATIC', () => {
    render(<FormWrapper />, { wrapper });

    expect(
      screen.getByRole('radio', {
        name: 'deployAIM.fields.advancedProfileParams.automaticSelection',
      }),
    ).toBeChecked();
    expect(screen.getByRole('radio', { name: /MI300X × 2/ })).not.toBeChecked();
  });

  it('updates optimizationClass when a filter select option is chosen', async () => {
    let formRef: ReturnType<typeof useForm<DeployAIMFormValues>> | undefined;

    render(
      <FormWrapper>
        {(form) => {
          formRef = form;
          return null;
        }}
      </FormWrapper>,
      { wrapper },
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /deployAIM\.fields\.advancedProfileParams\.optimizationClass/,
        }),
      );
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('option', { name: 'optimized' }));
    });

    await waitFor(() => {
      expect(formRef?.getValues('optimizationClass')).toBe('optimized');
    });
  });

  it('updates profileName when a profile row is clicked', async () => {
    let formRef: ReturnType<typeof useForm<DeployAIMFormValues>> | undefined;

    render(
      <FormWrapper>
        {(form) => {
          formRef = form;
          return null;
        }}
      </FormWrapper>,
      { wrapper },
    );

    const profileRow = screen.getByRole('row', { name: /MI300X × 2/ });
    await act(async () => {
      fireEvent.click(profileRow);
    });

    await waitFor(() => {
      expect(formRef?.getValues('profileName')).toBe('profile-latency');
    });
  });

  it('updates profileName when a profile radio is selected', async () => {
    let formRef: ReturnType<typeof useForm<DeployAIMFormValues>> | undefined;

    render(
      <FormWrapper>
        {(form) => {
          formRef = form;
          return null;
        }}
      </FormWrapper>,
      { wrapper },
    );

    const profileRadio = screen.getByRole('radio', {
      name: /MI300X × 2/,
    });
    await act(async () => {
      fireEvent.click(profileRadio);
    });

    await waitFor(() => {
      expect(formRef?.getValues('profileName')).toBe('profile-latency');
    });
  });

  it('reorders profile rows when a sortable column header is clicked', async () => {
    render(<FormWrapper />, { wrapper });

    const getProfileRowTexts = () =>
      screen
        .getAllByRole('row')
        .slice(2)
        .map((row) => row.textContent ?? '');

    expect(getProfileRowTexts()[0]).toContain('MI250X × 1');
    expect(getProfileRowTexts()[1]).toContain('MI300X × 2');

    await act(async () => {
      fireEvent.click(
        screen.getByRole('columnheader', {
          name: /deployAIM\.fields\.advancedProfileParams\.precision/,
        }),
      );
    });

    await waitFor(() => {
      const rows = getProfileRowTexts();
      expect(rows[0]).toContain('bf16');
      expect(rows[1]).toContain('fp16');
    });
  });

  it('persists filter values when fields remount after hiding', async () => {
    let formRef: ReturnType<typeof useForm<DeployAIMFormValues>> | undefined;

    const ToggleWrapper = () => {
      const [showAdvanced, setShowAdvanced] = React.useState(true);
      const form = useForm<DeployAIMFormValues>({
        defaultValues: {
          ...formValues,
          optimizationClass: ADVANCED_PARAM_AUTOMATIC,
          gpuModel: ADVANCED_PARAM_AUTOMATIC,
          precision: ADVANCED_PARAM_AUTOMATIC,
          gpuCount: ADVANCED_PARAM_AUTOMATIC,
          profileName: ADVANCED_PARAM_AUTOMATIC,
        },
        shouldUnregister: true,
      });
      formRef = form;

      return (
        <FormProvider {...form}>
          <button type="button" onClick={() => setShowAdvanced((v) => !v)}>
            toggle-advanced
          </button>
          {showAdvanced ? (
            <AdvancedProfileFields
              form={form}
              advancedProfileOptions={defaultAdvancedOptions}
              filteredProfiles={mockProfiles}
              noProfileMatches={false}
            />
          ) : null}
        </FormProvider>
      );
    };

    render(<ToggleWrapper />, { wrapper });

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /deployAIM\.fields\.advancedProfileParams\.optimizationClass/,
        }),
      );
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('option', { name: 'optimized' }));
    });

    await waitFor(() => {
      expect(formRef?.getValues('optimizationClass')).toBe('optimized');
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'toggle-advanced' }));
    });

    expect(
      screen.queryByTestId('deployAimAdvancedProfileTable'),
    ).not.toBeInTheDocument();
    expect(formRef?.getValues('optimizationClass')).toBe('optimized');

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'toggle-advanced' }));
    });

    await waitFor(() => {
      expect(
        screen.getByTestId('deployAimAdvancedProfileTable'),
      ).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /deployAIM\.fields\.advancedProfileParams\.optimizationClass/,
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'optimized' })).toHaveAttribute(
        'aria-selected',
        'true',
      );
    });
  });
});
