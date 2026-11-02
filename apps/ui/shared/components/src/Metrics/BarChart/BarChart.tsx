// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

'use client';

// Tremor BarChart [v1.0.0]

/* eslint-disable @typescript-eslint/no-explicit-any */
import { cn } from '@heroui/react';
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';
import React from 'react';
import { isEqual } from 'lodash';

import { useOnWindowResize } from '@amdenterpriseai/hooks';

import {
  generateSkeletonChartData,
  getFirstTimestampsOfDayIndices,
  isOver1Day,
} from '@amdenterpriseai/utils/app';
import {
  AvailableChartColors,
  constructCategoryColors,
  getColorClassName,
  getYAxisDomain,
} from '@amdenterpriseai/utils/app';

import type { AxisDomain } from 'recharts/types/util/types';

import { format } from 'date-fns/format';
import { isValid } from 'date-fns/isValid';
import {
  Bar,
  CartesianGrid,
  Label,
  BarChart as RechartsBarChart,
  Legend as RechartsLegend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { AvailableChartColorsKeys } from '@amdenterpriseai/types';

//#region Shape

const renderShape = (
  props: any,
  activeBar: any | undefined,
  activeLegend: string | undefined,
  layout: string,
) => {
  const { fillOpacity, name, payload, value } = props;
  let { x, width, y, height } = props;

  if (layout === 'horizontal' && height < 0) {
    y += height;
    height = Math.abs(height); // height must be a positive number
  } else if (layout === 'vertical' && width < 0) {
    x += width;
    width = Math.abs(width); // width must be a positive number
  }

  return (
    <rect
      x={x}
      y={y}
      width={width}
      height={height}
      opacity={
        activeBar || (activeLegend && activeLegend !== name)
          ? isEqual(activeBar, { ...payload, value })
            ? fillOpacity
            : 0.3
          : fillOpacity
      }
    />
  );
};

//#region Legend

interface LegendItemProps {
  name: string;
  color: AvailableChartColorsKeys;
  onClick?: (name: string, color: AvailableChartColorsKeys) => void;
  activeLegend?: string;
}

const LegendItem = ({
  name,
  color,
  onClick,
  activeLegend,
}: LegendItemProps) => {
  const hasOnValueChange = !!onClick;
  const isActive = activeLegend === name;
  const isDimmed = activeLegend && activeLegend !== name;
  return (
    <li
      className={cn(
        // base
        'group inline-flex flex-nowrap items-center gap-1.5 rounded-sm px-2 py-1 whitespace-nowrap transition',
        hasOnValueChange
          ? [
              'cursor-pointer',
              'hover:bg-gray-100 dark:hover:bg-gray-800',
              isActive && 'bg-gray-100 dark:bg-gray-800',
              isDimmed && 'opacity-50',
            ]
          : 'cursor-default',
      )}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(name, color);
      }}
    >
      <span
        className={cn(
          'size-2 shrink-0 rounded-xs',
          getColorClassName(color, 'bg'),
        )}
        aria-hidden={true}
      />
      <p
        className={cn(
          // base
          'truncate text-sm whitespace-nowrap',
          // text color
          'text-gray-700 dark:text-gray-300',
          hasOnValueChange &&
            'group-hover:text-gray-900 dark:group-hover:text-gray-50',
          isActive && 'text-gray-900 dark:text-gray-50 font-medium',
        )}
      >
        {name}
      </p>
    </li>
  );
};

interface ScrollButtonProps {
  icon: React.ElementType;
  onClick?: () => void;
  disabled?: boolean;
}

const ScrollButton = ({ icon, onClick, disabled }: ScrollButtonProps) => {
  const Icon = icon;
  const [isPressed, setIsPressed] = React.useState(false);
  const intervalRef = React.useRef<NodeJS.Timeout | null>(null);

  React.useEffect(() => {
    if (isPressed) {
      intervalRef.current = setInterval(() => {
        onClick?.();
      }, 300);
    } else {
      clearInterval(intervalRef.current as NodeJS.Timeout);
    }
    return () => clearInterval(intervalRef.current as NodeJS.Timeout);
  }, [isPressed, onClick]);

  React.useEffect(() => {
    if (disabled) {
      clearInterval(intervalRef.current as NodeJS.Timeout);
      setIsPressed(false);
    }
  }, [disabled]);

  return (
    <button
      type="button"
      className={cn(
        // base
        'group inline-flex size-5 items-center truncate rounded-sm transition',
        disabled
          ? 'cursor-not-allowed text-gray-400 dark:text-gray-600'
          : 'cursor-pointer text-gray-700 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-gray-50',
      )}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      onMouseDown={(e) => {
        e.stopPropagation();
        setIsPressed(true);
      }}
      onMouseUp={(e) => {
        e.stopPropagation();
        setIsPressed(false);
      }}
    >
      <Icon className="size-full" aria-hidden="true" />
    </button>
  );
};

