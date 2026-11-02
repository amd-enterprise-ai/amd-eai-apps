// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import React, { useMemo } from 'react';
import { Select, SelectItem } from '@amdenterpriseai/components';

import { IconCpu } from '@tabler/icons-react';
import { BarChart } from '../../../src/Metrics/BarChart';
import {
  AvailableChartColorsKeys,
  chartColors,
  ColorUtility,
} from '@amdenterpriseai/types';

export default {
  title: 'Components/Metrics/BarChart',
} satisfies StoryDefault;

// ============================================================================
// Mock Data Utilities
// ============================================================================

/**
 * Generates time-series bar chart data over the last N minutes.
 */
function generateBarChartData(config: {
  categories: string[];
  pointCount?: number;
  intervalMinutes?: number;
  baselines: number[];
  fluctuation: number;
  min?: number;
  max?: number;
}): Record<string, unknown>[] {
  const {
    categories,
    pointCount = 30,
    intervalMinutes = 5,
    baselines,
    fluctuation,
    min = 0,
    max = Infinity,
  } = config;

  const now = new Date('2026-02-11T12:30:00Z');
  const data: Record<string, unknown>[] = [];

  for (let i = 0; i < pointCount; i++) {
    const timestamp = new Date(
      now.getTime() - (pointCount - 1 - i) * intervalMinutes * 60 * 1000,
    );
    const point: Record<string, unknown> = {
      date: timestamp.toISOString(),
    };

    categories.forEach((category, idx) => {
      const baseline = baselines[idx % baselines.length];
      const noise = (Math.random() - 0.5) * 2 * fluctuation;
      const value = Math.max(min, Math.min(max, baseline + noise));
      point[category] = Math.round(value * 10) / 10;
    });

    data.push(point);
  }

  return data;
}

// ============================================================================
// Shared Utilities
// ============================================================================

const getColorClassName = (
  color: AvailableChartColorsKeys,
  type: ColorUtility,
): string => {
  return chartColors[color]?.[type] ?? 'bg-gray-500';
};

// ============================================================================
// GPU Device Select Component
// ============================================================================

/** Hook to manage GPU device selection state with HeroUI Select. */
function useGPUSelection(
  allCategories: string[],
  allColors: AvailableChartColorsKeys[],
) {
  const [selected, setSelected] = React.useState<Set<string>>(
    () => new Set(allCategories),
  );

  const onSelectionChange = React.useCallback(
    (keys: 'all' | Set<React.Key>) => {
      if (keys === 'all') {
        setSelected(new Set(allCategories));
        return;
      }
      const next = new Set(Array.from(keys).map(String));
      if (next.size > 0) setSelected(next);
    },
    [allCategories],
  );

  const filteredCategories = allCategories.filter((c) => selected.has(c));
  const filteredColors = allCategories
    .map((c, i) => [c, allColors[i]] as const)
    .filter(([c]) => selected.has(c))
    .map(([, color]) => color);

  return { selected, onSelectionChange, filteredCategories, filteredColors };
}

interface GPUDeviceSelectProps {
  allCategories: string[];
  allColors: AvailableChartColorsKeys[];
  selected: Set<string>;
  onSelectionChange: (keys: 'all' | Set<React.Key>) => void;
}

const GPUDeviceSelect: React.FC<GPUDeviceSelectProps> = ({
  allCategories,
  allColors,
  selected,
  onSelectionChange,
}) => (
  <Select
    aria-label="GPU Device"
    placeholder="GPU Device"
    selectionMode="multiple"
    variant="bordered"
    className="w-[200px]"
    startContent={<IconCpu size={16} className="text-gray-400 shrink-0" />}
    selectedKeys={selected}
    onSelectionChange={onSelectionChange}
    disallowEmptySelection
    renderValue={() => (
      <span className="text-xs">{selected.size} GPU devices selected</span>
    )}
  >
    {allCategories.map((gpu, idx) => (
      <SelectItem
        key={gpu}
        startContent={
          <span
            className={`size-2 rounded-sm shrink-0 ${getColorClassName(allColors[idx], 'bg')}`}
          />
        }
      >
        {gpu}
      </SelectItem>
    ))}
  </Select>
);

