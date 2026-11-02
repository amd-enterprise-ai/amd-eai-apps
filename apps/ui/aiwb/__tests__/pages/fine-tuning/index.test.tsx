// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { getServerSideProps } from '@/pages/[project]/fine-tuning';

describe('Fine-tuning route', () => {
  it('redirects to the first nested page', () => {
    expect(
      getServerSideProps({
        params: { project: 'test-project' },
      } as any),
    ).toEqual({
      redirect: {
        destination: '/test-project/fine-tuning/datasets',
        permanent: false,
      },
    });
  });
});
