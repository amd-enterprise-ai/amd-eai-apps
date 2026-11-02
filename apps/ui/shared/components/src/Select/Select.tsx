// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// HeroUI v3 rebuilt Select on top of React Aria Components: it is now fully
// compound (`Select.Trigger` / `Select.Value` / `Select.Popover` + `ListBox`),
// selection is expressed through `value` / `defaultValue` / `onChange` instead
// of v2's `selectedKeys` / `defaultSelectedKeys` / `onSelectionChange`, and the
// collection no longer derives item keys from the React `key` prop (it requires
// an explicit `id`). This adapter preserves the v2 prop surface so consumers do
// not have to change: it maps the v2 selection props onto the v3 model and
// injects each child's React `key` as an `id` so existing `<SelectItem key=…>`
// usage keeps working.
import {
  Description,
  FieldError,
  Key,
  Label,
  ListBox,
  Select as SelectBase,
  Selection,
  cn,
} from '@heroui/react';
import {
  Children,
  isValidElement,
  type ComponentType,
  type ReactElement,
  type ReactNode,
} from 'react';

import { injectCollectionIds } from '../internal/collectionIds';
import {
  type FormFieldVariant,
  resolveFormFieldVariant,
} from '../internal/formFieldVariant';
import { InfoTooltip } from '../internal/InfoTooltip';
import { ListboxItem } from '../Listbox/Listbox';

export type { FormFieldVariant };

// v3 Select is generically typed over its selection mode, which prevents passing
// a multi-select `value: Key[]` through a single, mode-agnostic adapter. Cast
// the root to a permissive component; the adapter owns the public prop surface.
const SelectRoot = SelectBase as unknown as ComponentType<
  Record<string, unknown> & { children?: ReactNode }
>;

export type { Selection };

/** Minimal shape of a selected item exposed to a v2 `renderValue` callback. */
export interface SelectRenderItem {
  key: Key;
  textValue?: string;
  data?: unknown;
}

/** v2 emitted a native-like change event whose `target.value` is the key. */
export interface SelectChangeEvent {
  target: { value: string };
}

export interface SelectProps {
  /** Static children or a render function for dynamic collections (when `items` is provided). */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  children?: ReactNode | ((item: any) => ReactNode);
  className?: string;
  /** Field label rendered above the trigger. */
  label?: ReactNode;
  /** Content shown in a tooltip next to the field label. */
  tooltipContent?: ReactNode;
  /** Placeholder shown when no value is selected. */
  placeholder?: string;
  /** Content rendered at the start of the trigger. */
  startContent?: ReactNode;
  /** Content rendered at the end of the trigger (before the indicator). */
  endContent?: ReactNode;
  /** Content pinned to the top of the dropdown, above the scrollable items. */
  topContent?: ReactNode;
  /** Content pinned to the bottom of the dropdown, below the scrollable items. */
  bottomContent?: ReactNode;
  /** Helper text rendered below the trigger. */
  description?: ReactNode;
  /** When true, selected item descriptions appear in the trigger. Defaults to false. */
  showDescriptionInTrigger?: boolean;
  selectionMode?: 'single' | 'multiple';
  selectedKeys?: Iterable<Key> | 'all';
  defaultSelectedKeys?: Iterable<Key> | 'all';
  onSelectionChange?: (keys: Selection) => void;
  /** v2 native-like change handler; receives `{ target: { value } }`. */
  onChange?: (event: SelectChangeEvent) => void;
  /** v2 custom trigger renderer; receives the selected items. */
  renderValue?: (items: SelectRenderItem[]) => ReactNode;
  disallowEmptySelection?: boolean;
  disabledKeys?: Iterable<Key>;
  isDisabled?: boolean;
  /** v2 alias for `isDisabled`. */
  disabled?: boolean;
  isInvalid?: boolean;
  isRequired?: boolean;
  errorMessage?: ReactNode;
  name?: string;
  /** Dynamic items list; when provided, `children` acts as a render function. */
  items?: Iterable<Record<string, unknown>>;
  /** Visual variant of the trigger. Defaults to `secondary`. */
  variant?: FormFieldVariant;
  /** Controlled open state for the dropdown popover. */
  isOpen?: boolean;
  /** Called when the dropdown open state changes. */
  onOpenChange?: (isOpen: boolean) => void;
  'aria-label'?: string;
  'data-testid'?: string;
}

type SelectInternalProps = SelectProps & {
  items?: Iterable<Record<string, unknown>>;
};

export type SelectItemProps = Parameters<typeof ListboxItem>[0];

const toArray = (keys?: Iterable<Key> | 'all'): Key[] | undefined => {
  if (keys === undefined) return undefined;
  if (keys === 'all') return [];
  return Array.from(keys);
};

