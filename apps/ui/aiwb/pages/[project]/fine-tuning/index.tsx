// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { GetServerSidePropsContext } from 'next';

const FineTuningPage = () => null;

export const getServerSideProps = (context: GetServerSidePropsContext) => ({
  redirect: {
    destination: `/${context.params?.project}/fine-tuning/datasets`,
    permanent: false,
  },
});

export default FineTuningPage;
