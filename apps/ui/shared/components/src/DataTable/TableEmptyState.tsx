// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

interface Props {
  text: string;
}

const TableEmptyState = ({ text }: Props) => (
  <div className="text-muted p-5 text-center">{text}</div>
);

export default TableEmptyState;
