// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { GetServerSidePropsContext } from 'next';

const ModelsPage = () => null;

export const getServerSideProps = (context: GetServerSidePropsContext) => ({
  redirect: {
    destination: `/${context.params?.project}/models/aim-catalog`,
    permanent: false,
  },
});

export default ModelsPage;