interface SelectItemMetadata {
  key: Key;
  textValue?: string;
  label: string;
  description?: ReactNode;
}

const toLabelString = (node: ReactNode): string => {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(toLabelString).join('');
  return '';
};

const toItemKey = (element: ReactElement): Key | undefined => {
  const props = element.props as { id?: Key };
  if (props.id != null) return props.id;
  if (element.key != null && element.key !== '.') return element.key;
  return undefined;
};

const collectSelectItemMetadata = (
  nodes: ReactNode,
  map: Map<Key, SelectItemMetadata>,
): void => {
  Children.forEach(nodes, (child) => {
    if (!isValidElement(child)) return;
    const element = child as ReactElement<{
      id?: Key;
      children?: ReactNode;
      description?: ReactNode;
      textValue?: string;
    }>;
    const type = element.type as { displayName?: string; name?: string };
    const typeName = type.displayName ?? type.name ?? '';
    if (/Section/i.test(typeName) && element.props.children != null) {
      collectSelectItemMetadata(element.props.children, map);
      return;
    }
    const itemKey = toItemKey(element);
    const description = element.props.description;
    const label = toLabelString(element.props.children);
    if (itemKey != null && (label || description != null)) {
      const textValue =
        element.props.textValue ??
        (description != null ? label : undefined) ??
        (label || undefined);
      map.set(itemKey, { key: itemKey, textValue, label, description });
      return;
    }
    if (element.props.children != null) {
      collectSelectItemMetadata(element.props.children, map);
    }
  });
};

const buildSelectItemMetadataMap = (
  childNodes: ReactNode | ((item: unknown) => ReactNode),
  collectionItems?: Iterable<Record<string, unknown>>,
): Map<Key, SelectItemMetadata> => {
  const map = new Map<Key, SelectItemMetadata>();
  if (typeof childNodes === 'function' && collectionItems) {
    for (const item of Array.from(collectionItems)) {
      const rendered = childNodes(item);
      if (isValidElement(rendered)) {
        collectSelectItemMetadata(rendered, map);
      }
    }
    return map;
  }
  collectSelectItemMetadata(childNodes as ReactNode, map);
  return map;
};

const getEffectiveSelectedKeys = (
  currentValue: Key | Key[] | null | undefined,
  initialValue: Key | Key[] | null | undefined,
  runtimeItems: { key?: Key }[],
): Key[] => {
  if (currentValue !== undefined) {
    if (currentValue === null) return [];
    return Array.isArray(currentValue) ? currentValue : [currentValue];
  }
  if (initialValue !== undefined) {
    if (initialValue === null) return [];
    return Array.isArray(initialValue) ? initialValue : [initialValue];
  }
  return runtimeItems
    .map((item) => item.key)
    .filter((key): key is Key => key != null);
};

const resolveSelectedRenderItems = (
  keys: Key[],
  metadataMap: Map<Key, SelectItemMetadata>,
  runtimeItems: { key?: Key; textValue?: string }[],
): SelectRenderItem[] =>
  keys.flatMap((key) => {
    const metadata = metadataMap.get(key);
    if (metadata) {
      return [
        {
          key,
          textValue: metadata.textValue ?? metadata.label,
        },
      ];
    }
    const runtime = runtimeItems.find((item) => item.key === key);
    if (runtime?.key != null) {
      return [{ key: runtime.key, textValue: runtime.textValue }];
    }
    return [];
  });

const labelOnlyTriggerValue = (
  keys: Key[],
  metadataMap: Map<Key, SelectItemMetadata>,
  runtimeItems: { key?: Key; textValue?: string }[],
): string | null => {
  const labels = resolveSelectedRenderItems(keys, metadataMap, runtimeItems)
    .map((item) => item.textValue)
    .filter((value): value is string => Boolean(value));
  return labels.length > 0 ? labels.join(', ') : null;
};

