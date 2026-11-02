// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Description, Slider as HeroUISlider, Label, cn } from '@heroui/react';
import React from 'react';

type SliderMark = { value: number; label: string };

type SliderState = {
  getValuePercent: (value: number) => number;
  values: number[];
};

type RootProps = React.ComponentProps<typeof HeroUISlider>;

export interface SliderProps extends Omit<RootProps, 'children'> {
  children?: React.ReactNode;
  /** Field label rendered above the track. */
  label?: React.ReactNode;
  /** Formats the current value rendered in the slider output. */
  getValue?: (value: number) => React.ReactNode;
  marks?: SliderMark[];
  description?: React.ReactNode;
  errorMessage?: React.ReactNode;
  isInvalid?: boolean;
  isRequired?: boolean;
}

const MARK_CLASSES =
  'absolute top-1/2 mt-1 -translate-x-1/2 translate-y-1/2 cursor-pointer text-sm text-muted';

const SliderMarkItem = ({
  mark,
  state,
  onChange,
}: {
  mark: SliderMark;
  state: SliderState;
  onChange?: (value: number | number[]) => void;
}) => {
  const percent = state.getValuePercent(mark.value);
  return (
    <div
      data-slot="mark"
      className={MARK_CLASSES}
      style={{ left: `${percent * 100}%` }}
      onMouseDown={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        if (!onChange) return;
        if (state.values.length === 1) {
          onChange(mark.value);
          return;
        }
        const [leftThumbVal, rightThumbVal] = state.values;
        if (mark.value < leftThumbVal) {
          onChange([mark.value, rightThumbVal]);
        } else if (mark.value > rightThumbVal) {
          onChange([leftThumbVal, mark.value]);
        } else if (
          Math.abs(mark.value - leftThumbVal) <
          Math.abs(mark.value - rightThumbVal)
        ) {
          onChange([mark.value, rightThumbVal]);
        } else {
          onChange([leftThumbVal, mark.value]);
        }
      }}
    >
      {mark.label}
    </div>
  );
};

export const Slider: React.FC<SliderProps> = ({
  children,
  label,
  getValue,
  marks,
  description,
  errorMessage,
  isInvalid,
  isRequired,
  className,
  onChange,
  ...rest
}) => {
  const valueOrDefault = rest.value ?? rest.defaultValue;
  const thumbCount =
    Array.isArray(valueOrDefault) && valueOrDefault.length > 1
      ? valueOrDefault.length
      : 1;
  const hasMarks = (marks?.length ?? 0) > 0;

  return (
    <div className={cn('flex w-full flex-col gap-1.5', className)}>
      <HeroUISlider
        className={cn(hasMarks && 'mb-5')}
        onChange={onChange}
        {...rest}
      >
        {label != null ? (
          <div className="flex items-center justify-between">
            <Label isRequired={isRequired} isInvalid={isInvalid}>
              {label}
            </Label>
            <HeroUISlider.Output>
              {getValue
                ? (renderProps: {
                    state: { getThumbValue: (index: number) => number };
                  }) => getValue(renderProps.state.getThumbValue(0))
                : null}
            </HeroUISlider.Output>
          </div>
        ) : null}
        <HeroUISlider.Track>
          {(trackRenderProps) => {
            const state = trackRenderProps.state as SliderState;
            return (
              <>
                <HeroUISlider.Fill />
                {Array.from({ length: thumbCount }, (_, index) => (
                  <HeroUISlider.Thumb key={index} index={index} />
                ))}
                {marks?.map((mark, index) => (
                  <SliderMarkItem
                    key={`${mark.value}-${index}`}
                    mark={mark}
                    state={state}
                    onChange={onChange}
                  />
                ))}
              </>
            );
          }}
        </HeroUISlider.Track>
        {children}
      </HeroUISlider>
      {description ? <Description>{description}</Description> : null}
      {isInvalid && errorMessage ? (
        <span className="text-danger text-xs">{errorMessage}</span>
      ) : null}
    </div>
  );
};

export default Slider;
