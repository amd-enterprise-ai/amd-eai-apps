// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { NextPageContext } from 'next';

import { ErrorMessage } from '@/components/shared/PageErrorHandler/ErrorMessage';
import { getPageTranslations } from '@/lib/server/i18n';
import { ErrorCodes } from '@amdenterpriseai/types';

interface Props {
  error: string;
}

function Error({ error }: Props) {
  return <ErrorMessage code={ErrorCodes.SERVICE_ERROR} message={error} />;
}

export async function getStaticProps({ locale, err }: NextPageContext) {
  return {
    props: {
      ...(await getPageTranslations(locale ?? 'en')),
      error: err?.message || 'An unknown error occurred',
    },
  };
}

export default Error;
