// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';

import {
  DrawerPrimitive,
  DrawerBody,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
} from '@amdenterpriseai/components';

import '@testing-library/jest-dom';

describe('DrawerPrimitive adapter', () => {
  it('exposes compound sub-components', () => {
    expect(DrawerPrimitive.Body).toBe(DrawerBody);
    expect(DrawerPrimitive.Content).toBe(DrawerContent);
    expect(DrawerPrimitive.Footer).toBe(DrawerFooter);
    expect(DrawerPrimitive.Header).toBe(DrawerHeader);
  });

  it('renders with compound component API', () => {
    render(
      <DrawerPrimitive isOpen onOpenChange={() => {}}>
        <DrawerPrimitive.Content>
          <DrawerPrimitive.Header>Test Title</DrawerPrimitive.Header>
          <DrawerPrimitive.Body>Test Body</DrawerPrimitive.Body>
          <DrawerPrimitive.Footer>Test Footer</DrawerPrimitive.Footer>
        </DrawerPrimitive.Content>
      </DrawerPrimitive>,
    );

    expect(screen.getByText('Test Title')).toBeInTheDocument();
    expect(screen.getByText('Test Body')).toBeInTheDocument();
    expect(screen.getByText('Test Footer')).toBeInTheDocument();
  });

  it('renders with flat alias API', () => {
    render(
      <DrawerPrimitive isOpen onOpenChange={() => {}}>
        <DrawerContent>
          <DrawerHeader>Flat Title</DrawerHeader>
          <DrawerBody>Flat Body</DrawerBody>
          <DrawerFooter>Flat Footer</DrawerFooter>
        </DrawerContent>
      </DrawerPrimitive>,
    );

    expect(screen.getByText('Flat Title')).toBeInTheDocument();
    expect(screen.getByText('Flat Body')).toBeInTheDocument();
    expect(screen.getByText('Flat Footer')).toBeInTheDocument();
  });

  // Width utilities must stay aligned with DRAWER_DIALOG_PANEL_CLASS in DrawerPrimitive.tsx.
  it('applies shim drawer dialog width classes on the dialog surface', () => {
    render(
      <DrawerPrimitive isOpen onOpenChange={() => {}}>
        <DrawerContent>
          <DrawerHeader>Title</DrawerHeader>
          <DrawerBody>Body</DrawerBody>
        </DrawerContent>
      </DrawerPrimitive>,
    );

    const dialog =
      document.querySelector('[data-slot="drawer-dialog"]') ??
      screen.getByRole('dialog');
    expect(dialog).toHaveClass('w-[30rem]', 'max-w-[85vw]');
  });
});