// ============================================================================
// Chart Card Wrapper
// ============================================================================

interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  headerRight?: React.ReactNode;
}

const ChartCard: React.FC<ChartCardProps> = ({
  title,
  subtitle,
  children,
  headerRight,
}) => (
  <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 p-4">
    <div className="flex items-center justify-between mb-3">
      <div>
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-50">
          {title}
        </h3>
        {subtitle && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {subtitle}
          </p>
        )}
      </div>
      {headerRight}
    </div>
    {children}
  </div>
);

// ============================================================================
// GPU Value Legend Component
// ============================================================================

interface GPUValueLegendProps {
  categories: string[];
  colors: AvailableChartColorsKeys[];
  data: Record<string, unknown>[];
  unit: string;
  valueFormatter?: (value: number) => string;
  /** When set (e.g. from tooltip hover), legend shows values at this point; otherwise last data point. */
  displayPoint?: Record<string, unknown> | null;
  activeCategory?: string;
  onCategoryClick?: (category: string) => void;
}

const GPUValueLegend: React.FC<GPUValueLegendProps> = ({
  categories,
  colors,
  data,
  unit,
  valueFormatter,
  displayPoint,
  activeCategory,
  onCategoryClick,
}) => {
  const point = displayPoint ?? data[data.length - 1];
  return (
    <div
      className="grid gap-2 mt-3"
      style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))' }}
    >
      {categories.map((category, idx) => {
        const value = point?.[category] as number | undefined;
        const formatted =
          value !== undefined
            ? valueFormatter
              ? valueFormatter(value)
              : `${value}${unit}`
            : 'N/A';
        const isActive = activeCategory === category;
        const isDimmed = activeCategory && activeCategory !== category;
        return (
          <button
            type="button"
            key={category}
            onClick={() => onCategoryClick?.(category)}
            className={`flex flex-col gap-0.5 rounded-md border px-3 py-2 cursor-pointer transition text-left ${
              isActive
                ? 'border-gray-400 dark:border-gray-500 bg-gray-100 dark:bg-gray-800'
                : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50'
            } ${isDimmed ? 'opacity-40' : ''}`}
          >
            <div className="flex items-center gap-1.5">
              <span
                className={`size-2.5 rounded-sm shrink-0 ${getColorClassName(colors[idx], 'bg')}`}
              />
              <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                {category}
              </span>
            </div>
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-50 whitespace-nowrap">
              {formatted}
            </span>
          </button>
        );
      })}
    </div>
  );
};

// ============================================================================
// Stories
// ============================================================================

export const BasicBarChart: Story = () => {
  const data = generateBarChartData({
    categories: ['Cluster A', 'Cluster B'],
    pointCount: 24,
    intervalMinutes: 60,
    baselines: [65, 45],
    fluctuation: 15,
    min: 0,
    max: 100,
  });

  return (
    <div className="w-full max-w-4xl p-4">
      <ChartCard title="GPU Utilization by Cluster">
        <BarChart
          data={data}
          index="date"
          categories={['Cluster A', 'Cluster B']}
          colors={['blue', 'emerald']}
          valueFormatter={(value: number) => `${value}%`}
          className="h-72"
        />
      </ChartCard>
    </div>
  );
};

export const StackedBarChart: Story = () => {
  const data = generateBarChartData({
    categories: ['Running', 'Waiting', 'Failed'],
    pointCount: 20,
    intervalMinutes: 15,
    baselines: [120, 30, 5],
    fluctuation: 20,
    min: 0,
  });

  return (
    <div className="w-full max-w-4xl p-4">
      <ChartCard title="Inference Requests">
        <BarChart
          data={data}
          index="date"
          categories={['Running', 'Waiting', 'Failed']}
          colors={['emerald', 'amber', 'red']}
          type="stacked"
          valueFormatter={(value: number) => `${Math.round(value)}`}
          className="h-72"
        />
      </ChartCard>
    </div>
  );
};

