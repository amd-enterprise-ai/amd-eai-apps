// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Checkbox,
  Divider,
  DrawerBody,
  DrawerContent,
  DrawerHeader,
  DrawerPrimitive as Drawer,
  Slider,
  Textarea,
  Tooltip,
} from '@amdenterpriseai/components';
import { IconInfoCircle } from '@tabler/icons-react';
import React from 'react';

import { useTranslation } from 'next-i18next';
import { InferenceSettings } from '@/types/models';
import type { Workload } from '@/types/workloads';

interface Props {
  showSyncSettings: boolean;
  settings: InferenceSettings;
  onSettingsChange: (settings: InferenceSettings) => void;
  syncSettings: boolean;
  onSyncSettingsChange: (syncSettings: boolean) => void;
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  selectedModelWorkload?: Workload;
}

const SettingsDrawer: React.FC<Props> = ({
  settings,
  onSettingsChange,
  showSyncSettings,
  syncSettings,
  onSyncSettingsChange,
  selectedModelWorkload,
  isOpen,
  onOpenChange,
}) => {
  const { t } = useTranslation('chat');

  return (
    <Drawer isOpen={isOpen} onOpenChange={onOpenChange} radius="none" size="sm">
      <DrawerContent>
        <DrawerHeader>{t('modelSettings.title')}</DrawerHeader>
        {selectedModelWorkload?.displayName && (
          <div className="text-muted max-w-80 text-sm font-light text-nowrap truncate px-6 pb-2">
            {selectedModelWorkload.displayName}
          </div>
        )}
        <Divider />
        <DrawerBody className="p-6">
          <div className="w-full">
            {showSyncSettings && (
              <div className="flex justify-between items-center border-b pb-4 mb-4 dark:border-default">
                <span className="text-sm text-foreground dark:text-muted">
                  {t('modelSettings.syncSettings.description')}
                </span>
                <Checkbox
                  isSelected={syncSettings}
                  onChange={(e) => onSyncSettingsChange(e.target.checked)}
                >
                  {t('modelSettings.syncSettings.label')}
                </Checkbox>
              </div>
            )}

            <Slider
              label={
                <div className="flex items-center gap-1">
                  {t('modelSettings.temperature.label')}
                  <Tooltip
                    classNames={{ content: 'max-w-sm' }}
                    content={t('modelSettings.temperature.tooltip')}
                  >
                    <button
                      aria-label={t('modelSettings.temperature.tooltip')}
                      type="button"
                      className="inline-flex cursor-pointer rounded-small border-0 bg-transparent p-0 text-muted outline-offset-2 hover:opacity-80"
                    >
                      <IconInfoCircle aria-hidden size={16} />
                    </button>
                  </Tooltip>
                </div>
              }
              aria-label={t('modelSettings.temperature.changeLabel')}
              getValue={(v) => String(v)}
              value={settings.temperature}
              onChange={(value) =>
                typeof value == 'number' &&
                onSettingsChange({ ...settings, temperature: value })
              }
              minValue={0}
              maxValue={1}
              step={0.05}
              className="py-4 first:pt-0"
            />

            <Slider
              label={
                <div className="flex items-center gap-1">
                  {t('modelSettings.frequencyPenalty.label')}
                  <Tooltip
                    classNames={{ content: 'max-w-sm' }}
                    content={t('modelSettings.frequencyPenalty.tooltip')}
                  >
                    <button
                      aria-label={t('modelSettings.frequencyPenalty.tooltip')}
                      type="button"
                      className="inline-flex cursor-pointer rounded-small border-0 bg-transparent p-0 text-muted outline-offset-2 hover:opacity-80"
                    >
                      <IconInfoCircle aria-hidden size={16} />
                    </button>
                  </Tooltip>
                </div>
              }
              aria-label={t('modelSettings.frequencyPenalty.changeLabel')}
              getValue={(v) => String(v)}
              value={settings.frequencyPenalty}
              onChange={(value) =>
                typeof value == 'number' &&
                onSettingsChange({ ...settings, frequencyPenalty: value })
              }
              minValue={-2}
              maxValue={2}
              step={0.05}
              className="py-4"
            />

            <Slider
              label={
                <div className="flex items-center gap-1">
                  {t('modelSettings.presencePenalty.label')}
                  <Tooltip
                    classNames={{ content: 'max-w-sm' }}
                    content={t('modelSettings.presencePenalty.tooltip')}
                  >
                    <button
                      aria-label={t('modelSettings.presencePenalty.tooltip')}
                      type="button"
                      className="inline-flex cursor-pointer rounded-small border-0 bg-transparent p-0 text-muted outline-offset-2 hover:opacity-80"
                    >
                      <IconInfoCircle aria-hidden size={16} />
                    </button>
                  </Tooltip>
                </div>
              }
              aria-label={t('modelSettings.presencePenalty.changeLabel')}
              getValue={(v) => String(v)}
              value={settings.presencePenalty}
              onChange={(value) =>
                typeof value == 'number' &&
                onSettingsChange({ ...settings, presencePenalty: value })
              }
              minValue={-2}
              maxValue={2}
              step={0.05}
              className="py-4"
            />

            <div className="flex flex-col gap-3 py-4">
              <div className="flex items-center gap-1">
                <span className="text-small">
                  {t('modelSettings.systemPrompt.label')}
                </span>
                <Tooltip
                  classNames={{ content: 'max-w-sm' }}
                  content={t('modelSettings.systemPrompt.tooltip')}
                >
                  <button
                    type="button"
                    aria-label={t('modelSettings.systemPrompt.tooltip')}
                    className="inline-flex cursor-pointer rounded-small border-0 bg-transparent p-0 text-muted outline-offset-2 hover:opacity-80"
                  >
                    <IconInfoCircle aria-hidden size={16} />
                  </button>
                </Tooltip>
              </div>
              <Textarea
                aria-label={t('modelSettings.systemPrompt.label')}
                placeholder={t('modelSettings.systemPrompt.placeholder')}
                value={settings.systemPrompt}
                onChange={(e) =>
                  onSettingsChange({
                    ...settings,
                    systemPrompt: e.target.value,
                  })
                }
                minRows={6}
                onKeyDown={(e) => e.stopPropagation()}
              />
            </div>
          </div>
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
};

export default SettingsDrawer;
