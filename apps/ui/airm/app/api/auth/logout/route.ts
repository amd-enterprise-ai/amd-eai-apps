// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { getServerSession } from 'next-auth';
import { NextResponse } from 'next/server';

import { authOptions, logOutUrl } from '@amdenterpriseai/utils/server';

export async function POST() {
  const session = await getServerSession(authOptions);

  try {
    const path = await logOutUrl(session?.idToken);
    return NextResponse.json({ path });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
