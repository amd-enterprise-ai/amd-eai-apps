// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import React, { useState, useMemo } from 'react';
import { Select, SelectItem } from '@amdenterpriseai/components';

import { IconCpu } from '@tabler/icons-react';
import { LineChart } from '../../../src/Metrics/LineChart';
import { DynamicValueLegend } from '../../../src/Metrics/DynamicValueLegend';
import {
  AvailableChartColorsKeys,
  chartColors,
  ColorUtility,
} from '@amdenterpriseai/types';

export default {
  title: 'Components/Metrics/LineChart',
} satisfies StoryDefault;

// ============================================================================
// Mock Data Utilities
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

/**
 * Generates time-series data for multiple GPUs over the last N minutes.
 * Each GPU gets a baseline value with random fluctuation.
 */
function generateGPUTimeSeriesData(config: {
  gpuCount?: number;
  pointCount?: number;
  intervalMinutes?: number;
  baselines: number[];
  fluctuation: number;
  min?: number;
  max?: number;
}): Record<string, unknown>[] {
  const {
    gpuCount = 8,
    pointCount = 60,
    intervalMinutes = 1,
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
      timestamp: timestamp.toISOString(),
    };

    for (let g = 0; g < gpuCount; g++) {
      const baseline = baselines[g % baselines.length];
      const noise = (Math.random() - 0.5) * 2 * fluctuation;
      // Gradual drift to make charts look more realistic
      const drift =
        Math.sin((i / pointCount) * Math.PI * 2 + g) * (fluctuation * 0.5);
      const value = Math.max(min, Math.min(max, baseline + noise + drift));
      point[GPU_CATEGORIES[g]] = Math.round(value * 10) / 10;
    }

    data.push(point);
  }

  return data;
}

// ============================================================================
// Tab Toggle Component
// ============================================================================

interface MetricTab {
  id: string;
  label: string;
}

interface MetricTabsProps {
  tabs: MetricTab[];
  activeTab: string;
  onTabChange: (id: string) => void;
}

const MetricTabs: React.FC<MetricTabsProps> = ({
  tabs,
  activeTab,
  onTabChange,
}) => (
  <div className="flex gap-1 rounded-md bg-gray-100 dark:bg-gray-800 p-0.5 w-fit">
    {tabs.map((tab) => (
      <button
        key={tab.id}
        type="button"
        onClick={() => onTabChange(tab.id)}
        className={`px-3 py-1 text-xs rounded-md transition-colors ${
          activeTab === tab.id
            ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm font-medium'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
        }`}
      >
        {tab.label}
      </button>
    ))}
  </div>
);

// ============================================================================
// GPU Device Select Component
// ============================================================================

const getColorClassName = (
  color: AvailableChartColorsKeys,
  type: ColorUtility,
): string => chartColors[color]?.[type] ?? 'bg-gray-500';

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
// Metric Data Generators
// ============================================================================

const gpuUtilizationData = {
  'Memory utilization': generateGPUTimeSeriesData({
    baselines: [79, 60, 80, 85, 79, 15, 75, 70],
    fluctuation: 8,
    min: 0,
    max: 100,
  }),
  'Clock speed': generateGPUTimeSeriesData({
    baselines: [1800, 1750, 1820, 1790, 1810, 1770, 1800, 1760],
    fluctuation: 50,
    min: 1500,
    max: 2000,
  }),
  'GPU usage': generateGPUTimeSeriesData({
    baselines: [65, 55, 70, 72, 68, 12, 62, 58],
    fluctuation: 10,
    min: 0,
    max: 100,
  }),
};

const pcieTrafficData = {
  'PCIe bandwidth': generateGPUTimeSeriesData({
    baselines: [58, 82, 80, 58, 82, 84, 70, 81],
    fluctuation: 10,
    pointCount: 12,
    intervalMinutes: 5,
    min: 0,
    max: 100,
  }),
  'PCIe performance': generateGPUTimeSeriesData({
    baselines: [45, 70, 65, 50, 72, 75, 60, 68],
    fluctuation: 8,
    pointCount: 12,
    intervalMinutes: 5,
    min: 0,
    max: 100,
  }),
};