interface LegendProps extends React.OlHTMLAttributes<HTMLOListElement> {
  categories: string[];
  colors?: AvailableChartColorsKeys[];
  onClickLegendItem?: (category: string, color: string) => void;
  activeLegend?: string;
  enableLegendSlider?: boolean;
}

type HasScrollProps = {
  left: boolean;
  right: boolean;
};

const Legend = React.forwardRef<HTMLOListElement, LegendProps>((props, ref) => {
  const {
    categories,
    colors = AvailableChartColors,
    className,
    onClickLegendItem,
    activeLegend,
    enableLegendSlider = false,
    ...other
  } = props;
  const scrollableRef = React.useRef<HTMLInputElement>(null);
  const scrollButtonsRef = React.useRef<HTMLDivElement>(null);
  const [hasScroll, setHasScroll] = React.useState<HasScrollProps | null>(null);
  const [isKeyDowned, setIsKeyDowned] = React.useState<string | null>(null);
  const intervalRef = React.useRef<NodeJS.Timeout | null>(null);

  const checkScroll = React.useCallback(() => {
    const scrollable = scrollableRef?.current;
    if (!scrollable) return;

    const hasLeftScroll = scrollable.scrollLeft > 0;
    const hasRightScroll =
      scrollable.scrollWidth - scrollable.clientWidth > scrollable.scrollLeft;

    setHasScroll({ left: hasLeftScroll, right: hasRightScroll });
  }, [setHasScroll]);

  const scrollToTest = React.useCallback(
    (direction: 'left' | 'right') => {
      const element = scrollableRef?.current;
      const scrollButtons = scrollButtonsRef?.current;
      const scrollButtonsWith = scrollButtons?.clientWidth ?? 0;
      const width = element?.clientWidth ?? 0;

      if (element && enableLegendSlider) {
        element.scrollTo({
          left:
            direction === 'left'
              ? element.scrollLeft - width + scrollButtonsWith
              : element.scrollLeft + width - scrollButtonsWith,
          behavior: 'smooth',
        });
        setTimeout(() => {
          checkScroll();
        }, 400);
      }
    },
    [enableLegendSlider, checkScroll],
  );

  React.useEffect(() => {
    const keyDownHandler = (key: string) => {
      if (key === 'ArrowLeft') {
        scrollToTest('left');
      } else if (key === 'ArrowRight') {
        scrollToTest('right');
      }
    };
    if (isKeyDowned) {
      keyDownHandler(isKeyDowned);
      intervalRef.current = setInterval(() => {
        keyDownHandler(isKeyDowned);
      }, 300);
    } else {
      clearInterval(intervalRef.current as NodeJS.Timeout);
    }
    return () => clearInterval(intervalRef.current as NodeJS.Timeout);
  }, [isKeyDowned, scrollToTest]);

  const keyDown = (e: KeyboardEvent) => {
    e.stopPropagation();
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      setIsKeyDowned(e.key);
    }
  };
  const keyUp = (e: KeyboardEvent) => {
    e.stopPropagation();
    setIsKeyDowned(null);
  };

  React.useEffect(() => {
    const scrollable = scrollableRef?.current;
    if (enableLegendSlider) {
      checkScroll();
      scrollable?.addEventListener('keydown', keyDown);
      scrollable?.addEventListener('keyup', keyUp);
    }

    return () => {
      scrollable?.removeEventListener('keydown', keyDown);
      scrollable?.removeEventListener('keyup', keyUp);
    };
  }, [checkScroll, enableLegendSlider]);

  return (
    <ol
      ref={ref}
      className={cn('relative overflow-hidden', className)}
      {...other}
    >
      <div
        ref={scrollableRef}
        tabIndex={0}
        className={cn(
          'flex h-full',
          enableLegendSlider
            ? hasScroll?.right || hasScroll?.left
              ? 'snap-mandatory items-center overflow-auto pr-12 pl-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden'
              : ''
            : 'flex-wrap',
        )}
      >
        {categories.map((category, index) => (
          <LegendItem
            key={`item-${index}`}
            name={category}
            color={colors[index] as AvailableChartColorsKeys}
            onClick={onClickLegendItem}
            activeLegend={activeLegend}
          />
        ))}
      </div>
      {enableLegendSlider && (hasScroll?.right || hasScroll?.left) ? (
        <div
          className={cn(
            // base
            'absolute top-0 right-0 bottom-0 flex h-full items-center justify-center pr-1',
            // background color
            'bg-white dark:bg-gray-950',
          )}
        >
          <ScrollButton
            icon={IconChevronLeft}
            onClick={() => {
              setIsKeyDowned(null);
              scrollToTest('left');
            }}
            disabled={!hasScroll?.left}
          />
          <ScrollButton
            icon={IconChevronRight}
            onClick={() => {
              setIsKeyDowned(null);
              scrollToTest('right');
            }}
            disabled={!hasScroll?.right}
          />
        </div>
      ) : null}
    </ol>
  );
});

