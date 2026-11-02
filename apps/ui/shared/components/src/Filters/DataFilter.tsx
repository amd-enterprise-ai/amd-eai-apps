// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Select, SelectItem } from '@amdenterpriseai/components';
import { cn } from '@heroui/react';
import {
  type ComponentProps,
  createRef,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { useTranslation } from 'next-i18next';

import { getDefaultFilterValues } from '@amdenterpriseai/utils/app';

import { FilterComponentType } from '@amdenterpriseai/types';
import { FilterFieldMapping, FilterValueMap } from '@amdenterpriseai/types';

import { SearchInput } from './SearchInput';
import ClearFiltersButton from './ClearFiltersButton';
import FilterDropdown from './FilterDropdown';

import { isEqual } from 'lodash';

interface Props {
  filters: FilterFieldMapping;
  onFilterChange: (filters: FilterValueMap) => void;
  canClear?: boolean;
}

export const DataFilter = ({
  filters,
  onFilterChange,
  canClear = true,
}: Props) => {
  const { t } = useTranslation('common');

  const [filterValues, setFilterValues] = useState<Partial<FilterValueMap>>(
    getDefaultFilterValues(filters),
  );

  // Store debounce inputs per filter key
  const debounceInputRef = useRef<
    Record<string, React.RefObject<{ clear: () => void } | null>>
  >({});

  // Store FilterDropdown refs per filter key
  const filterDropdownRef = useRef<
    Record<string, React.RefObject<{ clear: () => void } | null>>
  >({});

  // Memoize default values to avoid recalculating on every render
  const defaultValues = useMemo(
    () => getDefaultFilterValues(filters),
    [filters],
  );

  // Keep latest onFilterChange in a ref so the effect does not re-run when the
  // parent passes a new callback reference (which would cause an infinite loop
  // when the callback calls setState).
  const onFilterChangeRef = useRef(onFilterChange);
  onFilterChangeRef.current = onFilterChange;

  // Call onFilterChange when filterValues change (but not on initial render)
  const isInitialMount = useRef(true);
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    onFilterChangeRef.current(filterValues as FilterValueMap);
  }, [filterValues]);

  const clearFilters = useCallback(() => {
    // Reset FilterDropdown components directly via refs
    Object.keys(filters).forEach((key) => {
      const filter = filters[key as keyof typeof filters];

      if (filter.type === FilterComponentType.DROPDOWN) {
        const dropdownRef = filterDropdownRef.current[key]?.current;
        if (dropdownRef) {
          dropdownRef.clear();
        }
      }

      if (filter.type === FilterComponentType.TEXT) {
        const input = debounceInputRef.current[key]?.current;
        if (input) {
          input.clear();
        }
      }
    });

    setFilterValues(defaultValues);
  }, [filters, defaultValues]);

  const isClearButtonDisabled = useMemo(() => {
    return isEqual(filterValues, defaultValues);
  }, [filterValues, defaultValues]);

  return (
    <>
      {Object.keys(filters).map((key) => {
        const filter = filters[key as keyof typeof filters];

        if (filter.type === FilterComponentType.TEXT) {
          return (
            <SearchInput
              key={`filter-input-${String(key)}`}
              className={cn(
                'w-[calc(100%-3.3rem)] md:w-[calc(100%-3.4rem)] lg:max-w-48',
                filter.className,
              )}
              aria-label={filter.label}
              placeholder={filter.placeholder}
              variant={filter.variant}
              onValueChange={(value) => {
                // Keep state for all filter values
                setFilterValues((prev) => {
                  const trimmed = value?.trim();
                  if (!trimmed) {
                    if (prev[key] === undefined) return prev;
                    const { [key]: _, ...rest } = prev;
                    return rest;
                  }
                  return { ...prev, [key]: [trimmed] };
                });
              }}
              ref={(() => {
                if (!debounceInputRef.current[key]) {
                  debounceInputRef.current[key] = createRef<{
                    clear: () => void;
                  }>();
                }
                return debounceInputRef.current[key];
              })()}
            />
          );
        }

        if (filter.type === FilterComponentType.SELECT) {
          return (
            <Select
              key={`select-filter-${filter.name}-${String(key)}`}
              variant="primary"
              selectionMode={
                filter.allowMultipleSelection ? 'multiple' : undefined
              }
              aria-label={filter.label}
              className={cn(
                'w-full md:w-[calc(50%-0.5rem)] lg:w-48',
                filter.className,
              )}
              startContent={filter.icon}
              placeholder={filter.placeholder}
              defaultSelectedKeys={filter.defaultSelectedValues?.map(String)}
              selectedKeys={
                Array.isArray(filterValues[key])
                  ? (filterValues[key] as (string | number | boolean)[]).map(
                      String,
                    )
                  : []
              }
              onSelectionChange={(values) => {
                setFilterValues((prev) => ({
                  ...prev,
                  [key]: Array.from(values).map((item) => String(item)),
                }));
              }}
            >
              {filter?.fields
                ? filter.fields.map((field) => (
                    <SelectItem
                      key={String(field.key)}
                      {...(field.props as ComponentProps<typeof SelectItem>)}
                    >
                      {field.label}
                    </SelectItem>
                  ))
                : null}
            </Select>
          );
        }

        if (filter.type === FilterComponentType.DROPDOWN) {
          return (
            <FilterDropdown
              key={`dropdown-filter-${String(key)}`}
              ref={(() => {
                if (!filterDropdownRef.current[key]) {
                  filterDropdownRef.current[key] = createRef<{
                    clear: () => void;
                  }>();
                }
                return filterDropdownRef.current[key];
              })()}
              icon={filter.icon}
              className={cn(
                'w-full md:w-[calc(50%-0.5rem)] lg:w-48',
                filter.className,
              )}
              items={(filter.fields ?? []).map((field) => {
                return {
                  ...field.props,
                  key: String(field.key),
                  label: t(field.label as any) as string,
                  description: String(field.label),
                };
              })}
              defaultSelectedKeys={
                filter.defaultSelectedValues
                  ? filter.defaultSelectedValues.map((value) => String(value))
                  : undefined
              }
              showDescription={!!filter.showFieldDescription}
              selectedKeys={
                Array.isArray(filterValues[key])
                  ? (filterValues[key] as (string | number | boolean)[]).map(
                      String,
                    )
                  : []
              }
              onSelectionChange={(selected) => {
                setFilterValues((prev) => ({
                  ...prev,
                  [key]: selected
                    ? Array.from(selected).map((item) => String(item))
                    : [],
                }));
              }}
              label={t(filter.label as any) as string}
            />
          );
        }

        throw new Error(`Unsupported filter type: ${filter.type}`);
      })}
      {canClear && Object.keys(filters).length > 0 && (
        <ClearFiltersButton
          isDisabled={isClearButtonDisabled}
          onPress={clearFilters}
        />
      )}
    </>
  );
};

export default DataFilter;
