// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import SettingsDrawer from '@/components/features/chat/SettingsDrawer';
import ProviderWrapper from '@/__tests__/ProviderWrapper';

import '@testing-library/jest-dom';

// Import mocks
import {
  mockInferenceSettings,
  mockInferenceSettingsExtreme,
} from '@/__mocks__/services/app/chat.data';
import { mockWorkloads } from '@/__mocks__/services/app/workloads.data';

describe('SettingsDrawer Component', () => {
  const defaultProps = {
    isOpen: true,
    settings: mockInferenceSettings,
    selectedModelWorkload: mockWorkloads[0], // Use first workload from mock data
    onOpenChange: vi.fn(),
    onSettingsChange: vi.fn(),
    showSyncSettings: true,
    syncSettings: false,
    onSyncSettingsChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Drawer Visibility and Structure', () => {
    it('renders the drawer when isOpen is true', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('modelSettings.title')).toBeInTheDocument();
    });

    it('does not render the drawer content when isOpen is false', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} isOpen={false} />
        </ProviderWrapper>,
      );

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('displays the selected model workload name', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
    });

    it('handles undefined selectedModelWorkload gracefully', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} selectedModelWorkload={undefined} />
        </ProviderWrapper>,
      );

      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  describe('Sync Settings', () => {
    it('shows sync settings checkbox when showSyncSettings is true', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer
            {...defaultProps}
            showSyncSettings={true}
            syncSettings={false}
          />
        </ProviderWrapper>,
      );

      expect(
        screen.getByLabelText('modelSettings.syncSettings.label'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('modelSettings.syncSettings.description'),
      ).toBeInTheDocument();
    });

    it('hides sync settings when showSyncSettings is false', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} showSyncSettings={false} />
        </ProviderWrapper>,
      );

      expect(
        screen.queryByLabelText('modelSettings.syncSettings.label'),
      ).not.toBeInTheDocument();
    });

    it('calls onSyncSettingsChange when sync checkbox is toggled', async () => {
      const user = userEvent.setup();

      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      const checkbox = screen.getByLabelText(
        'modelSettings.syncSettings.label',
      );
      await user.click(checkbox);

      expect(defaultProps.onSyncSettingsChange).toHaveBeenCalledWith(true);
    });

    it('reflects the current syncSettings state', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} syncSettings={true} />
        </ProviderWrapper>,
      );

      const checkbox = screen.getByLabelText(
        'modelSettings.syncSettings.label',
      );
      expect(checkbox).toBeChecked();
    });
  });

  describe('Temperature Slider', () => {
    it('displays the temperature slider with correct initial value', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(
        screen.getByText('modelSettings.temperature.label'),
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText('modelSettings.temperature.changeLabel'),
      ).toBeInTheDocument();
    });

    it('calls onSettingsChange when temperature slider is moved', async () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      const temperatureInput = screen.getByDisplayValue('0.5');

      fireEvent.change(temperatureInput, { target: { value: '0.7' } });

      expect(defaultProps.onSettingsChange).toHaveBeenCalled();
    });
  });

  describe('Frequency Penalty Slider', () => {
    it('displays the frequency penalty slider with correct initial value', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(
        screen.getByText('modelSettings.frequencyPenalty.label'),
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText('modelSettings.frequencyPenalty.changeLabel'),
      ).toBeInTheDocument();
    });

    it('calls onSettingsChange when frequency penalty slider is moved', async () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      const frequencyInput = screen.getByDisplayValue('0.2');

      fireEvent.change(frequencyInput, { target: { value: '0.5' } });

      expect(defaultProps.onSettingsChange).toHaveBeenCalled();
    });
  });

  describe('Presence Penalty Slider', () => {
    it('displays the presence penalty slider with correct initial value', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(
        screen.getByText('modelSettings.presencePenalty.label'),
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText('modelSettings.presencePenalty.changeLabel'),
      ).toBeInTheDocument();
    });

    it('calls onSettingsChange when presence penalty slider is moved', async () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      const presenceInput = screen.getByDisplayValue('0.1');

      fireEvent.change(presenceInput, { target: { value: '0.3' } });

      expect(defaultProps.onSettingsChange).toHaveBeenCalled();
    });
  });

  describe('System Prompt Textarea', () => {
    it('displays the system prompt textarea with correct initial value', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(
        screen.getByText('modelSettings.systemPrompt.label'),
      ).toBeInTheDocument();
      expect(
        screen.getByDisplayValue('Test system prompt'),
      ).toBeInTheDocument();
    });

    it('calls onSettingsChange when system prompt is changed', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );
      const textarea = screen.getByDisplayValue('Test system prompt');

      fireEvent.change(textarea, { target: { value: 'New system prompt' } });

      expect(defaultProps.onSettingsChange).toHaveBeenCalledWith({
        ...mockInferenceSettings,
        systemPrompt: 'New system prompt',
      });
    });

    it('shows placeholder when system prompt is empty', () => {
      const emptySettings = { ...mockInferenceSettings, systemPrompt: '' };

      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} settings={emptySettings} />
        </ProviderWrapper>,
      );

      expect(
        screen.getByPlaceholderText('modelSettings.systemPrompt.placeholder'),
      ).toBeInTheDocument();
    });
  });

  describe('Drawer Interactions', () => {
    it('calls onOpenChange when drawer state should change', async () => {
      const user = userEvent.setup();

      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      // Press Escape to close the drawer
      await user.keyboard('{Escape}');

      expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  describe('Settings Values Display', () => {
    it('displays all current settings values correctly', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(screen.getByText('0.5')).toBeInTheDocument(); // temperature
      expect(screen.getByText('0.2')).toBeInTheDocument(); // frequency penalty
      expect(screen.getByText('0.1')).toBeInTheDocument(); // presence penalty
      expect(
        screen.getByDisplayValue('Test system prompt'),
      ).toBeInTheDocument();
    });

    it('handles extreme slider values correctly', () => {
      const extremeSettings = {
        ...mockInferenceSettingsExtreme,
      };

      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} settings={extremeSettings} />
        </ProviderWrapper>,
      );

      expect(screen.getByText('1')).toBeInTheDocument(); // temperature
      expect(screen.getByText('-2')).toBeInTheDocument(); // frequency penalty
      expect(screen.getByText('2')).toBeInTheDocument(); // presence penalty
    });
  });

  describe('Accessibility', () => {
    it('has proper aria labels for all interactive elements', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(
        screen.getByLabelText('modelSettings.temperature.changeLabel'),
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText('modelSettings.frequencyPenalty.changeLabel'),
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText('modelSettings.presencePenalty.changeLabel'),
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText('modelSettings.systemPrompt.label'),
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText('modelSettings.syncSettings.label'),
      ).toBeInTheDocument();
      expect(screen.getByLabelText('Close')).toBeInTheDocument();
    });

    it('uses one dialog heading for the title; workload name is outside the heading', () => {
      render(
        <ProviderWrapper>
          <SettingsDrawer {...defaultProps} />
        </ProviderWrapper>,
      );

      const headings = screen.getAllByRole('heading');
      expect(headings).toHaveLength(1);
      expect(headings[0]).toHaveAccessibleName(/modelSettings\.title/);
      expect(
        within(headings[0] as HTMLElement).queryByText('Llama 7B Inference'),
      ).not.toBeInTheDocument();
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
    });
  });
});