// ============================================================================
// Stories
// ============================================================================

export const BasicLineChart: Story = () => {
  const data = generateGPUTimeSeriesData({
    gpuCount: 3,
    pointCount: 30,
    baselines: [60, 40, 80],
    fluctuation: 10,
    min: 0,
    max: 100,
  });

  return (
    <div className="w-full max-w-4xl p-4">
      <ChartCard title="Basic Multi-Series LineChart">
        <LineChart
          data={data}
          index="timestamp"
          categories={['gpu-1', 'gpu-2', 'gpu-3']}
          colors={['blue', 'emerald', 'violet']}
          valueFormatter={(value: number) => `${value}%`}
          minValue={0}
          maxValue={100}
          className="h-64"
        />
      </ChartCard>
    </div>
  );
};

export const GPUUtilization: Story = () => {
  const tabs: MetricTab[] = [
    { id: 'Memory utilization', label: 'Memory utilization' },
    { id: 'Clock speed', label: 'Clock speed' },
    { id: 'GPU usage', label: 'GPU usage' },
  ];
  const [activeTab, setActiveTab] = useState(tabs[0].id);
  const [activeGpu, setActiveGpu] = useState<string | undefined>(undefined);
  const [hoveredPoint, setHoveredPoint] = useState<Record<
    string,
    unknown
  > | null>(null);
  const { selected, onSelectionChange, filteredCategories, filteredColors } =
    useGPUSelection(GPU_CATEGORIES, GPU_COLORS);

  const data = gpuUtilizationData[activeTab as keyof typeof gpuUtilizationData];

  const isClockSpeed = activeTab === 'Clock speed';
  const valueFormatter = isClockSpeed
    ? (value: number) => `${value} MHz`
    : (value: number) => `${value}%`;
  const unit = isClockSpeed ? ' MHz' : '%';

  return (
    <div className="w-full max-w-5xl p-4">
      <ChartCard
        title="GPU Utilization"
        headerRight={
          <div className="flex items-center gap-2">
            <GPUDeviceSelect
              allCategories={GPU_CATEGORIES}
              allColors={GPU_COLORS}
              selected={selected}
              onSelectionChange={onSelectionChange}
            />
            <MetricTabs
              tabs={tabs}
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />
          </div>
        }
      >
        <LineChart
          data={data}
          index="timestamp"
          categories={filteredCategories}
          colors={filteredColors}
          valueFormatter={valueFormatter}
          minValue={isClockSpeed ? 1400 : 0}
          maxValue={isClockSpeed ? 2100 : 100}
          showLegend={false}
          className="h-72"
          yAxisWidth={64}
          activeLegendProp={activeGpu}
          tooltipCallback={({ active, payload }) => {
            setHoveredPoint(
              active && payload?.length
                ? (payload[0].payload as Record<string, unknown>)
                : null,
            );
          }}
        />
        <DynamicValueLegend
          categories={filteredCategories}
          colors={filteredColors}
          data={data}
          unit={unit}
          valueFormatter={valueFormatter}
          displayPoint={hoveredPoint}
          activeCategory={activeGpu}
          onCategoryClick={(category) =>
            setActiveGpu((prev) => (prev === category ? undefined : category))
          }
        />
      </ChartCard>
    </div>
  );
};

