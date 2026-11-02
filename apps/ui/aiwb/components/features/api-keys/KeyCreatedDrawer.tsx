// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ActionButton,
  Alert,
  CopySnippet,
  DrawerBody,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerPrimitive as Drawer,
  Input,
} from '@amdenterpriseai/components';
import { useTranslation } from 'next-i18next';

import type { components } from '@/types/api';

import { useSystemToast } from '@amdenterpriseai/hooks';

type ApiKeyWithFullKey = components['schemas']['ApiKeyWithFullKey'];

interface KeyCreatedDrawerProps {
  isOpen: boolean;
  apiKey: ApiKeyWithFullKey | null;
  onClose: () => void;
}

export const KeyCreatedDrawer: React.FC<KeyCreatedDrawerProps> = ({
  isOpen,
  apiKey,
  onClose,
}) => {
  const { t } = useTranslation('api-keys');
  const { toast } = useSystemToast();

  if (!apiKey) return null;

  return (
    <Drawer isOpen={isOpen} onClose={onClose}>
      <DrawerContent>
        <DrawerHeader>{t('form.keyCreated.title')}</DrawerHeader>

        <DrawerBody>
          <div className="flex flex-col gap-4">
            {/* Description */}
            <p className="text-sm text-foreground">
              {t('form.keyCreated.description')}
            </p>

            {/* Warning Section */}
            <Alert
              status="warning"
              description={t('form.keyCreated.warning')}
            />

            {/* Name Field */}

            <CopySnippet
              label={t('form.keyCreated.field.name.label')}
              value={apiKey.displayName}
              hideCopyButton
            />

            <CopySnippet
              label={t('form.keyCreated.field.key.label')}
              value={apiKey.fullKey}
              onCopySuccess={() =>
                toast.success(t('form.keyCreated.notification.copySuccess'))
              }
              onCopyError={() =>
                toast.error(t('form.keyCreated.notification.copyError'))
              }
            />
          </div>
        </DrawerBody>

        <DrawerFooter className="justify-end">
          <ActionButton primary onPress={onClose}>
            {t('form.keyCreated.action.done')}
          </ActionButton>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
};

export default KeyCreatedDrawer;