Legend.displayName = 'Legend';

const ChartLegend = (
  { payload }: any,
  categoryColors: Map<string, AvailableChartColorsKeys>,
  setLegendHeight: React.Dispatch<React.SetStateAction<number>>,
  activeLegend: string | undefined,
  onClick?: (category: string, color: string) => void,
  enableLegendSlider?: boolean,
  legendPosition?: 'left' | 'center' | 'right',
  yAxisWidth?: number,
) => {
  const legendRef = React.useRef<HTMLDivElement>(null);

  useOnWindowResize(() => {
    const calculateHeight = (height: number | undefined) =>
      height ? Number(height) + 15 : 60;
    setLegendHeight(calculateHeight(legendRef.current?.clientHeight));
  });

  const filteredPayload = payload.filter((item: any) => item.type !== 'none');

  const paddingLeft =
    legendPosition === 'left' && yAxisWidth ? yAxisWidth - 8 : 0;

  return (
    <div
      style={{ paddingLeft: paddingLeft }}
      ref={legendRef}
      className={cn(
        'flex items-center',
        { 'justify-center': legendPosition === 'center' },
        {
          'justify-start': legendPosition === 'left',
        },
        { 'justify-end': legendPosition === 'right' },
      )}
    >
      <Legend
        categories={filteredPayload.map((entry: any) => entry.value)}
        colors={filteredPayload.map((entry: any) =>
          categoryColors.get(entry.value),
        )}
        onClickLegendItem={onClick}
        activeLegend={activeLegend}
        enableLegendSlider={enableLegendSlider}
      />
    </div>
  );
};

//#region Tooltip

type TooltipProps = Pick<ChartTooltipProps, 'active' | 'payload' | 'label'>;

type PayloadItem = {
  category: string;
  value: number;
  index: string;
  color: AvailableChartColorsKeys;
  type?: string;
  payload: any;
};

interface ChartTooltipProps {
  active: boolean | undefined;
  payload: PayloadItem[];
  label: string;
  valueFormatter: (value: number) => string;
}

