// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  DropdownItemProps,
  SelectItemProps,
} from '@amdenterpriseai/components';

import { FilterComponentType } from './enums/filters';
import { FilterOperator } from './enums/server-collection';

export type FilterOption<T> = {
  label: string;
  key: T;
  props?: SelectItemProps | DropdownItemProps;
};

export type FilterComponentField = {
  name: string;
  label: string;
  icon?: React.ReactNode;
  placeholder?: string;
  className?: string;
  variant?: 'primary' | 'secondary';
  allowEmptySelection?: boolean;
  allowMultipleSelection?: boolean;
  defaultSelectedValues?: (string | number | boolean)[];
  type: FilterComponentType;
  fields?: FilterOption<string | number | boolean>[];
  showFieldDescription?: boolean;
};

export type FilterFieldMapping = {
  [key: string]: FilterComponentField;
};

export type ClientSideFilterField<T> = {
  field: keyof T;
  path?: string;
};

export type ClientSideDataFilterBase = {
  values: string[];
  exact?: boolean;
  showAllWhenEmpty?: boolean;
};

export type ClientSideDataFilter<T> =
  | ({
      field: keyof T;
      path?: string;
      compositeFields?: undefined;
    } & ClientSideDataFilterBase)
  | ({
      field?: undefined;
      path?: undefined;
      compositeFields: ClientSideFilterField<T>[];
    } & ClientSideDataFilterBase);

export type FilterValueMap = {
  [key: string]: string[];
};

export type ServerSideFilterOperatorMap = {
  [key: string]: FilterOperator;
};
