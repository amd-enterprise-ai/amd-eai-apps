// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import NextAuth from 'next-auth';
import { NextRequest } from 'next/server';

import { getAuthOptions } from '@amdenterpriseai/utils/server';

// The provider endpoints come from OIDC discovery, so the options are async.
async function handler(
  request: NextRequest,
  context: { params: Promise<{ nextauth: string[] }> },
) {
  return NextAuth(request, context, await getAuthOptions());
}

export { handler as GET, handler as POST };
