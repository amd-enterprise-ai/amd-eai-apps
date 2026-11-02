// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';

import {
  WorkloadGpuDevicesDetail,
  GpuDeviceEntry,
  GpuDevicesList,
} from '@/components/features/clusters/NodeWorkloadsTable/WorkloadGpuDevicesDetail';

import { GpuDeviceInfo } from '@/types/workloads';

describe('WorkloadGpuDevicesDetail', () => {
  const nodeName = 'worker-1';

  it('renders dash when no devices', () => {
    render(
      <WorkloadGpuDevicesDetail
        devices={[]}
        nodeName={nodeName}
        devicesLabel="0 devices"
      />,
    );

    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('renders device name for a single on-node device', () => {
    render(
      <WorkloadGpuDevicesDetail
        devices={[{ gpuId: '0', hostname: 'worker-1' }]}
        nodeName={nodeName}
        devicesLabel="1 device"
      />,
    );

    expect(screen.getByText('gpu-1')).toBeInTheDocument();
  });

  it('renders devicesLabel with underline for multiple devices', () => {
    render(
      <WorkloadGpuDevicesDetail
        devices={[
          { gpuId: '0', hostname: 'worker-1' },
          { gpuId: '1', hostname: 'worker-1' },
        ]}
        nodeName={nodeName}
        devicesLabel="2 devices"
      />,
    );

    const label = screen.getByText('2 devices');
    expect(label).toBeInTheDocument();
    expect(label).toHaveClass('cursor-pointer', 'underline');
  });

  it('converts zero-based gpuId to one-based display name', () => {
    render(
      <WorkloadGpuDevicesDetail
        devices={[{ gpuId: '7', hostname: 'worker-1' }]}
        nodeName={nodeName}
        devicesLabel="1 device"
      />,
    );

    expect(screen.getByText('gpu-8')).toBeInTheDocument();
  });
});

describe('GpuDeviceEntry', () => {
  it('renders only device name when on-node', () => {
    render(
      <GpuDeviceEntry
        device={{ gpuId: '0', hostname: 'worker-1' }}
        isOnNode={true}
      />,
    );

    const span = screen.getByText('gpu-1');
    expect(span).toBeInTheDocument();
    expect(span).not.toHaveClass('text-muted');
  });

  it('renders hostname with chevron and muted text when off-node', () => {
    const { container } = render(
      <GpuDeviceEntry
        device={{ gpuId: '2', hostname: 'worker-2' }}
        isOnNode={false}
      />,
    );

    const wrapper = container.querySelector('span.text-muted')!;
    expect(wrapper).toBeInTheDocument();
    expect(wrapper).toHaveTextContent('worker-2');
    expect(wrapper).toHaveTextContent('gpu-3');
  });
});

describe('GpuDevicesList', () => {
  const nodeName = 'worker-1';

  it('lists all devices with hostname and device name', () => {
    const devices: GpuDeviceInfo[] = [
      { gpuId: '0', hostname: 'worker-1' },
      { gpuId: '1', hostname: 'worker-2' },
    ];

    render(<GpuDevicesList devices={devices} nodeName={nodeName} />);

    const listItems = screen.getAllByRole('listitem');
    expect(listItems).toHaveLength(2);
    expect(listItems[0]).toHaveTextContent('worker-1');
    expect(listItems[0]).toHaveTextContent('gpu-1');
    expect(listItems[1]).toHaveTextContent('worker-2');
    expect(listItems[1]).toHaveTextContent('gpu-2');
  });

  it('applies muted text only to off-node devices', () => {
    const devices: GpuDeviceInfo[] = [
      { gpuId: '0', hostname: 'worker-1' },
      { gpuId: '0', hostname: 'worker-2' },
    ];

    render(<GpuDevicesList devices={devices} nodeName={nodeName} />);

    const listItems = screen.getAllByRole('listitem');
    const spans = listItems.map((li) => li.querySelector('span')!);
    expect(spans[0]).not.toHaveClass('text-muted');
    expect(spans[1]).toHaveClass('text-muted');
  });

  it('sorts devices by hostname then gpuId', () => {
    const devices: GpuDeviceInfo[] = [
      { gpuId: '2', hostname: 'worker-2' },
      { gpuId: '0', hostname: 'worker-1' },
      { gpuId: '1', hostname: 'worker-2' },
    ];

    render(<GpuDevicesList devices={devices} nodeName={nodeName} />);

    const listItems = screen.getAllByRole('listitem');
    expect(listItems).toHaveLength(3);
    expect(listItems[0]).toHaveTextContent('worker-1');
    expect(listItems[0]).toHaveTextContent('gpu-1');
    expect(listItems[1]).toHaveTextContent('worker-2');
    expect(listItems[1]).toHaveTextContent('gpu-2');
    expect(listItems[2]).toHaveTextContent('worker-2');
    expect(listItems[2]).toHaveTextContent('gpu-3');
  });
});