export const PCIETraffic: Story = () => {
  const tabs: MetricTab[] = [
    { id: 'PCIe bandwidth', label: 'PCIe bandwidth' },
    { id: 'PCIe performance', label: 'PCIe performance' },
  ];
  const [activeTab, setActiveTab] = useState(tabs[0].id);
  const [activeGpu, setActiveGpu] = useState<string | undefined>(undefined);
  const [hoveredPoint, setHoveredPoint] = useState<Record<
    string,
    unknown
  > | null>(null);
  const { selected, onSelectionChange, filteredCategories, filteredColors } =
    useGPUSelection(GPU_CATEGORIES, GPU_COLORS);

  const data = pcieTrafficData[activeTab as keyof typeof pcieTrafficData];
  const valueFormatter = (value: number) => `${value} Mbps`;

  return (
    <div className="w-full max-w-5xl p-4">
      <ChartCard
        title="PCIe Traffic"
        headerRight={
          <div className="flex items-center gap-2">
            <GPUDeviceSelect
              allCategories={GPU_CATEGORIES}
              allColors={GPU_COLORS}
              selected={selected}
              onSelectionChange={onSelectionChange}
            />
            <MetricTabs
              tabs={tabs}
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />
          </div>
        }
      >
        <LineChart
          data={data}
          index="timestamp"
          categories={filteredCategories}
          colors={filteredColors}
          valueFormatter={valueFormatter}
          minValue={0}
          maxValue={100}
          showLegend={false}
          showDots={true}
          className="h-72"
          yAxisWidth={64}
          activeLegendProp={activeGpu}
          tooltipCallback={({ active, payload }) => {
            setHoveredPoint(
              active && payload?.length
                ? (payload[0].payload as Record<string, unknown>)
                : null,
            );
          }}
        />
        <DynamicValueLegend
          categories={filteredCategories}
          colors={filteredColors}
          data={data}
          unit=" Mbps"
          valueFormatter={valueFormatter}
          displayPoint={hoveredPoint}
          activeCategory={activeGpu}
          onCategoryClick={(category) =>
            setActiveGpu((prev) => (prev === category ? undefined : category))
          }
        />
      </ChartCard>
    </div>
  );
};

export const LoadingState: Story = () => (
  <div className="w-full max-w-5xl p-4">
    <ChartCard title="GPU Utilization">
      <LineChart
        data={[]}
        index="timestamp"
        categories={GPU_CATEGORIES}
        colors={GPU_COLORS}
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
  gpuCount: number;
  showLegend: boolean;
  showGridLines: boolean;
  showXAxis: boolean;
  showYAxis: boolean;
  isLoading: boolean;
};

export const Playground: Story<PlaygroundArgs> = ({
  gpuCount = 4,
  showLegend = true,
  showGridLines = true,
  showXAxis = true,
  showYAxis = true,
  isLoading = false,
}) => {
  const categories = GPU_CATEGORIES.slice(0, gpuCount);
  const colors = GPU_COLORS.slice(0, gpuCount);
  const data = useMemo(
    () =>
      generateGPUTimeSeriesData({
        gpuCount,
        pointCount: 60,
        baselines: [79, 60, 80, 85, 79, 15, 75, 70].slice(0, gpuCount),
        fluctuation: 8,
        min: 0,
        max: 100,
      }),
    [gpuCount],
  );

  return (
    <div className="w-full max-w-5xl p-4">
      <ChartCard title="Playground">
        <LineChart
          data={data}
          index="timestamp"
          categories={categories}
          colors={colors}
          valueFormatter={(value: number) => `${value}%`}
          minValue={0}
          maxValue={100}
          showLegend={showLegend}
          showGridLines={showGridLines}
          showXAxis={showXAxis}
          showYAxis={showYAxis}
          isLoading={isLoading}
          className="h-72"
          yAxisWidth={64}
        />
        {!showLegend && (
          <DynamicValueLegend
            categories={categories}
            colors={colors}
            data={data}
            unit="%"
          />
        )}
      </ChartCard>
    </div>
  );
};

Playground.args = {
  gpuCount: 4,
  showLegend: true,
  showGridLines: true,
  showXAxis: true,
  showYAxis: true,
  isLoading: false,
};

Playground.argTypes = {
  gpuCount: {
    control: { type: 'range', min: 1, max: 8, step: 1 },
    defaultValue: 4,
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