export const PercentStackedBarChart: Story = () => {
  const data = generateBarChartData({
    categories: ['GPU Compute', 'GPU Memory', 'GPU Idle'],
    pointCount: 12,
    intervalMinutes: 30,
    baselines: [55, 30, 15],
    fluctuation: 10,
    min: 5,
    max: 80,
  });

  return (
    <div className="w-full max-w-4xl p-4">
      <ChartCard title="GPU Resource Distribution">
        <BarChart
          data={data}
          index="date"
          categories={['GPU Compute', 'GPU Memory', 'GPU Idle']}
          colors={['blue', 'violet', 'gray']}
          type="percent"
          className="h-72"
        />
      </ChartCard>
    </div>
  );
};

export const SingleCategoryBarChart: Story = () => {
  const data = generateBarChartData({
    categories: ['GPU Utilization'],
    pointCount: 24,
    intervalMinutes: 60,
    baselines: [72],
    fluctuation: 20,
    min: 10,
    max: 100,
  });

  return (
    <div className="w-full max-w-4xl p-4">
      <ChartCard title="Cluster GPU Utilization">
        <BarChart
          data={data}
          index="date"
          categories={['GPU Utilization']}
          colors={['blue']}
          valueFormatter={(value: number) => `${Math.round(value)}%`}
          showLegend={false}
          className="h-72"
        />
      </ChartCard>
    </div>
  );
};

// ============================================================================
// Time Range Examples (1h, 24h, 7d)
// ============================================================================

const GPU_CATEGORIES = [
  'gpu-1',
  'gpu-2',
  'gpu-3',
  'gpu-4',
  'gpu-5',
  'gpu-6',
  'gpu-7',
  'gpu-8',
];

const GPU_COLORS: AvailableChartColorsKeys[] = [
  'blue',
  'emerald',
  'violet',
  'amber',
  'gray',
  'cyan',
  'pink',
  'lime',
];

type TimeRange = '1h' | '24h' | '7d';

const TimeRangeTabs: React.FC<{
  activeRange: TimeRange;
  onRangeChange: (range: TimeRange) => void;
}> = ({ activeRange, onRangeChange }) => (
  <div className="flex gap-1 rounded-md bg-gray-100 dark:bg-gray-800 p-0.5 w-fit">
    {(['1h', '24h', '7d'] as TimeRange[]).map((range) => (
      <button
        key={range}
        type="button"
        onClick={() => onRangeChange(range)}
        className={`px-3 py-1 text-xs rounded-md transition-colors ${
          activeRange === range
            ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm font-medium'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
        }`}
      >
        {range}
      </button>
    ))}
  </div>
);

