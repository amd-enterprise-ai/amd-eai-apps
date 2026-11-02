// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Card as HeroUICard, cn, type CardVariants } from '@heroui/react';
import React from 'react';

/**
 * Thin wrapper around HeroUI v3 `Card` that keeps the `CardBody` export name
 * (`Card.Content` in HeroUI) and the `Card.Header` / `Card.Body` compound API.
 */
export interface CardProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'color'> {
  children: React.ReactNode;
  className?: string;
  variant?: CardVariants['variant'];
}

const CardBase: React.FC<CardProps> = ({ children, className, ...rest }) => (
  <HeroUICard className={className} {...rest}>
    {children}
  </HeroUICard>
);

export const CardContent = HeroUICard.Content;
export const CardBody = CardContent;

// HeroUI v3 Card.Header defaults to justify-center; override to justify-start
// so call sites that pass flex items-center get left-aligned headers.
const CardHeaderWrapper = ({
  className,
  ...props
}: React.ComponentProps<typeof HeroUICard.Header>) => (
  <HeroUICard.Header className={cn('justify-start', className)} {...props} />
);
CardHeaderWrapper.displayName = 'CardHeader';

export const CardHeader = CardHeaderWrapper;
export const CardFooter = HeroUICard.Footer;

export const Card = Object.assign(CardBase, {
  Body: CardBody,
  Content: CardContent,
  Header: CardHeader,
  Title: HeroUICard.Title,
  Description: HeroUICard.Description,
  Footer: CardFooter,
});
