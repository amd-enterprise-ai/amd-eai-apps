// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';

import type { components } from '@/types/api';

import ModelDetailsModal from '@/components/features/models/ModelDetailsModal';

import { describe, expect, it, vi } from 'vitest';

const mockModel: components['schemas']['AIMModelResource'] = {
  metadata: {
    name: 'test-model-resource',
    creationTimestamp: '2023-01-02T00:00:00Z',
    labels: {
      'aiwb.apps.eai.amd.com/model-name': 'Test Model',
    },
  },
  spec: {
    image: '',
    profiles: {
      overrides: {
        modelSources: [
          {
            modelId: 'test-org/test-model',
            sourceUri: 'hf://test-org/test-model',
          },
        ],
      },
    },
  },
  status: {
    status: 'Ready',
  },
};

describe('ModelDetailsModal', () => {
  let onOpenChangeMock: ReturnType<typeof vi.fn<(isOpen: boolean) => void>>;

  beforeEach(() => {
    onOpenChangeMock = vi.fn<(isOpen: boolean) => void>();
  });

  it('should not render if isOpen is false', () => {
    render(
      <ModelDetailsModal
        isOpen={false}
        onOpenChange={onOpenChangeMock}
        model={mockModel}
      />,
    );
    expect(
      screen.queryByText('list.actions.details.modal.title'),
    ).not.toBeInTheDocument();
  });

  it('should render with default title if model is undefined but isOpen is true', () => {
    render(
      <ModelDetailsModal
        isOpen={true}
        onOpenChange={onOpenChangeMock}
        model={undefined}
      />,
    );
    expect(
      screen.getByText('list.actions.details.modal.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('list.actions.details.modal.modelNotFound'),
    ).toBeInTheDocument();
  });

  it('should render the modal with correct title when open and model is provided', () => {
    render(
      <ModelDetailsModal
        isOpen={true}
        onOpenChange={onOpenChangeMock}
        model={mockModel}
      />,
    );

    expect(
      screen.getByText('list.actions.details.modal.title'),
    ).toBeInTheDocument();
  });

  it('should display model name and resource name', () => {
    render(
      <ModelDetailsModal
        isOpen={true}
        onOpenChange={onOpenChangeMock}
        model={mockModel}
      />,
    );

    expect(screen.getByText('Test Model')).toBeInTheDocument();
    expect(screen.getByText('test-model-resource')).toBeInTheDocument();
  });

  it('should display the description when the source-description annotation is present', () => {
    const modelWithDescription: components['schemas']['AIMModelResource'] = {
      ...mockModel,
      metadata: {
        ...mockModel.metadata,
        annotations: {
          'aiwb.apps.eai.amd.com/source-description': 'A helpful description',
        },
      },
    };

    render(
      <ModelDetailsModal
        isOpen={true}
        onOpenChange={onOpenChangeMock}
        model={modelWithDescription}
      />,
    );

    expect(
      screen.getByText('list.actions.details.modal.fields.description'),
    ).toBeInTheDocument();
    expect(screen.getByText('A helpful description')).toBeInTheDocument();
  });

  it('should omit the description field when no description annotation is present', () => {
    render(
      <ModelDetailsModal
        isOpen={true}
        onOpenChange={onOpenChangeMock}
        model={mockModel}
      />,
    );

    expect(
      screen.queryByText('list.actions.details.modal.fields.description'),
    ).not.toBeInTheDocument();
  });

  it('should not render a footer close button', () => {
    render(
      <ModelDetailsModal
        isOpen={true}
        onOpenChange={onOpenChangeMock}
        model={mockModel}
      />,
    );

    expect(
      screen.queryByText('list.actions.details.modal.close'),
    ).not.toBeInTheDocument();
  });
});
