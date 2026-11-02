// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

'use client';

// Tremor LineChart [v1.0.0]

/* eslint-disable @typescript-eslint/no-explicit-any */
import { cn } from '@heroui/react';
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';
import React from 'react';

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
  hasOnlyOneValueForKey,
} from '@amdenterpriseai/utils/app';

import type { AxisDomain } from 'recharts/types/util/types';

import { TOOLTIP_Z_INDEX } from '../constants';

import { format } from 'date-fns/format';

import {
  CartesianGrid,
  Dot,
  Label,
  Line,
  Legend as RechartsLegend,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { AvailableChartColorsKeys } from '@amdenterpriseai/types';

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
  return (
    <li
      className={cn(
        // base
        'group inline-flex flex-nowrap items-center gap-1.5 rounded-sm px-2 py-1 whitespace-nowrap transition',
        hasOnValueChange
          ? 'cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800'
          : 'cursor-default',
      )}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(name, color);
      }}
    >
      <span
        className={cn(
          'h-[3px] w-3.5 shrink-0 rounded-full',
          getColorClassName(color, 'bg'),
          activeLegend && activeLegend !== name ? 'opacity-40' : 'opacity-100',
        )}
        aria-hidden={true}
      />
      <p
        className={cn(
          // base
          'truncate text-xs whitespace-nowrap',
          // text color
          'text-gray-700 dark:text-gray-300',
          hasOnValueChange &&
            'group-hover:text-gray-900 dark:group-hover:text-gray-50',
          activeLegend && activeLegend !== name ? 'opacity-40' : 'opacity-100',
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
            // backgrousnd color
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

  const legendPayload = payload.filter((item: any) => item.type !== 'none');

  const paddingLeft =
    legendPosition === 'left' && yAxisWidth ? yAxisWidth - 8 : 0;

  return (
    <div
      ref={legendRef}
      style={{ paddingLeft: paddingLeft }}
      className={cn(
        'flex items-center',
        { 'justify-center': legendPosition === 'center' },
        { 'justify-start': legendPosition === 'left' },
        { 'justify-end': legendPosition === 'right' },
      )}
    >
      <Legend
        categories={legendPayload.map((entry: any) => entry.value)}
        colors={legendPayload.map((entry: any) =>
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
    const legendPayload = payload.filter((item: any) => item.type !== 'none');
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
          {legendPayload.map(({ value, category, color }, index) => (
            <div
              key={`id-${index}`}
              className="flex items-center justify-between space-x-8"
            >
              <div className="flex items-center space-x-2">
                <span
                  aria-hidden="true"
                  className={cn(
                    'h-[3px] w-3.5 shrink-0 rounded-full',
                    getColorClassName(color, 'bg'),
                  )}
                />
                <p
                  className={cn(
                    // base
                    'text-right whitespace-nowrap',
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
                  'text-right font-medium whitespace-nowrap tabular-nums',
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

//#region LineChart

interface ActiveDot {
  index?: number;
  dataKey?: string;
}

type BaseEventProps = {
  eventType: 'dot' | 'category';
  categoryClicked: string;
  [key: string]: number | string;
};

type LineChartEventProps = BaseEventProps | null | undefined;

interface LineChartProps extends React.HTMLAttributes<HTMLDivElement> {
  data: Record<string, any>[];
  index: string;
  categories: string[];
  colors?: AvailableChartColorsKeys[];
  valueFormatter?: (value: number) => string;
  tooltipValueFormatter?: (value: number) => string;
  startEndOnly?: boolean;
  showXAxis?: boolean;
  showYAxis?: boolean;
  showGridLines?: boolean;
  yAxisWidth?: number;
  /** Max number of Y-axis ticks (and horizontal grid lines). e.g. 3 for compact charts. */
  yAxisTickCount?: number;
  intervalType?: 'preserveStartEnd' | 'equidistantPreserveStart';
  showTooltip?: boolean;
  showLegend?: boolean;
  autoMinValue?: boolean;
  minValue?: number;
  maxValue?: number;
  allowDecimals?: boolean;
  onValueChange?: (value: LineChartEventProps) => void;
  enableLegendSlider?: boolean;
  tickGap?: number;
  connectNulls?: boolean;
  xAxisLabel?: string;
  yAxisLabel?: string;
  xPadding?: boolean;
  legendPosition?: 'left' | 'center' | 'right';
  tooltipCallback?: (tooltipCallbackContent: TooltipProps) => void;
  customTooltip?: React.ComponentType<TooltipProps>;
  customWidth?: Record<number, number>;
  isLoading?: boolean;
  loadingText?: string;
  activeLegendProp?: string;
  showDots?: boolean;
  /** Extra space (px) above the top gridline so the highest Y-axis tick label isn't clipped. Defaults to 5. */
  marginTop?: number;
}

const LineChart = React.forwardRef<HTMLDivElement, LineChartProps>(
  (props, ref) => {
    const { t } = useTranslation('sharedComponents');
    const {
      data = [],
      categories = [],
      index,
      isLoading = false,
      loadingText = t('data.loading'),
      colors = AvailableChartColors,
      valueFormatter = (value: number) => value.toString(),
      tooltipValueFormatter = (value: number) => value.toFixed(2),
      startEndOnly = false,
      showXAxis = true,
      showYAxis = true,
      showGridLines = true,
      xPadding = true,
      yAxisWidth = 56,
      yAxisTickCount,
      intervalType = 'equidistantPreserveStart',
      showTooltip = true,
      showLegend = true,
      autoMinValue = false,
      minValue,
      maxValue,
      allowDecimals = true,
      connectNulls = false,
      className,
      onValueChange,
      enableLegendSlider = false,
      tickGap = 5,
      xAxisLabel,
      yAxisLabel,
      legendPosition = 'right',
      tooltipCallback,
      customTooltip,
      customWidth,
      activeLegendProp,
      showDots = false,
      marginTop = 5,
      ...other
    } = props;
    const CustomTooltip = customTooltip;
    const paddingValue =
      (!showXAxis && !showYAxis) || (startEndOnly && !showYAxis) || !xPadding
        ? 0
        : 20;
    const [legendHeight, setLegendHeight] = React.useState(60);
    const [activeDot, setActiveDot] = React.useState<ActiveDot | undefined>(
      undefined,
    );
    const [internalActiveLegend, setInternalActiveLegend] = React.useState<
      string | undefined
    >(undefined);
    const activeLegend = activeLegendProp ?? internalActiveLegend;
    const setActiveLegend = (value: string | undefined) => {
      if (activeLegendProp === undefined) {
        setInternalActiveLegend(value);
      }
    };

    const _categories = isLoading ? [loadingText] : categories;
    const _data = isLoading ? generateSkeletonChartData(loadingText) : data;
    const categoryColors = constructCategoryColors(
      _categories,
      isLoading ? ['gray'] : colors,
    );

    const isOver1d = React.useMemo(() => {
      return isOver1Day(_data, index);
    }, [_data, index]);

    const firstOfDayIndices = getFirstTimestampsOfDayIndices(
      data.map((item) => {
        return new Date(item[index]);
      }),
    );

    const ticks = isOver1d
      ? _data
          .filter((_, idx) => firstOfDayIndices.includes(idx))
          .map((item) => item[index])
      : undefined;

    const yAxisDomain = getYAxisDomain(autoMinValue, minValue, maxValue);
    const hasOnValueChange = !!onValueChange;

    function onDotClick(itemData: any, event: React.MouseEvent) {
      event.stopPropagation();

      if (!hasOnValueChange) return;
      if (
        (itemData.index === activeDot?.index &&
          itemData.dataKey === activeDot?.dataKey) ||
        (hasOnlyOneValueForKey(_data, itemData.dataKey) &&
          activeLegend &&
          activeLegend === itemData.dataKey)
      ) {
        setActiveLegend(undefined);
        setActiveDot(undefined);
        onValueChange?.(null);
      } else {
        setActiveLegend(itemData.dataKey);
        setActiveDot({
          index: itemData.index,
          dataKey: itemData.dataKey,
        });
        onValueChange?.({
          eventType: 'dot',
          categoryClicked: itemData.dataKey,
          ...itemData.payload,
        });
      }
    }

    function onCategoryClick(dataKey: string) {
      if (!hasOnValueChange) return;
      if (
        (dataKey === activeLegend && !activeDot) ||
        (hasOnlyOneValueForKey(_data, dataKey) &&
          activeDot &&
          activeDot.dataKey === dataKey)
      ) {
        setActiveLegend(undefined);
        onValueChange?.(null);
      } else {
        setActiveLegend(dataKey);
        onValueChange?.({
          eventType: 'category',
          categoryClicked: dataKey,
        });
      }
      setActiveDot(undefined);
    }

    return (
      <div
        ref={ref}
        className={cn('h-80 w-full', className)}
        tremor-id="tremor-raw"
        {...other}
      >
        <ResponsiveContainer debounce={300}>
          <RechartsLineChart
            data={_data}
            onClick={
              hasOnValueChange && (activeLegend || activeDot)
                ? () => {
                    setActiveDot(undefined);
                    setActiveLegend(undefined);
                    onValueChange?.(null);
                  }
                : undefined
            }
            margin={{
              bottom: xAxisLabel ? 30 : 5,
              left: yAxisLabel ? 20 : undefined,
              right: yAxisLabel ? 5 : undefined,
              top: marginTop,
            }}
          >
            {showGridLines ? (
              <CartesianGrid
                className={cn('stroke-gray-200 stroke-1 dark:stroke-gray-600', {
                  'animate-pulse': isLoading,
                })}
                horizontal={true}
                vertical={false}
              />
            ) : null}
            <XAxis
              padding={{ left: paddingValue, right: paddingValue }}
              hide={!showXAxis}
              dataKey={index}
              interval={startEndOnly ? 'preserveStartEnd' : intervalType}
              tick={{ transform: 'translate(0, 6)' }}
              ticks={
                startEndOnly && data.length > 0
                  ? [_data[0][index], _data[_data.length - 1][index]]
                  : ticks
              }
              tickFormatter={(time) => {
                const date = time instanceof Date ? time : new Date(time);
                if (Number.isNaN(date.getTime())) return '';
                return isOver1d
                  ? format(date, 'MMM dd')
                  : format(date, 'HH:mm');
              }}
              fill=""
              stroke=""
              className={cn(
                // base
                'text-xs',
                // text fill
                'fill-gray-500 dark:fill-gray-400',
                { 'animate-pulse': isLoading },
              )}
              tickLine={false}
              axisLine={false}
              minTickGap={tickGap}
            >
              {xAxisLabel && (
                <Label
                  position="insideBottom"
                  offset={-20}
                  className="fill-gray-800 text-sm font-medium dark:fill-gray-200"
                >
                  {xAxisLabel}
                </Label>
              )}
            </XAxis>
            <YAxis
              orientation="left"
              interval="preserveStartEnd"
              width={yAxisWidth}
              hide={!showYAxis}
              axisLine={false}
              tickLine={false}
              type="number"
              domain={yAxisDomain as AxisDomain}
              tickCount={yAxisTickCount}
              tick={{ transform: 'translate(-3, 0)' }}
              minTickGap={1}
              fill=""
              stroke=""
              className={cn(
                // base
                'text-xs',
                // text fill
                'fill-gray-500 dark:fill-gray-400',
                { 'animate-pulse': isLoading },
              )}
              tickFormatter={valueFormatter}
              allowDecimals={allowDecimals}
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
            <Tooltip
              wrapperStyle={{ outline: 'none', zIndex: TOOLTIP_Z_INDEX }}
              isAnimationActive={true}
              animationDuration={100}
              cursor={{ stroke: '#d1d5db', strokeWidth: 1 }}
              offset={20}
              position={{ y: 0 }}
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

                return showTooltip && active ? (
                  CustomTooltip ? (
                    <CustomTooltip
                      active={active}
                      payload={cleanPayload}
                      label={label}
                    />
                  ) : (
                    <ChartTooltip
                      active={active}
                      payload={cleanPayload}
                      label={label}
                      valueFormatter={tooltipValueFormatter}
                    />
                  )
                ) : null;
              }}
            />

            {showLegend ? (
              <RechartsLegend
                verticalAlign="top"
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
            {_categories.map((category, catIdx) => (
              <Line
                className={cn(
                  getColorClassName(
                    categoryColors.get(category) as AvailableChartColorsKeys,
                    'stroke',
                  ),
                  { 'animate-pulse': isLoading },
                )}
                strokeOpacity={
                  activeDot || (activeLegend && activeLegend !== category)
                    ? 0.3
                    : 1
                }
                activeDot={(props: any) => {
                  const {
                    cx: cxCoord,
                    cy: cyCoord,
                    stroke,
                    strokeLinecap,
                    strokeLinejoin,
                    strokeWidth,
                    dataKey,
                  } = props;
                  return (
                    <Dot
                      className={cn(
                        'stroke-white dark:stroke-gray-950',
                        onValueChange ? 'cursor-pointer' : '',
                        getColorClassName(
                          categoryColors.get(
                            dataKey,
                          ) as AvailableChartColorsKeys,
                          'fill',
                        ),
                      )}
                      cx={cxCoord}
                      cy={cyCoord}
                      r={5}
                      fill=""
                      stroke={stroke}
                      strokeLinecap={strokeLinecap}
                      strokeLinejoin={strokeLinejoin}
                      strokeWidth={strokeWidth}
                      onClick={(_, event) => onDotClick(props, event)}
                    />
                  );
                }}
                dot={(props: any) => {
                  const {
                    stroke,
                    strokeLinecap,
                    strokeLinejoin,
                    strokeWidth,
                    cx: cxCoord,
                    cy: cyCoord,
                    dataKey,
                    index,
                  } = props;

                  const shouldShowDot =
                    showDots ||
                    (hasOnlyOneValueForKey(_data, category) &&
                      !(
                        activeDot ||
                        (activeLegend && activeLegend !== category)
                      )) ||
                    (activeDot?.index === index &&
                      activeDot?.dataKey === category);

                  if (shouldShowDot) {
                    const isDimmed =
                      activeDot || (activeLegend && activeLegend !== category);
                    // Outlined circles with white fill when showDots is enabled
                    if (showDots) {
                      return (
                        <Dot
                          key={index}
                          cx={cxCoord}
                          cy={cyCoord}
                          r={3.5}
                          fill="white"
                          stroke=""
                          strokeWidth={2}
                          className={cn(
                            'dark:fill-gray-950',
                            onValueChange ? 'cursor-pointer' : '',
                            getColorClassName(
                              categoryColors.get(
                                dataKey,
                              ) as AvailableChartColorsKeys,
                              'stroke',
                            ),
                            isDimmed && 'opacity-30',
                          )}
                        />
                      );
                    }
                    return (
                      <Dot
                        key={index}
                        cx={cxCoord}
                        cy={cyCoord}
                        r={5}
                        stroke={stroke}
                        fill=""
                        strokeLinecap={strokeLinecap}
                        strokeLinejoin={strokeLinejoin}
                        strokeWidth={strokeWidth}
                        className={cn(
                          'stroke-white dark:stroke-gray-950',
                          onValueChange ? 'cursor-pointer' : '',
                          getColorClassName(
                            categoryColors.get(
                              dataKey,
                            ) as AvailableChartColorsKeys,
                            'fill',
                          ),
                        )}
                      />
                    );
                  }
                  return <React.Fragment key={index}></React.Fragment>;
                }}
                key={category}
                name={category}
                type="monotone"
                dataKey={category}
                stroke=""
                strokeWidth={customWidth?.[catIdx] ?? 2}
                strokeLinejoin="round"
                strokeLinecap="round"
                isAnimationActive={false}
                connectNulls={connectNulls}
              />
            ))}
            {/* hidden lines to increase clickable target area */}
            {onValueChange
              ? _categories.map((category) => (
                  <Line
                    className={cn('cursor-pointer')}
                    strokeOpacity={0}
                    key={category}
                    name={category}
                    type="monotone"
                    dataKey={category}
                    stroke="transparent"
                    fill="transparent"
                    legendType="none"
                    tooltipType="none"
                    strokeWidth={12}
                    connectNulls={connectNulls}
                    onClick={(props: any, event) => {
                      event.stopPropagation();
                      const { name } = props;
                      onCategoryClick(name);
                    }}
                  />
                ))
              : null}
          </RechartsLineChart>
        </ResponsiveContainer>
      </div>
    );
  },
);

LineChart.displayName = 'LineChart';

export { LineChart, type LineChartEventProps, type TooltipProps };
