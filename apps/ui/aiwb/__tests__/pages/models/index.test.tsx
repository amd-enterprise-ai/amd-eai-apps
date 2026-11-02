// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { getServerSideProps } from '@/pages/[project]/models';

describe('Models route', () => {
  it('redirects to the first nested page', () => {
    expect(
      getServerSideProps({
        params: { project: 'test-project' },
      } as any),
    ).toEqual({
      redirect: {
        destination: '/test-project/models/aim-catalog',
        permanent: false,
      },
    });
  });
});
