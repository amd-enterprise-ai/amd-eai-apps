// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Link } from '../Link';
import NextLink from 'next/link';
import { useTranslation } from 'next-i18next';

interface LinkToastProps {
  message: string;
  href: string;
  linkLabel?: string;
}

export const LinkToast = ({ message, href, linkLabel }: LinkToastProps) => {
  const { t } = useTranslation('sharedComponents');

  return (
    <div className="flex items-center gap-1 pr-3">
      {message} {'\u2008'}
      <Link as={NextLink} href={href} className="ml-1">
        {linkLabel ?? t('actions.showDetails.title')}
      </Link>
    </div>
  );
};

LinkToast.displayName = 'LinkToast';