export const GPUTemperature: Story = () => {
  const [timeRange, setTimeRange] = React.useState<TimeRange>('1h');
  const [activeGpu, setActiveGpu] = React.useState<string | undefined>(
    undefined,
  );
  const [hoveredPoint, setHoveredPoint] = React.useState<Record<
    string,
    unknown
  > | null>(null);
  const { selected, onSelectionChange, filteredCategories, filteredColors } =
    useGPUSelection(GPU_CATEGORIES, GPU_COLORS);

  const data1h = React.useMemo(
    () =>
      generateBarChartData({
        categories: GPU_CATEGORIES,
        pointCount: 12,
        intervalMinutes: 5,
        baselines: [58, 98, 25, 43, 42, 20, 21, 23],
        fluctuation: 5,
        min: 15,
        max: 105,
      }),
    [],
  );
  const data24h = React.useMemo(
    () =>
      generateBarChartData({
        categories: GPU_CATEGORIES,
        pointCount: 12,
        intervalMinutes: 120,
        baselines: [58, 98, 25, 43, 42, 20, 21, 23],
        fluctuation: 8,
        min: 15,
        max: 105,
      }),
    [],
  );
  const data7d = React.useMemo(
    () =>
      generateBarChartData({
        categories: GPU_CATEGORIES,
        pointCount: 12,
        intervalMinutes: 840,
        baselines: [58, 98, 25, 43, 42, 20, 21, 23],
        fluctuation: 12,
        min: 15,
        max: 105,
      }),
    [],
  );

  const dataByRange: Record<TimeRange, Record<string, unknown>[]> = {
    '1h': data1h,
    '24h': data24h,
    '7d': data7d,
  };
  const data = dataByRange[timeRange];

  return (
    <div className="w-full max-w-5xl p-4">
      <ChartCard
        title="GPU Temperature"
        headerRight={
          <div className="flex items-center gap-2">
            <GPUDeviceSelect
              allCategories={GPU_CATEGORIES}
              allColors={GPU_COLORS}
              selected={selected}
              onSelectionChange={onSelectionChange}
            />
            <TimeRangeTabs
              activeRange={timeRange}
              onRangeChange={setTimeRange}
            />
          </div>
        }
      >
        <BarChart
          data={data}
          index="date"
          categories={filteredCategories}
          colors={filteredColors}
          valueFormatter={(value: number) => `${value}°C`}
          className="h-72"
          showLegend={false}
          activeLegendProp={activeGpu}
          tooltipCallback={({ active, payload }) => {
            setHoveredPoint(
              active && payload?.length
                ? (payload[0].payload as Record<string, unknown>)
                : null,
            );
          }}
        />
        <GPUValueLegend
          categories={filteredCategories}
          colors={filteredColors}
          data={data}
          unit="°C"
          valueFormatter={(value: number) => `${value} °C`}
          displayPoint={hoveredPoint}
          activeCategory={activeGpu}
          onCategoryClick={(c) =>
            setActiveGpu((p) => (p === c ? undefined : c))
          }
        />
      </ChartCard>
    </div>
  );
};

export const GPUPowerUsage: Story = () => {
  const [timeRange, setTimeRange] = React.useState<TimeRange>('1h');
  const [activeGpu, setActiveGpu] = React.useState<string | undefined>(
    undefined,
  );
  const [hoveredPoint, setHoveredPoint] = React.useState<Record<
    string,
    unknown
  > | null>(null);
  const { selected, onSelectionChange, filteredCategories, filteredColors } =
    useGPUSelection(GPU_CATEGORIES, GPU_COLORS);

  const data1h = React.useMemo(
    () =>
      generateBarChartData({
        categories: GPU_CATEGORIES,
        pointCount: 12,
        intervalMinutes: 5,
        baselines: [19, 19.5, 20, 10, 15, 14, 13, 10],
        fluctuation: 3,
        min: 5,
        max: 130,
      }),
    [],
  );
  const data24h = React.useMemo(
    () =>
      generateBarChartData({
        categories: GPU_CATEGORIES,
        pointCount: 12,
        intervalMinutes: 120,
        baselines: [19, 19.5, 20, 10, 15, 14, 13, 10],
        fluctuation: 5,
        min: 5,
        max: 130,
      }),
    [],
  );
  const data7d = React.useMemo(
    () =>
      generateBarChartData({
        categories: GPU_CATEGORIES,
        pointCount: 12,
        intervalMinutes: 840,
        baselines: [19, 19.5, 20, 10, 15, 14, 13, 10],
        fluctuation: 8,
        min: 5,
        max: 130,
      }),
    [],
  );

  const dataByRange: Record<TimeRange, Record<string, unknown>[]> = {
    '1h': data1h,
    '24h': data24h,
    '7d': data7d,
  };
  const data = dataByRange[timeRange];

  return (
    <div className="w-full max-w-5xl p-4">
      <ChartCard
        title="GPU Power Usage"
        headerRight={
          <div className="flex items-center gap-2">
            <GPUDeviceSelect
              allCategories={GPU_CATEGORIES}
              allColors={GPU_COLORS}
              selected={selected}
              onSelectionChange={onSelectionChange}
            />
            <TimeRangeTabs
              activeRange={timeRange}
              onRangeChange={setTimeRange}
            />
          </div>
        }
      >
        <BarChart
          data={data}
          index="date"
          categories={filteredCategories}
          colors={filteredColors}
          valueFormatter={(value: number) => `${value}W`}
          className="h-72"
          showLegend={false}
          activeLegendProp={activeGpu}
          tooltipCallback={({ active, payload }) => {
            setHoveredPoint(
              active && payload?.length
                ? (payload[0].payload as Record<string, unknown>)
                : null,
            );
          }}
        />
        <GPUValueLegend
          categories={filteredCategories}
          colors={filteredColors}
          data={data}
          unit="W"
          valueFormatter={(value: number) => `${value}W`}
          displayPoint={hoveredPoint}
          activeCategory={activeGpu}
          onCategoryClick={(c) =>
            setActiveGpu((p) => (p === c ? undefined : c))
          }
        />
      </ChartCard>
    </div>
  );
};