const ChartTooltip = ({
  active,
  payload,
  label,
  valueFormatter,
}: ChartTooltipProps) => {
  if (active && payload && payload.length) {
    return (
      <div
        className={cn(
          // base
          'rounded-md border text-sm shadow-md',
          // border color
          'border-gray-200 dark:border-gray-800',
          // background color
          'bg-white dark:bg-gray-950',
        )}
      >
        <div className={cn('border-b border-inherit px-4 py-2')}>
          <p
            className={cn(
              // base
              'font-medium',
              // text color
              'text-gray-900 dark:text-gray-50',
            )}
          >
            {label}
          </p>
        </div>
        <div className={cn('space-y-1 px-4 py-2')}>
          {payload.map(({ value, category, color }, index) => (
            <div
              key={`id-${index}`}
              className="flex items-center justify-between space-x-8"
            >
              <div className="flex items-center space-x-2">
                <span
                  aria-hidden="true"
                  className={cn(
                    'size-2 shrink-0 rounded-xs',
                    getColorClassName(color, 'bg'),
                  )}
                />
                <p
                  className={cn(
                    // base
                    'text-right whitespace-nowrap text-sm',
                    // text color
                    'text-gray-700 dark:text-gray-300',
                  )}
                >
                  {category}
                </p>
              </div>
              <p
                className={cn(
                  // base
                  'text-right text-sm font-medium whitespace-nowrap tabular-nums',
                  // text color
                  'text-gray-900 dark:text-gray-50',
                )}
              >
                {valueFormatter(value)}
              </p>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return null;
};

//#region BarChart

type BaseEventProps = {
  eventType: 'category' | 'bar';
  categoryClicked: string;
  [key: string]: number | string;
};

type BarChartEventProps = BaseEventProps | null | undefined;

interface BarChartProps extends React.HTMLAttributes<HTMLDivElement> {
  data: Record<string, any>[];
  index: string;
  categories: string[];
  colors?: AvailableChartColorsKeys[];
  valueFormatter?: (value: number) => string;
  startEndOnly?: boolean;
  showXAxis?: boolean;
  showYAxis?: boolean;
  showGridLines?: boolean;
  yAxisWidth?: number;
  intervalType?: 'preserveStartEnd' | 'equidistantPreserveStart';
  showTooltip?: boolean;
  showLegend?: boolean;
  autoMinValue?: boolean;
  minValue?: number;
  maxValue?: number;
  allowDecimals?: boolean;
  onValueChange?: (value: BarChartEventProps) => void;
  enableLegendSlider?: boolean;
  tickGap?: number;
  barCategoryGap?: string | number;
  xAxisLabel?: string;
  yAxisLabel?: string;
  layout?: 'vertical' | 'horizontal';
  type?: 'default' | 'stacked' | 'percent';
  legendPosition?: 'left' | 'center' | 'right';
  tooltipCallback?: (tooltipCallbackContent: TooltipProps) => void;
  customTooltip?: React.ComponentType<TooltipProps>;
  maxBarSize?: number;
  isLoading?: boolean;
  loadingText?: string;
  showTooltipOnNull?: boolean;
  activeLegendProp?: string;
}

const BarChart = React.forwardRef<HTMLDivElement, BarChartProps>(
  (props, forwardedRef) => {
    const { t } = useTranslation('sharedComponents');
    const {
      data = [],
      categories = [],
      index,
      colors = AvailableChartColors,
      valueFormatter = (value: number) => value.toString(),
      startEndOnly = false,
      showXAxis = true,
      showYAxis = true,
      showGridLines = true,
      yAxisWidth = 56,
      intervalType = 'equidistantPreserveStart',
      showTooltip = true,
      showLegend = true,
      autoMinValue = false,
      minValue,
      maxValue,
      allowDecimals = true,
      className,
      onValueChange,
      enableLegendSlider = false,
      barCategoryGap,
      tickGap = 5,
      xAxisLabel,
      yAxisLabel,
      layout = 'horizontal',
      type = 'default',
      legendPosition = 'right',
      tooltipCallback,
      customTooltip,
      isLoading = false,
      loadingText = t('data.loading'),
      showTooltipOnNull = false,
      activeLegendProp,
      maxBarSize,
      ...other
    } = props;
    const CustomTooltip = customTooltip;
    const _categories = isLoading ? [loadingText] : categories;
    const _data = isLoading ? generateSkeletonChartData(loadingText) : data;

    const paddingValue =
      (!showXAxis && !showYAxis) || (startEndOnly && !showYAxis) ? 0 : 20;
    const [legendHeight, setLegendHeight] = React.useState(60);
    const [internalActiveLegend, setInternalActiveLegend] = React.useState<
      string | undefined
    >(undefined);
    const activeLegend = activeLegendProp ?? internalActiveLegend;
    const setActiveLegend = (value: string | undefined) => {
      if (activeLegendProp === undefined) {
        setInternalActiveLegend(value);
      }
    };
    const categoryColors = constructCategoryColors(
      _categories,
      isLoading ? ['gray'] : colors,
    );

    const isOver1d = React.useMemo(() => {
      return isOver1Day(_data, index);
    }, [_data, index]);

    const firstOfDayIndices = getFirstTimestampsOfDayIndices(
      data.map((item) => new Date(item[index])),
    );

    const ticks = isOver1d
      ? _data
          .filter((_, index) => firstOfDayIndices.includes(index))
          .map((item) => item[index])
      : undefined;

    const [activeBar, setActiveBar] = React.useState<any | undefined>(
      undefined,
    );
    const yAxisDomain = getYAxisDomain(autoMinValue, minValue, maxValue);
    const hasOnValueChange = !!onValueChange && !isLoading;
    const stacked = type === 'stacked' || type === 'percent';

    function valueToPercent(value: number) {
      return `${(value * 100).toFixed(0)}%`;
    }

    function onBarClick(data: any, _: any, event: React.MouseEvent) {
      event.stopPropagation();
      if (!onValueChange) return;
      if (isEqual(activeBar, { ...data.payload, value: data.value })) {
        setActiveLegend(undefined);
        setActiveBar(undefined);
        onValueChange?.(null);
      } else {
        setActiveLegend(data.tooltipPayload?.[0]?.dataKey);
        setActiveBar({
          ...data.payload,
          value: data.value,
        });
        onValueChange?.({
          eventType: 'bar',
          categoryClicked: data.tooltipPayload?.[0]?.dataKey,
          ...data.payload,
        });
      }
    }

    function onCategoryClick(dataKey: string) {
      if (!hasOnValueChange) return;
      if (dataKey === activeLegend && !activeBar) {
        setActiveLegend(undefined);
        onValueChange?.(null);
      } else {
        setActiveLegend(dataKey);
        onValueChange?.({
          eventType: 'category',
          categoryClicked: dataKey,
        });
      }
      setActiveBar(undefined);
    }

    return (
      <div
        ref={forwardedRef}
        className={cn('h-80 w-full', className)}
        tremor-id="tremor-raw"
        {...other}
      >
        <ResponsiveContainer debounce={300}>
          <RechartsBarChart
            data={_data}
            onClick={
              hasOnValueChange && (activeLegend || activeBar)
                ? () => {
                    setActiveBar(undefined);
                    setActiveLegend(undefined);
                    onValueChange?.(null);
                  }
                : undefined
            }
            margin={{
              bottom: xAxisLabel ? 30 : undefined,
              left: yAxisLabel ? 20 : undefined,
              right: yAxisLabel ? 5 : undefined,
              top: 5,
            }}
            stackOffset={type === 'percent' ? 'expand' : undefined}
            layout={layout}
            barCategoryGap={barCategoryGap}
          >
            {showGridLines ? (
              <CartesianGrid
                className={cn('stroke-gray-200 stroke-1 dark:stroke-gray-600')}
                horizontal={layout !== 'vertical'}
                vertical={layout === 'vertical'}
              />
            ) : null}
            <XAxis
              hide={!showXAxis}
              tick={{
                transform:
                  layout !== 'vertical' ? 'translate(0, 6)' : undefined,
              }}
              fill=""
              stroke=""
              className={cn(
                // base
                'text-xs',
                // text fill
                'fill-gray-500 dark:fill-gray-400',
                { 'mt-4': layout !== 'vertical' },
              )}
              tickLine={false}
              axisLine={false}
              tickFormatter={(time) => {
                const d = new Date(time);
                if (!isValid(d)) return '';
                return isOver1d ? format(d, 'MMM dd') : format(d, 'HH:mm');
              }}
              minTickGap={tickGap}
              {...(layout !== 'vertical'
                ? {
                    padding: {
                      left: paddingValue,
                      right: paddingValue,
                    },
                    dataKey: index,
                    interval: startEndOnly ? 'preserveStartEnd' : intervalType,
                    ticks: startEndOnly
                      ? [_data[0][index], _data[_data.length - 1][index]]
                      : ticks,
                  }
                : {
                    type: 'number',
                    domain: yAxisDomain as AxisDomain,
                    tickFormatter:
                      type === 'percent' ? valueToPercent : valueFormatter,
                    allowDecimals: allowDecimals,
                  })}
            >
              {xAxisLabel && (
                <Label
                  position="insideBottom"
                  offset={-20}
                  className={cn(
                    'fill-gray-800 text-sm font-medium dark:fill-gray-200',
                    { 'animate-pulse': isLoading },
                  )}
                >
                  {xAxisLabel}
                </Label>
              )}
            </XAxis>
            <YAxis
              width={yAxisWidth}
              hide={!showYAxis}
              axisLine={false}
              tickLine={false}
              fill=""
              stroke=""
              className={cn(
                // base
                'text-xs',
                // text fill
                'fill-gray-500 dark:fill-gray-400',
                { 'animate-pulse': isLoading },
              )}
              tick={{
                transform:
                  layout !== 'vertical'
                    ? 'translate(-3, 0)'
                    : 'translate(0, 0)',
              }}
              {...(layout !== 'vertical'
                ? {
                    type: 'number',
                    domain: yAxisDomain as AxisDomain,
                    tickFormatter:
                      type === 'percent' ? valueToPercent : valueFormatter,
                    allowDecimals: allowDecimals,
                  }
                : {
                    dataKey: index,
                    ticks: startEndOnly
                      ? [_data[0][index], _data[_data.length - 1][index]]
                      : undefined,
                    type: 'category',
                    interval: 'equidistantPreserveStart',
                  })}
            >
              {yAxisLabel && (
                <Label
                  position="insideLeft"
                  style={{ textAnchor: 'middle' }}
                  angle={-90}
                  offset={-15}
                  className="fill-gray-800 text-sm font-medium dark:fill-gray-200"
                >
                  {yAxisLabel}
                </Label>
              )}
            </YAxis>
            {!!categories.length && (
              <Tooltip
                wrapperStyle={{ outline: 'none' }}
                isAnimationActive={true}
                animationDuration={100}
                cursor={{ fill: '#d1d5db', opacity: '0.15' }}
                offset={20}
                position={{
                  y: layout === 'horizontal' ? 0 : undefined,
                  x: layout === 'horizontal' ? undefined : yAxisWidth + 20,
                }}
                filterNull={!showTooltipOnNull}
                content={({ active, payload, label }) => {
                  const cleanPayload: TooltipProps['payload'] = payload
                    ? payload.map((item: any) => ({
                        category: item.dataKey,
                        value: item.value,
                        index: item.payload[index],
                        color: categoryColors.get(
                          item.dataKey,
                        ) as AvailableChartColorsKeys,
                        type: item.type,
                        payload: item.payload,
                      }))
                    : [];

                  if (tooltipCallback) {
                    queueMicrotask(() =>
                      tooltipCallback({ active, payload: cleanPayload, label }),
                    );
                  }

                  const labelDate = new Date(label);
                  const formattedLabel = isValid(labelDate)
                    ? format(labelDate, 'yyyy-MM-dd HH:mm')
                    : String(label);

                  return showTooltip && !isLoading && active ? (
                    CustomTooltip ? (
                      <CustomTooltip
                        active={active}
                        payload={cleanPayload}
                        label={formattedLabel}
                      />
                    ) : (
                      <ChartTooltip
                        active={active}
                        payload={cleanPayload}
                        label={formattedLabel}
                        valueFormatter={valueFormatter}
                      />
                    )
                  ) : null;
                }}
              />
            )}
            {showLegend ? (
              <RechartsLegend
                verticalAlign="bottom"
                height={legendHeight}
                content={({ payload }) =>
                  ChartLegend(
                    { payload },
                    categoryColors,
                    setLegendHeight,
                    activeLegend,
                    hasOnValueChange
                      ? (clickedLegendItem: string) =>
                          onCategoryClick(clickedLegendItem)
                      : undefined,
                    enableLegendSlider,
                    legendPosition,
                    yAxisWidth,
                  )
                }
              />
            ) : null}
            {_categories.map((category) => (
              <Bar
                className={cn(
                  getColorClassName(
                    categoryColors.get(category) as AvailableChartColorsKeys,
                    'fill',
                  ),
                  onValueChange ? 'cursor-pointer' : '',
                  { 'animate-pulse': isLoading },
                )}
                key={category}
                name={category}
                type="linear"
                dataKey={category}
                stackId={stacked ? 'stack' : undefined}
                isAnimationActive={false}
                maxBarSize={maxBarSize}
                fill=""
                fillOpacity={0.8}
                shape={(props: any) =>
                  renderShape(props, activeBar, activeLegend, layout)
                }
                onClick={onBarClick}
              />
            ))}
          </RechartsBarChart>
        </ResponsiveContainer>
      </div>
    );
  },
);

BarChart.displayName = 'BarChart';

export { BarChart, type BarChartEventProps, type TooltipProps };
