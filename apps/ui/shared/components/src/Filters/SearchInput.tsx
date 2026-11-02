// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { SearchField as HeroUISearchField, cn } from '@heroui/react';
import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from 'react';
import React, { forwardRef } from 'react';
import { debounce } from 'lodash';

const sizeToClassName = {
  sm: 'w-54',
  md: 'w-96',
  lg: 'w-1/2',
  full: 'w-full',
} as const;

type SearchInputSize = keyof typeof sizeToClassName;

interface SearchInputProps {
  placeholder?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  delay?: number;
  disableDebounce?: boolean;
  size?: SearchInputSize;
  variant?: 'primary' | 'secondary';
  className?: string;
  isDisabled?: boolean;
  'aria-label'?: string;
}

/**
 * Debounced search field adapter over HeroUI `SearchField`.
 */
const SearchInput = forwardRef<{ clear: () => void }, SearchInputProps>(
  (
    {
      placeholder,
      defaultValue = '',
      onValueChange,
      size = 'sm',
      variant,
      delay = 500,
      disableDebounce = false,
      isDisabled,
      className,
      'aria-label': ariaLabel,
    },
    ref,
  ) => {
    const [internalValue, setInternalValue] = useState<string>(defaultValue);

    useEffect(() => {
      if (defaultValue) setInternalValue(defaultValue);
    }, [defaultValue]);

    useImperativeHandle(
      ref,
      () => ({
        clear: () => {
          setInternalValue('');
        },
      }),
      [],
    );

    const debouncedOnValueChange = useMemo(() => {
      if (!onValueChange) return undefined;
      if (disableDebounce) return onValueChange;
      return debounce(onValueChange, delay);
    }, [onValueChange, delay, disableDebounce]);

    const handleValueChange = useCallback(
      (newValue: string) => {
        setInternalValue(newValue);
        debouncedOnValueChange?.(newValue);
      },
      [debouncedOnValueChange],
    );

    return (
      <HeroUISearchField
        value={internalValue}
        onChange={handleValueChange}
        fullWidth={size === 'full'}
        variant={variant}
        isDisabled={isDisabled}
        aria-label={ariaLabel}
        className={cn(sizeToClassName[size], className)}
      >
        <HeroUISearchField.Group className="w-full min-w-0">
          <HeroUISearchField.SearchIcon />
          <HeroUISearchField.Input
            placeholder={placeholder}
            className="min-w-0"
          />
          <HeroUISearchField.ClearButton />
        </HeroUISearchField.Group>
      </HeroUISearchField>
    );
  },
);

SearchInput.displayName = 'SearchInput';

export { SearchInput };