export const LoadingState: Story = () => (
  <div className="w-full max-w-4xl p-4">
    <ChartCard title="GPU Utilization">
      <BarChart
        data={[]}
        index="date"
        categories={['Cluster A', 'Cluster B']}
        colors={['blue', 'emerald']}
        isLoading={true}
        className="h-72"
      />
    </ChartCard>
  </div>
);

// ============================================================================
// Interactive Playground
// ============================================================================

type PlaygroundArgs = {
  categoryCount: number;
  chartType: 'default' | 'stacked' | 'percent';
  showLegend: boolean;
  showGridLines: boolean;
  showXAxis: boolean;
  showYAxis: boolean;
  isLoading: boolean;
};

const categoryNames = [
  'Cluster A',
  'Cluster B',
  'Cluster C',
  'Cluster D',
  'Cluster E',
];

const categoryColors: AvailableChartColorsKeys[] = [
  'blue',
  'emerald',
  'violet',
  'amber',
  'pink',
];

export const Playground: Story<PlaygroundArgs> = ({
  categoryCount = 2,
  chartType = 'default',
  showLegend = true,
  showGridLines = true,
  showXAxis = true,
  showYAxis = true,
  isLoading = false,
}) => {
  const categories = categoryNames.slice(0, categoryCount);
  const colors = categoryColors.slice(0, categoryCount);

  const data = useMemo(
    () =>
      generateBarChartData({
        categories,
        pointCount: 24,
        intervalMinutes: 60,
        baselines: [65, 50, 70, 40, 55].slice(0, categoryCount),
        fluctuation: 15,
        min: 0,
        max: 100,
      }),
    [categoryCount],
  );

  return (
    <div className="w-full max-w-4xl p-4">
      <ChartCard title="Playground">
        <BarChart
          data={data}
          index="date"
          categories={categories}
          colors={colors}
          type={chartType}
          valueFormatter={(value: number) => `${Math.round(value)}%`}
          showLegend={showLegend}
          showGridLines={showGridLines}
          showXAxis={showXAxis}
          showYAxis={showYAxis}
          isLoading={isLoading}
          className="h-72"
        />
      </ChartCard>
    </div>
  );
};

Playground.args = {
  categoryCount: 2,
  chartType: 'default',
  showLegend: true,
  showGridLines: true,
  showXAxis: true,
  showYAxis: true,
  isLoading: false,
};

Playground.argTypes = {
  categoryCount: {
    control: { type: 'range', min: 1, max: 5, step: 1 },
    defaultValue: 2,
  },
  chartType: {
    control: { type: 'select' },
    options: ['default', 'stacked', 'percent'],
    defaultValue: 'default',
  },
  showLegend: {
    control: { type: 'boolean' },
    defaultValue: true,
  },
  showGridLines: {
    control: { type: 'boolean' },
    defaultValue: true,
  },
  showXAxis: {
    control: { type: 'boolean' },
    defaultValue: true,
  },
  showYAxis: {
    control: { type: 'boolean' },
    defaultValue: true,
  },
  isLoading: {
    control: { type: 'boolean' },
    defaultValue: false,
  },
};
