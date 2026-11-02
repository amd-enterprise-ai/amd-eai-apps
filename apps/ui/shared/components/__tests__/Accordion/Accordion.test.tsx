// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';
import { Accordion, AccordionItem } from '@amdenterpriseai/components';

describe('Accordion adapter', () => {
  it('allows descendant focus rings when panel is expanded', () => {
    render(
      <Accordion defaultSelectedKeys={['advanced']}>
        <AccordionItem id="advanced" title="Advanced settings">
          <input aria-label="Batch size" />
        </AccordionItem>
      </Accordion>,
    );

    expect(screen.getByLabelText('Batch size')).toBeInTheDocument();
    expect(document.querySelector('.accordion__panel')).toHaveClass(
      'data-[expanded=true]:!overflow-visible',
    );
  });
});
