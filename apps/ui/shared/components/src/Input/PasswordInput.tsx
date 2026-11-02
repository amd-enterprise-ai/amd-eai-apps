// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ComponentType, forwardRef, useState } from 'react';

import { Input, type InputProps } from './InputPrimitive';
import { Button } from '../Buttons/Button';
import { cn } from '@heroui/react';
import { IconEye, IconEyeOff } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';

interface PasswordInputProps extends InputProps {
  icon?: ComponentType<any>;
  /**
   * Renders the field as `type="text"` with CSS-only obscuring instead of
   * `type="password"`. Native password managers (Chrome/Edge/Safari) decide
   * whether to offer "Save password?" solely from the presence of a
   * `type="password"` input in a submitted form — autocomplete and the
   * data-1p-ignore/data-lpignore/data-bwignore extension hints don't affect
   * it. Use this for secrets that are not login credentials (API tokens,
   * access keys) where that prompt is misleading.
   */
  preventPasswordManagerPrompt?: boolean;
}

/**
 * `-webkit-text-security` has no effect in Firefox, which would otherwise
 * render the "masked" `type="text"` input in clear text. Only use the
 * CSS-masking trick when the browser actually supports it; fall back to a
 * native `type="password"` field (and its password-manager prompt) rather
 * than silently exposing the secret.
 */
const supportsTextSecurityMasking = (): boolean =>
  typeof CSS !== 'undefined' &&
  typeof CSS.supports === 'function' &&
  CSS.supports('-webkit-text-security', 'disc');

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  (
    {
      icon: Icon,
      startContent,
      preventPasswordManagerPrompt,
      classNames,
      ...props
    },
    ref,
  ) => {
    const { t } = useTranslation('sharedComponents');
    const [reveal, setReveal] = useState(false);
    const canMaskWithCss = preventPasswordManagerPrompt
      ? supportsTextSecurityMasking()
      : false;

    // If an icon is provided, render it with error-aware styling
    const iconContent = Icon ? (
      <Icon
        className={cn({
          'stroke-danger': props.isInvalid,
          'stroke-neutral-500': !props.isInvalid,
        })}
      />
    ) : null;

    return (
      <Input
        ref={ref}
        {...props}
        type={canMaskWithCss ? 'text' : reveal ? 'text' : 'password'}
        classNames={
          canMaskWithCss
            ? {
                ...classNames,
                input: cn(
                  classNames?.input,
                  reveal
                    ? '[-webkit-text-security:none]'
                    : '[-webkit-text-security:disc]',
                ),
              }
            : classNames
        }
        startContent={iconContent || startContent}
        endContent={
          <Button
            variant="light"
            isIconOnly
            size="sm"
            onPress={() => setReveal(!reveal)}
            tabIndex={-1}
            aria-label={
              reveal ? t('password.hidePassword') : t('password.showPassword')
            }
          >
            {reveal ? <IconEyeOff /> : <IconEye />}
          </Button>
        }
      />
    );
  },
);

PasswordInput.displayName = 'PasswordInput';

export default PasswordInput;