const Select = (props: SelectProps): ReactElement => {
  const {
    children,
    className,
    label,
    tooltipContent,
    placeholder,
    startContent,
    endContent,
    topContent,
    bottomContent,
    description,
    showDescriptionInTrigger = false,
    selectionMode = 'single',
    selectedKeys,
    defaultSelectedKeys,
    onSelectionChange,
    onChange,
    renderValue,
    isDisabled,
    disabled,
    isInvalid,
    isRequired,
    errorMessage,
    name,
    variant,
    items,
    'aria-label': ariaLabel,
    ...rest
  } = props as SelectInternalProps;

  const listboxAriaLabel =
    ariaLabel ?? (typeof label === 'string' ? label : undefined);

  const isMultiple = selectionMode === 'multiple';

  const toValue = (keys?: Iterable<Key> | 'all') => {
    const arr = toArray(keys);
    if (arr === undefined) return undefined;
    return isMultiple ? arr : (arr[0] ?? null);
  };

  const handleChange = (value: Key | Key[] | null) => {
    const arr = value == null ? [] : Array.isArray(value) ? value : [value];
    onSelectionChange?.(new Set(arr));
    onChange?.({ target: { value: arr[0] != null ? String(arr[0]) : '' } });
  };

  const value = toValue(selectedKeys);
  const defaultValue = toValue(defaultSelectedKeys);
  const itemMetadata = buildSelectItemMetadataMap(children, items);

  return (
    <SelectRoot
      className={className || undefined}
      variant={resolveFormFieldVariant(variant)}
      placeholder={placeholder}
      selectionMode={isMultiple ? 'multiple' : 'single'}
      isDisabled={isDisabled ?? disabled}
      isInvalid={isInvalid}
      isRequired={isRequired}
      name={name}
      onChange={handleChange}
      {...(value !== undefined ? { value } : {})}
      {...(defaultValue !== undefined ? { defaultValue } : {})}
      {...(!label && ariaLabel ? { 'aria-label': ariaLabel } : {})}
      {...rest}
    >
      {label ? (
        <div className="flex items-center gap-1">
          <Label>{label}</Label>
          {tooltipContent ? <InfoTooltip content={tooltipContent} /> : null}
        </div>
      ) : null}
      <SelectBase.Trigger
        className={cn(
          'justify-start',
          startContent != null ? 'gap-2' : undefined,
        )}
      >
        {startContent != null ? (
          <span className="shrink-0 flex items-center">{startContent}</span>
        ) : null}
        <SelectBase.Value
          className={cn(
            'flex-1 text-start min-w-0',
            showDescriptionInTrigger && 'flex items-center gap-2',
            !showDescriptionInTrigger && '[&_[data-slot=description]]:hidden',
          )}
        >
          {({
            defaultChildren,
            isPlaceholder,
            selectedItems: valueSelectedItems,
          }) => {
            const triggerSelectedItems = (
              valueSelectedItems as ({
                key?: Key;
                textValue?: string;
              } | null)[]
            ).filter(
              (item): item is { key?: Key; textValue?: string } => item != null,
            );
            const effectiveKeys = getEffectiveSelectedKeys(
              value,
              defaultValue,
              triggerSelectedItems,
            );
            if (isPlaceholder || effectiveKeys.length === 0) {
              return defaultChildren;
            }
            const resolvedItems = resolveSelectedRenderItems(
              effectiveKeys,
              itemMetadata,
              triggerSelectedItems,
            );
            if (renderValue) {
              const rendered = renderValue(resolvedItems);
              if (rendered != null) {
                return (
                  <div className="flex flex-col items-start min-w-0 w-full">
                    {rendered}
                  </div>
                );
              }
            }
            if (!showDescriptionInTrigger) {
              const labelOnly = labelOnlyTriggerValue(
                effectiveKeys,
                itemMetadata,
                triggerSelectedItems,
              );
              if (labelOnly != null) {
                return labelOnly;
              }
            }
            return defaultChildren;
          }}
        </SelectBase.Value>
        {endContent != null ? (
          <span className="shrink-0 flex items-center">{endContent}</span>
        ) : null}
        <SelectBase.Indicator />
      </SelectBase.Trigger>
      <SelectBase.Popover
        className={cn(
          'min-w-(--trigger-width) max-w-95',
          'flex flex-col overflow-hidden',
        )}
      >
        {topContent != null ? (
          <div className="shrink-0 border-b border-default bg-overlay min-h-10 px-2.5 py-1.5">
            {topContent}
          </div>
        ) : null}
        <ListBox
          className="min-h-0 flex-1 scroll-py-1 overflow-y-auto overscroll-contain scrollbar"
          selectionMode={isMultiple ? 'multiple' : 'single'}
          aria-label={listboxAriaLabel}
          items={items}
        >
          {typeof children === 'function'
            ? (children as (item: unknown) => ReactNode)
            : injectCollectionIds(children as ReactNode)}
        </ListBox>
        {bottomContent != null ? (
          <div className="shrink-0 border-t border-default bg-overlay min-h-10 px-2.5 py-1.5">
            {bottomContent}
          </div>
        ) : null}
      </SelectBase.Popover>
      {isInvalid && errorMessage ? (
        <FieldError>{errorMessage}</FieldError>
      ) : description ? (
        <Description>{description}</Description>
      ) : null}
    </SelectRoot>
  );
};

const SelectItem = ListboxItem;

const SelectWithItem = Object.assign(Select, { Item: SelectItem });

export { SelectWithItem as Select, SelectItem };
