// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconExternalLink, IconMenu, IconX } from '@tabler/icons-react';

import { BreadcrumbItem, Breadcrumbs } from '../Breadcrumbs';

import { Button } from '../Buttons/Button';
import { Link } from '../Link';
import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';

import { toCamelCase } from '@amdenterpriseai/utils/app';
import { CollectionElement } from '@react-types/shared';

import { PageBreadcrumbs } from '@amdenterpriseai/types';

import { UserMenu } from '../Navigation/UserMenu';

interface AppBarProps {
  pageBreadcrumb?: PageBreadcrumbs;
  endContent?: React.ReactNode;
  additionalMenuItems?: CollectionElement<object>;
  documentationHref?: string;
  isMobileMenuOpen: boolean;
  onMobileMenuOpenChange: () => void;
}

export const AppBar: React.FC<AppBarProps> = ({
  pageBreadcrumb,
  endContent,
  additionalMenuItems,
  documentationHref,
  isMobileMenuOpen,
  onMobileMenuOpenChange,
}) => {
  const router = useRouter();
  const { pathname } = router;
  const { t } = useTranslation();
  const { t: tShared } = useTranslation('sharedComponents');
  const path = pathname.split('/').pop()?.replace(/^_/, '');
  const title = path
    ? (t(`pages.${toCamelCase(path)}.title` as any) as string)
    : t('pages.dashboard.title');
  const localePrefix =
    router.locale && router.locale !== router.defaultLocale
      ? `/${router.locale}`
      : '';
  const mobileMenuLabel = isMobileMenuOpen
    ? tShared('menu.actions.close')
    : tShared('menu.actions.open');

  return (
    <div className="md:py-4 px-4 md:px-8 flex items-center justify-between w-full border-b border-default dark:border-default">
      <div className="flex items-center">
        <Button
          isIconOnly
          variant="light"
          radius="sm"
          aria-label={mobileMenuLabel}
          aria-expanded={isMobileMenuOpen}
          aria-controls="mobile-nav-overlay"
          aria-haspopup="dialog"
          onPress={onMobileMenuOpenChange}
          className="h-16 w-11 min-w-11 bg-transparent px-0 data-[hover=true]:bg-transparent data-[pressed=true]:bg-transparent md:hidden"
        >
          {isMobileMenuOpen ? (
            <IconX aria-hidden="true" />
          ) : (
            <IconMenu aria-hidden="true" />
          )}
        </Button>
        {pageBreadcrumb ? (
          <Breadcrumbs
            size="lg"
            aria-label={tShared('breadcrumbs.label') as string}
          >
            {pageBreadcrumb.map((breadcrumb, idx) => (
              <BreadcrumbItem
                {...(breadcrumb.href
                  ? { href: `${localePrefix}${breadcrumb.href}` }
                  : {})}
                key={`page-breadcrumb-${idx}`}
              >
                {breadcrumb.title}
              </BreadcrumbItem>
            ))}
          </Breadcrumbs>
        ) : (
          <div className="text-md font-semibold text-foreground capitalize ml-6 sm:ml-3">
            {title}
          </div>
        )}
      </div>
      <div className="flex gap-3 md:gap-6 items-center">
        {endContent && <div>{endContent}</div>}

        {documentationHref && (
          <Button
            isExternal
            variant="outline"
            size="sm"
            href={documentationHref}
            endContent={<IconExternalLink size="14" stroke="2" />}
          >
            {tShared('links.documentation')}
          </Button>
        )}
        <UserMenu additionalMenuItems={additionalMenuItems} />
      </div>
    </div>
  );
};
