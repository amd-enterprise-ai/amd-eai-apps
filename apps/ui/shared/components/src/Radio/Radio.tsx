// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// HeroUI v3 ships Radio as a compound component (`Radio.Content` >
// `Radio.Control` > `Radio.Indicator`, plus a `Label`) and expects the group's
// own label to be supplied as a child. This adapter presents the flat surface
// the rest of the design system uses — `<RadioGroup label=…>` wrapping
// `<Radio value=…>label</Radio>` — by composing the subcomponents internally.
import {
  Description,
  FieldError,
  Label,
  Radio as HeroUIRadio,
  RadioGroup as HeroUIRadioGroup,
} from '@heroui/react';
import type { RadioGroupRootProps, RadioRootProps } from '@heroui/react';
import type { ReactNode } from 'react';

import { InfoTooltip } from '../internal/InfoTooltip';

export interface RadioGroupProps
  extends Omit<RadioGroupRootProps, 'children' | 'onChange'> {
  children?: ReactNode;
  /** Field label rendered above the options. */
  label?: ReactNode;
  /** Content shown in a tooltip next to the field label. */
  tooltipContent?: ReactNode;
  /** Helper text rendered below the options. */
  description?: ReactNode;
  /** Validation message rendered below the options when `isInvalid`. */
  errorMessage?: ReactNode;
  onChange?: (value: string) => void;
}

export const RadioGroup = ({
  children,
  label,
  tooltipContent,
  description,
  errorMessage,
  ...props
}: RadioGroupProps) => (
  <HeroUIRadioGroup {...props}>
    {label != null && (
      <div className="flex w-full items-center gap-1">
        <Label>{label}</Label>
        {tooltipContent != null && <InfoTooltip content={tooltipContent} />}
      </div>
    )}
    {children}
    {description != null && (
      <Description className="w-full">{description}</Description>
    )}
    {errorMessage != null && (
      <FieldError className="w-full">{errorMessage}</FieldError>
    )}
  </HeroUIRadioGroup>
);

export interface RadioProps extends Omit<RadioRootProps, 'children'> {
  children?: ReactNode;
  description?: ReactNode;
}

// `Radio.Content` renders the `<label>` that wraps the input, so the option's
// text is its accessible name as-is. Wrapping it in `Label` would instead reuse
// the enclosing group's label id and emit duplicate ids into the document.
export const Radio = ({ children, description, ...props }: RadioProps) => (
  <HeroUIRadio {...props}>
    <HeroUIRadio.Content>
      <HeroUIRadio.Control>
        <HeroUIRadio.Indicator />
      </HeroUIRadio.Control>
      {children}
    </HeroUIRadio.Content>
    {description != null && description !== '' ? (
      <Description>{description}</Description>
    ) : null}
  </HeroUIRadio>
);

export default RadioGroup;
