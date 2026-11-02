// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { describe, expect, it, vi } from 'vitest';

import { RuntimeProfileAcceleratorFields } from '@/components/features/models/runtime-profile/RuntimeProfileAcceleratorFields';
import type { ClusterAccelerator } from '@/types/cluster';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const translations: Record<string, string> = {
        'customModels.import.steps.runtime.catalog.modelAccelerators.EPYC_ZEN4':
          'AMD EPYC Zen 4',
      };
      if (key in translations) {
        return translations[key];
      }
      if (key.endsWith('.modelAccelerator') && options?.model) {
        return `Accelerator ${String(options.model)}`;
      }
      return key;
    },
  }),
}));

vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const React = await import('react');
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();

  const FormSelectMock = ({
    form,
    name,
    children,
    isDisabled,
    ...rest
  }: any) => {
    const testId = rest['data-testid'];
    useEffect(() => {
      form?.register(name);
    }, [form, name]);
    const flatItems = React.Children.toArray(children).flatMap((child: any) => {
      if (
        React.isValidElement<{ children?: unknown }>(child) &&
        child.type === React.Fragment
      ) {
        return React.Children.toArray(child.props.children as ReactNode);
      }
      return [child];
    });
    const clickableItems = flatItems.map((child: any) => {
      if (!React.isValidElement(child)) return child;
      const itemKey = String(child.key ?? '');
      const normalizedItemKey = itemKey.includes('$')
        ? itemKey.slice(itemKey.lastIndexOf('$') + 1)
        : itemKey.replace(/^\./, '');
      return React.cloneElement(child as ReactElement<any>, {
        onItemSelect: () => {
          if (!isDisabled) {
            form?.setValue(name, normalizedItemKey, {
              shouldValidate: true,
              shouldDirty: true,
            });
          }
        },
      });
    });
    return (
      <>
        <button type="button" data-testid={testId}>
          {String(form?.watch(name) ?? '')}
        </button>
        <div data-testid={testId ? `${testId}-items` : undefined}>
          {clickableItems}
        </div>
      </>
    );
  };
  FormSelectMock.displayName = 'FormSelect';

  const SelectItemMock = ({ children, onItemSelect, ...rest }: any) => (
    <button type="button" role="option" onClick={onItemSelect} {...rest}>
      {children}
    </button>
  );
  SelectItemMock.displayName = 'SelectItem';

  const FormInputMock = ({ form, name, ...rest }: any) => {
    useEffect(() => {
      form?.register(name);
    }, [form, name]);
    return <input data-testid={rest['data-testid']} />;
  };
  FormInputMock.displayName = 'FormInput';

  return {
    ...actual,
    FormSelect: FormSelectMock,
    SelectItem: SelectItemMock,
    FormInput: FormInputMock,
  };
});

type FormValues = {
  acceleratorType: string;
  accelerator: string;
  acceleratorCount: number;
};

const accelerators: ClusterAccelerator[] = [
  {
    acceleratorType: 'gpu',
    acceleratorVendor: 'amd',
    deviceId: '74a1',
    productName: 'AMD Instinct MI300X',
    allocatableCount: 8,
    acceleratorModel: 'MI300X',
  },
  {
    acceleratorType: 'cpu',
    acceleratorVendor: 'amd',
    deviceId: 'cpu-epyc',
    productName: '',
    allocatableCount: 96,
    acceleratorModel: 'EPYC_ZEN4',
  },
];

function Harness() {
  const form = useForm<FormValues>({
    defaultValues: {
      acceleratorType: 'gpu',
      accelerator: '',
      acceleratorCount: 1,
    },
  });
  return (
    <RuntimeProfileAcceleratorFields<FormValues>
      form={form}
      accelerators={accelerators}
      acceleratorCounts={[1, 2, 4, 8]}
      acceleratorTypeField="acceleratorType"
      acceleratorField="accelerator"
      acceleratorCountField="acceleratorCount"
      acceleratorTypeLabel="Accelerator type"
      acceleratorTypePlaceholder="Pick type"
      acceleratorLabel="Accelerator"
      acceleratorPlaceholder="Pick model"
      acceleratorCountLabel="Count"
    />
  );
}

describe('RuntimeProfileAcceleratorFields', () => {
  it('derives accelerator type options from accelerators API data', () => {
    render(<Harness />);
    const typeItems = screen.getByTestId(
      'custom-model-import-accelerator-type-items',
    );
    expect(
      within(typeItems).getByRole('option', { name: 'GPU' }),
    ).toBeInTheDocument();
    expect(
      within(typeItems).getByRole('option', { name: 'CPU' }),
    ).toBeInTheDocument();
  });

  it('filters accelerator models when accelerator type changes', () => {
    render(<Harness />);
    const typeItems = screen.getByTestId(
      'custom-model-import-accelerator-type-items',
    );
    fireEvent.click(within(typeItems).getByRole('option', { name: 'CPU' }));

    const acceleratorItems = screen.getByTestId(
      'custom-model-import-accelerator-items',
    );
    expect(
      within(acceleratorItems).getByRole('option', { name: 'AMD EPYC Zen 4' }),
    ).toBeInTheDocument();
    expect(
      within(acceleratorItems).queryByRole('option', {
        name: 'AMD Instinct MI300X',
      }),
    ).not.toBeInTheDocument();
  });
});
