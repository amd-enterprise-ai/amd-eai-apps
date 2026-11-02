// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  type Selection,
  Button,
  Dropdown,
  DropdownItem,
  DropdownMenu,
  DropdownTrigger,
  ActionButton,
  RelevantDocs,
  AiwbDocsPage,
  aiwbDocumentationMapping,
  ConfirmationModal,
  ServerSideDataTable,
  ChipDisplay,
  DateDisplay,
  ActionsToolbar,
  NoDataDisplay,
} from '@amdenterpriseai/components';
import {
  useDebouncedCallback,
  useOverlayState,
  useSystemToast,
} from '@amdenterpriseai/hooks';
import { IconChevronDown, IconCloudUpload } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { GetServerSidePropsContext } from 'next';
import { useCallback, useMemo, useState } from 'react';

import { useTranslation } from 'next-i18next';

import {
  DOCS_WORKBENCH_BASE,
  displayHumanReadableBytes,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';
import {
  deleteDatasets,
  downloadDatasetById,
  getDatasetTypeVariants,
  listDatasets,
} from '@/lib/app/datasets';
import { getPageTranslations } from '@/lib/server/i18n';

import { TableColumns } from '@amdenterpriseai/types';
import { CollectionRequestParams } from '@amdenterpriseai/types';
import { FilterParams } from '@amdenterpriseai/types';
import { SortDirection } from '@amdenterpriseai/types';
import type { components } from '@/types/api';
import type { DatasetType } from '@/types/datasets';
import { FilterComponentType } from '@amdenterpriseai/types';
import { FilterValueMap } from '@amdenterpriseai/types';
import { DatasetUpload } from '@/components/features/datasets/DatasetUpload';

import { useProject } from '@/contexts/ProjectContext';
import { buildPageBreadcrumb } from '@/lib/app/breadcrumbs';

const DatasetsTableField = {
  TYPE: 'type',
  NAME: 'name',
  DESCRIPTION: 'description',
  SIZE: 'sizeBytes',
  CREATED_BY: 'createdBy',
  CREATED_AT: 'createdAt',
} as const;

type DatasetsTableField =
  (typeof DatasetsTableField)[keyof typeof DatasetsTableField];

type DatasetResponse = components['schemas']['DatasetResponse'];

const API_REQUEST_DEFAULTS: CollectionRequestParams<DatasetResponse> = {
  page: 1,
  pageSize: 10,
  sort: [
    {
      field: 'createdAt',
      direction: SortDirection.DESC,
    },
  ],
  filter: [],
};

const DatasetsPage: React.FC & WithDocumentationLink = () => {
  const { toast } = useSystemToast();
  const { t } = useTranslation('datasets');
  const { activeProject } = useProject();
  const queryClient = useQueryClient();

  const [tableParams, setTableParams] =
    useState<CollectionRequestParams<DatasetResponse>>(API_REQUEST_DEFAULTS);
  const [selectedTypeFilter, setSelectedTypeFilter] = useState<
    DatasetType | undefined
  >(undefined);
  const [datasetUploadVisible, setDatasetUploadVisible] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<Selection>(new Set([]));
  const {
    isOpen: isDeleteConfirmOpen,
    onOpen: onDeleteConfirmOpen,
    onOpenChange: onDeleteConfirmOpenChange,
  } = useOverlayState();

  const fetchParams = useMemo(
    () => ({
      page: tableParams.page,
      pageSize: tableParams.pageSize,
      type: selectedTypeFilter,
    }),
    [tableParams.page, tableParams.pageSize, selectedTypeFilter],
  );

  const {
    data: paginatedDatasets,
    isLoading,
    isFetching,
    refetch,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['project', activeProject, 'datasets', fetchParams],
    queryFn: () => listDatasets(activeProject!, fetchParams),
    enabled: !!activeProject,
  });

  const data = paginatedDatasets?.data ?? [];
  const total = paginatedDatasets?.pagination.total ?? 0;

  const typeFilterOptions = useMemo(
    () => [
      {
        name: t('types.Fine-tuning'),
        type: 'Fine-tuning',
      },
    ],
    [t],
  );

  const columns: TableColumns<DatasetsTableField | null> = [
    { key: DatasetsTableField.TYPE },
    { key: DatasetsTableField.NAME },
    { key: DatasetsTableField.DESCRIPTION },
    { key: DatasetsTableField.SIZE },
    { key: DatasetsTableField.CREATED_BY },
    { key: DatasetsTableField.CREATED_AT },
  ];

  const actions = [
    {
      key: 'download',
      aria: 'Download',
      className: '',
      color: 'default',
      onPress: (item: DatasetResponse) => {
        handleDownload(item);
      },
      label: t('list.actions.download.label'),
    },
    {
      key: 'delete',
      className: 'text-danger',
      color: 'danger',
      onPress: (item: DatasetResponse) => {
        handleDelete(item.id);
      },
      label: t('list.actions.delete.label'),
    },
  ];

  const handleSelectionChange = (keys: Selection) => {
    setSelectedKeys(keys);
  };

  const handleDelete = useCallback(
    (id: string) => {
      setSelectedKeys(new Set([id]));
      onDeleteConfirmOpenChange();
    },
    [onDeleteConfirmOpenChange],
  );

  const refreshDatasets = () => {
    refetch();
  };

  const handleDownload = async (item: DatasetResponse) => {
    let dismissed = false;
    const toastKey = toast(t('download.indicator.preparing.title'), {
      description: t('download.indicator.preparing.subtitle'),
      isLoading: true,
      timeout: 0,
      onClose: () => {
        dismissed = true;
      },
    });
    try {
      await downloadDatasetById(item.id, activeProject!);
      toast.close(toastKey);
      if (!dismissed) {
        toast.success(t('download.indicator.done.title'), {
          description: t('download.indicator.done.subtitle'),
        });
      }
    } catch (_) {
      toast.close(toastKey);
      if (!dismissed) {
        toast.error(t('download.error'));
      }
    }
  };

  const customRenderers: Partial<
    Record<
      DatasetsTableField,
      (item: DatasetResponse) => React.ReactNode | string
    >
  > = {
    [DatasetsTableField.TYPE]: (item) => (
      <ChipDisplay
        type={item[DatasetsTableField.TYPE]}
        variants={getDatasetTypeVariants(t)}
      />
    ),
    [DatasetsTableField.CREATED_AT]: (item) => (
      <DateDisplay date={item[DatasetsTableField.CREATED_AT]} />
    ),
    [DatasetsTableField.SIZE]: (item) =>
      item.sizeBytes == null ? (
        <NoDataDisplay />
      ) : (
        displayHumanReadableBytes(item.sizeBytes)
      ),
  };

  const { mutate: handleDatasetDelete, isPending: isDeletingDatasets } =
    useMutation({
      mutationFn: (ids: string[]) => deleteDatasets(ids, activeProject!),
      onSuccess: (result) => {
        onDeleteConfirmOpenChange();
        queryClient.invalidateQueries({
          queryKey: ['project', activeProject, 'datasets'],
        });
        setSelectedKeys(new Set([]));
        refreshDatasets();
        if (result.failed.length === 0) {
          toast.success(t('actions.delete.success'));
        } else if (result.succeededIds.length === 0) {
          toast.error(t('actions.delete.error'));
        } else {
          toast.error(
            t('actions.delete.partialError', { count: result.failed.length }),
          );
        }
      },
      onError: () => {
        toast.error(t('actions.delete.error'));
      },
    });

  const handleDeleteSelected = useCallback(() => {
    let datasetIds: string[] = [];

    // Server-side pagination: "select all" refers to rows on the current page.
    // Bulk operations therefore target the visible page only — the backend does
    // not expose an "all matching" delete contract.
    if (selectedKeys === 'all') {
      datasetIds = data.map((dataset) => dataset.id.toString());
    } else if (selectedKeys instanceof Set && selectedKeys.size > 0) {
      datasetIds = Array.from(selectedKeys) as string[];
    }
    if (datasetIds.length > 0) {
      handleDatasetDelete(datasetIds);
    }
  }, [handleDatasetDelete, data, selectedKeys]);

  const filterConfig = useMemo(
    () => ({
      type: {
        className: 'sm:w-[calc(100%-3.5rem)]',
        name: 'type',
        label: t('actions.datasetTypeFilter'),
        placeholder: t('actions.datasetTypeFilter'),
        type: FilterComponentType.SELECT,
        // Backend supports a single exact `type` match only.
        // Constrain UI to single-select to keep filter semantics honest.
        allowMultipleSelection: false,
        fields: typeFilterOptions.map((option) => ({
          label: option.name,
          key: option.type,
        })),
      },
    }),
    [t, typeFilterOptions],
  );

  const handleFilterChange = useCallback((filters: FilterValueMap) => {
    const next = filters.type?.[0] as DatasetType | undefined;
    setSelectedTypeFilter(next);
    setSelectedKeys(new Set([]));
    // Reset to page 1 immediately so the next fetch uses the new filter on
    // page 1, not the old page number. ServerSideDataTable also resets via
    // its filters effect, but this avoids the brief window where a stale
    // page request is issued before that effect runs.
    setTableParams((prev) => ({ ...prev, page: 1 }));
  }, []);

  // Surface the type filter to ServerSideDataTable so its built-in
  // reset-to-page-1 effect fires when the user changes filters. Without this,
  // a filter change while on page > 1 would refetch the same page with the
  // new filter — likely empty — while the pagination control still shows the
  // old page.
  const tableFilters = useMemo<FilterParams<DatasetResponse>[]>(
    () =>
      selectedTypeFilter
        ? [{ fields: ['type'], values: [selectedTypeFilter] }]
        : [],
    [selectedTypeFilter],
  );

  const handleTableParamsChange = useDebouncedCallback(
    (params: CollectionRequestParams<DatasetResponse>) => {
      setTableParams(params);
    },
    100,
  );

  return (
    <div className="min-h-full flex flex-col w-full">
      <div className="flex-1 flex flex-col min-h-0">
        <ActionsToolbar
          filterConfig={filterConfig}
          onFilterChange={handleFilterChange}
          onRefresh={refreshDatasets}
          updatedTimestamp={dataUpdatedAt}
          isRefreshing={isLoading || isFetching}
          endContent={
            <div className="flex gap-3 items-center">
              <Dropdown>
                <DropdownTrigger>
                  <Button
                    isDisabled={
                      selectedKeys === 'all'
                        ? false
                        : selectedKeys instanceof Set
                          ? selectedKeys.size === 0
                          : true
                    }
                    endContent={<IconChevronDown className="text-sm" />}
                    variant="flat"
                    radius="md"
                  >
                    {t('actions.actionsDropdown')}
                  </Button>
                </DropdownTrigger>
                <DropdownMenu aria-label={t('actions.actionsDropdown')}>
                  <DropdownItem
                    key="delete"
                    variant="danger"
                    onPress={onDeleteConfirmOpen}
                  >
                    {t('actions.delete.label')}
                  </DropdownItem>
                </DropdownMenu>
              </Dropdown>
              <ActionButton
                primary
                aria-label={t('actions.upload') || ''}
                className="hidden md:flex"
                icon={<IconCloudUpload size={16} stroke={2} />}
                isDisabled={isLoading}
                onPress={() => setDatasetUploadVisible(true)}
              >
                {t('actions.upload')}
              </ActionButton>
              <ActionButton
                primary
                data-testid="upload-dataset-button"
                className="flex md:hidden"
                icon={<IconCloudUpload size={16} stroke={2} />}
                isDisabled={isLoading}
                onPress={() => setDatasetUploadVisible(true)}
              ></ActionButton>

              {datasetUploadVisible && (
                <DatasetUpload
                  isOpen={datasetUploadVisible}
                  refresh={() => refreshDatasets()}
                  onClose={() => setDatasetUploadVisible(false)}
                />
              )}
              <ConfirmationModal
                description={t('actions.delete.confirm.description')}
                title={t('actions.delete.confirm.title')}
                isOpen={isDeleteConfirmOpen}
                loading={isDeletingDatasets}
                onConfirm={handleDeleteSelected}
                onClose={onDeleteConfirmOpenChange}
                confirmationButtonColor="danger"
              />
            </div>
          }
        />

        <ServerSideDataTable
          filters={tableFilters}
          data={data}
          total={total}
          handleDataRequest={handleTableParamsChange}
          isSelectable
          selectedKeys={selectedKeys}
          onSelectionChange={handleSelectionChange}
          className="flex-1 overflow-y-auto"
          columns={columns}
          defaultSortByField={DatasetsTableField.CREATED_AT}
          defaultSortDirection={SortDirection.DESC}
          translation={t}
          customRenderers={customRenderers}
          rowActions={actions}
          isLoading={isLoading}
          isFetching={isFetching}
          idKey={'id'}
        />
      </div>
      <RelevantDocs docs={aiwbDocumentationMapping[AiwbDocsPage.DATASETS]} />
    </div>
  );
};

export async function getServerSideProps(context: GetServerSidePropsContext) {
  const locale = context.locale || 'en';
  const translations = await getPageTranslations(locale, ['datasets']);

  return {
    props: {
      ...translations,
      pageBreadcrumb: buildPageBreadcrumb(
        translations,
        locale,
        'fineTuning',
        'datasets',
      ),
    },
  };
}

export default DatasetsPage;

DatasetsPage.documentationLink = `${DOCS_WORKBENCH_BASE}/training/datasets.html`;
