// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { SecretUseCase } from '@amdenterpriseai/types';

import { createS3SecretRequest } from '@/lib/app/s3-secret';

describe('createS3SecretRequest', () => {
  it('builds an S3 request payload with access/secret key names', () => {
    expect(
      createS3SecretRequest({
        name: 'my-s3-secret',
        accessKeyId: 'AKIAEXAMPLE',
        secretAccessKey: 'secret-value',
      }),
    ).toEqual({
      displayName: 'my-s3-secret',
      useCase: SecretUseCase.S3,
      data: {
        accessKeyId: Buffer.from('AKIAEXAMPLE', 'utf-8').toString('base64'),
        secretAccessKey: Buffer.from('secret-value', 'utf-8').toString(
          'base64',
        ),
      },
    });
  });

  it('always emits only access and secret keys for S3 payload', () => {
    const payload = createS3SecretRequest({
      name: 'my-s3-secret',
      accessKeyId: 'AKIAEXAMPLE',
      secretAccessKey: 'secret-value',
    });
    expect(payload.data).not.toHaveProperty('awsEndpointUrl');
    expect(payload.data).not.toHaveProperty('awsDefaultRegion');
  });
});
