// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Chip } from '../Chip';
import { Tooltip } from '../Tooltip';
import { ReactNode } from 'react';

import { useTranslation } from 'next-i18next';

import { BadgeDisplayVariant } from '@amdenterpriseai/types';
import { ChipDisplayVariant } from '@amdenterpriseai/types';
import { StatusBadgeVariant } from '@amdenterpriseai/types';

import { DateSince } from '../DateSince';
import { InlineBadge } from '../InlineBadge';
import Status, { StatusProps } from '../Status/Status';

/**
 * Displays a date as relative time ("just now", "N minutes ago", "yesterday at HH:mm", or absolute)
 * with a tooltip showing the absolute date/time on hover.
 * @param date - The ISO date string to format.
 */
const DateDisplay = ({ date }: { date: string }) => <DateSince date={date} />;

export interface ChipDisplayVariants {
  [type: string]: ChipDisplayVariant;
}

/**
 * Displays a chip based on a given type and a set of predefined variants.
 * @param variants - An object mapping variant keys to their configurations.
 * @param type - The key of the variant to display.
 */
const ChipDisplay = ({
  variants,
  type,
}: {
  variants: ChipDisplayVariants;
  type: string;
}) => {
  // Fallback render a Chip in danger color as an indicator of an error
  if (!variants[type]) {
    return (
      <Chip size="sm" color="danger">
        {type}!
      </Chip>
    );
  }

  const {
    label,
    color = 'default',
    icon: IconComponent = null,
  } = variants[type];

  const iconElement: ReactNode | undefined = IconComponent && (
    <IconComponent size="16" />
  );

  return (
    <Chip size="sm" variant="flat" color={color} startContent={iconElement}>
      {label}
    </Chip>
  );
};

export interface StatusVariants {
  [type: string]: StatusBadgeVariant;
}

/**
 * Displays a status badge with an icon and label, based on a given type and a set of predefined variants.
 * @param variants - An object mapping variant keys to their configurations.
 * @param type - The key of the variant to display.
 * @param additionalProps - Optional partial props merged on top of the variant to override or extend status display behavior (e.g. enabling click interactions or custom help content).
 */
const StatusDisplay = ({
  variants,
  type,
  additionalProps = {},
}: {
  variants: { [T: string]: StatusBadgeVariant };
  type: string;
  additionalProps?: Partial<StatusBadgeVariant>;
}) => {
  // Fallback render a Chip in danger color as an indicator of an error
  if (!variants[type]) {
    return (
      <Chip size="sm" color="danger">
        {type}!
      </Chip>
    );
  }

  const mergedProps: StatusProps = { ...variants[type], ...additionalProps };

  return <Status {...mergedProps} />;
};

interface TranslationDisplayBaseProps {
  tKey: string;
  ns: string;
}

type TranslationDisplayProps = TranslationDisplayBaseProps &
  Record<string, any>;

/**
 * Displays a translated string using the useTranslation hook from next-i18next.
 * All props other than `tKey` and `ns` will be passed as interpolation options to the `t` function.
 * @example
 * <TranslationDisplay tKey="templates.resources" ns="common" total={10} free={5} />
 * // Assuming "templates.resources.vram" is "{{total}} GB / {{free}} GB free"
 * // This would render: "10 GB / 5 GB free"
 *
 * @param props - Component props including `tKey`, `ns`, and any interpolation options.
 */
const TranslationDisplay = (props: TranslationDisplayProps) => {
  const { tKey, ns, ...interpolationOptions } = props;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { t } = useTranslation(ns as any);
  // The `interpolationOptions` object will contain all props other than tKey and ns.
  // This is directly compatible with what i18next's `t` function expects for options.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return <>{t(tKey as any, interpolationOptions)}</>;
};

/**
 * Renders an mdash (—) character as a placeholder in faded color.
 *
 * @remarks
 * This component is recommended for use in table cells where data might be missing
 * or not applicable, providing a visually consistent way to indicate the absence of data.
 *
 * @returns A span element containing an mdash character.
 *
 */
const NoDataDisplay = () => {
  return <span className="text-muted">&mdash;</span>;
};

export interface BadgeStackVariants {
  [type: string]: BadgeDisplayVariant;
}

/**
 * Displays a stack of overlapping badges with tooltip information.
 *
 * @remarks
 * This component renders badges in a horizontally stacked layout with negative margins
 * to create an overlapping effect. When there are more badges than the specified limit,
 * it shows a "+N" indicator. A tooltip displays all badges with their labels when hovered.
 *
 * @example
 * ```tsx
 * const variants = {
 *   gpu: { label: 'GPU', color: 'primary', icon: GpuIcon },
 *   cpu: { label: 'CPU', color: 'secondary', icon: CpuIcon },
 *   memory: { label: 'Memory', color: 'warning' }
 * };
 *
 * <BadgeStackDisplay
 *   variants={variants}
 *   types={['gpu', 'cpu', 'memory']}
 *   limit={2}
 *   title="Resource Types"
 * />
 * ```
 *
 * @param variants - An object mapping badge type keys to their display configurations
 * @param types - Array of badge type keys to display from the variants object
 * @param limit - Optional maximum number of badges to show before truncating with "+N"
 * @param title - Optional title to display at the top of the tooltip
 */
const BadgeStackDisplay = ({
  variants,
  types = [],
  limit,
  title,
}: {
  variants: BadgeStackVariants;
  types?: string[];
  limit?: number;
  title?: string;
}) => {
  const displayedTypes = limit ? types.slice(0, limit) : types;
  const remainingCount =
    limit && types.length > limit ? types.length - limit : 0;

  if (!types.length) return;

  const tooltipContent = (
    <div className="flex flex-col gap-1">
      {title && <span className="text-sm font-semibold">{title}:</span>}
      {types.map((type, index) => {
        const {
          label = type,
          color,
          icon: IconComponent,
        } = variants[type] || {};
        return (
          <div
            key={`tooltip-${type}-${index}`}
            className="flex items-center gap-2"
          >
            <InlineBadge color={color} size="sm" isOneChar>
              {IconComponent ? <IconComponent size="12" /> : label}
            </InlineBadge>
            <span className="text-sm capitalize">{label}</span>
          </div>
        );
      })}
    </div>
  );

  return (
    <Tooltip content={tooltipContent}>
      {/* biome-ignore lint/a11y/useSemanticElements: the element reveals supplemental text rather than performing an action. */}
      <span
        className="flex flex-row items-center cursor-help"
        role="button"
        tabIndex={0}
      >
        {displayedTypes.map((type, index) => {
          const {
            label = type,
            color,
            icon: IconComponent,
          } = variants[type] || {};
          return (
            <InlineBadge
              color={color}
              size="sm"
              isOneChar={true}
              className={index > 0 ? '-ml-2' : undefined}
              key={`stack-${index}`}
              aria-label={label}
            >
              {IconComponent ? <IconComponent size="12" /> : label}
            </InlineBadge>
          );
        })}

        {remainingCount > 0 && (
          <span className="text-muted text-sm font-medium ml-1">
            +{remainingCount}
          </span>
        )}
      </span>
    </Tooltip>
  );
};

export {
  DateDisplay,
  ChipDisplay,
  StatusDisplay,
  TranslationDisplay,
  NoDataDisplay,
  BadgeStackDisplay,
};
