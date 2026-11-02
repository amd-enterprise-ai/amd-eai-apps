// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { Slider } from '@amdenterpriseai/components';

describe('Slider adapter', () => {
  it('renders with a numeric value', () => {
    render(
      <Slider
        aria-label="Test slider"
        value={0.5}
        minValue={0}
        maxValue={1}
        data-testid="slider"
      />,
    );
    expect(screen.getByTestId('slider')).toBeInTheDocument();
    expect(screen.getByRole('slider')).toBeInTheDocument();
  });

  it('calls onChange for single-value sliders', () => {
    const handleChange = vi.fn();
    render(
      <Slider
        aria-label="Test slider"
        value={0.25}
        minValue={0}
        maxValue={1}
        step={0.05}
        onChange={handleChange}
        data-testid="slider"
      />,
    );
    fireEvent.change(screen.getByRole('slider'), { target: { value: '0.5' } });
    expect(handleChange).toHaveBeenCalled();
  });

  it('respects step prop', () => {
    render(
      <Slider
        aria-label="Step slider"
        value={10}
        minValue={0}
        maxValue={100}
        step={5}
        data-testid="slider"
      />,
    );
    expect(screen.getByRole('slider')).toHaveAttribute('step', '5');
  });

  it('supports range values as a number array', () => {
    const RangeSlider = () => {
      const [value, setValue] = useState<[number, number]>([20, 80]);
      return (
        <Slider
          aria-label="Range slider"
          value={value}
          minValue={0}
          maxValue={100}
          onChange={(next) => {
            if (Array.isArray(next)) {
              setValue(next as [number, number]);
            }
          }}
          data-testid="range-slider"
        />
      );
    };
    render(<RangeSlider />);
    expect(screen.getByTestId('range-slider')).toBeInTheDocument();
    expect(screen.getAllByRole('slider')).toHaveLength(2);
  });

  it('passes isDisabled', () => {
    render(
      <Slider
        aria-label="Disabled slider"
        value={50}
        minValue={0}
        maxValue={100}
        isDisabled
        data-testid="slider"
      />,
    );
    expect(screen.getByRole('slider')).toBeDisabled();
  });

  it('renders mark labels when marks are provided', () => {
    render(
      <Slider
        aria-label="Marked slider"
        value={2}
        minValue={0}
        maxValue={8}
        marks={[{ value: 4, label: 'req' }]}
        data-testid="slider"
      />,
    );
    const mark = screen.getByText('req');
    expect(mark).toBeInTheDocument();
    expect(mark).toHaveClass('text-sm');
    expect(mark).toHaveClass('text-muted');
  });

  it('calls onChange with mark value when a mark is clicked', () => {
    const handleChange = vi.fn();
    render(
      <Slider
        aria-label="Marked slider"
        value={2}
        minValue={0}
        maxValue={8}
        marks={[{ value: 4, label: 'req' }]}
        onChange={handleChange}
        data-testid="slider"
      />,
    );
    fireEvent.click(screen.getByText('req'));
    expect(handleChange).toHaveBeenCalledWith(4);
  });

  it('renders description text', () => {
    render(
      <Slider
        aria-label="Described slider"
        value={50}
        minValue={0}
        maxValue={100}
        description="Select a value between 0 and 100"
        data-testid="slider"
      />,
    );
    expect(
      screen.getByText('Select a value between 0 and 100'),
    ).toBeInTheDocument();
  });

  it('renders error message when invalid', () => {
    render(
      <Slider
        aria-label="Invalid slider"
        value={25}
        minValue={0}
        maxValue={100}
        isInvalid
        errorMessage="Value must be at least 50"
        data-testid="slider"
      />,
    );
    const errorText = screen.getByText('Value must be at least 50');
    expect(errorText).toBeInTheDocument();
    expect(errorText).toHaveClass('text-danger');
  });

  it('hides error message when not invalid', () => {
    render(
      <Slider
        aria-label="Valid slider"
        value={75}
        minValue={0}
        maxValue={100}
        isInvalid={false}
        errorMessage="Value must be at least 50"
        data-testid="slider"
      />,
    );
    expect(
      screen.queryByText('Value must be at least 50'),
    ).not.toBeInTheDocument();
  });
});
