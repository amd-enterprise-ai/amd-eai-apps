// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Select, SelectItem } from '@amdenterpriseai/components';
import { Pagination as HeroUIPagination } from '@heroui/react';
import React from 'react';

import { PageFrameSize } from '@amdenterpriseai/types';

interface Props {
  currentPage: number;
  frameSize: PageFrameSize;
  totalItems: number;
  translation: (key: string, options?: Record<string, unknown>) => string;
  translationKeyPrefix?: string;
  onFrameSizeChange: (frameSize: PageFrameSize) => void;
  onPageChange: (page: number) => void;
}

const buildPageList = (
  page: number,
  total: number,
): (number | 'ellipsis')[] => {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const pages: (number | 'ellipsis')[] = [1];
  if (page > 3) pages.push('ellipsis');
  const start = Math.max(2, page - 1);
  const end = Math.min(total - 1, page + 1);
  for (let i = start; i <= end; i++) pages.push(i);
  if (page < total - 2) pages.push('ellipsis');
  pages.push(total);
  return pages;
};

const ACTIVE_PAGE_LINK_CLASS =
  'data-[active=true]:[--pagination-link-bg:var(--default-hover)] ' +
  'data-[active=true]:[--pagination-link-bg-hover:color-mix(in_oklab,var(--default-hover)_92%,var(--default-foreground)_8%)] ' +
  'data-[active=true]:[--pagination-link-bg-pressed:color-mix(in_oklab,var(--default-hover)_88%,var(--default-foreground)_12%)]';

const ClientSidePagination: React.FC<Props> = ({
  currentPage,
  frameSize,
  totalItems,
  translation,
  translationKeyPrefix,
  onFrameSizeChange,
  onPageChange,
}) => {
  const t = translation;
  const totalPages = Math.ceil(totalItems / frameSize);
  if (totalItems === 0) return null;

  return (
    <div className="w-full flex justify-between items-center">
      <div className="flex items-center gap-4 text-sm w-1/3">
        <span className="text-muted">
          {t(
            `list.${translationKeyPrefix ? `${translationKeyPrefix}.` : ''}pagination.pageSize.label`,
          )}
        </span>
        <Select
          variant="primary"
          defaultSelectedKeys={[
            frameSize ? frameSize.toString() : PageFrameSize.SMALL.toString(),
          ]}
          aria-label={
            t(
              `list.${translationKeyPrefix ? `${translationKeyPrefix}.` : ''}pagination.pageSize.label`,
            ) || ''
          }
          onSelectionChange={(keys) => {
            const value = keys === 'all' ? undefined : Array.from(keys)[0];
            if (value != null) {
              onFrameSizeChange(Number(value) as unknown as PageFrameSize);
            }
          }}
          className="w-24"
        >
          <SelectItem key={PageFrameSize.SMALL.toString()}>
            {PageFrameSize.SMALL.toString()}
          </SelectItem>
          <SelectItem key={PageFrameSize.MEDIUM.toString()}>
            {PageFrameSize.MEDIUM.toString()}
          </SelectItem>
          <SelectItem key={PageFrameSize.LARGE.toString()}>
            {PageFrameSize.LARGE.toString()}
          </SelectItem>
        </Select>
        <span className="text-muted">
          {t(
            `list.${translationKeyPrefix ? `${translationKeyPrefix}.` : ''}pagination.pageSize.entities`,
          )}
        </span>
      </div>
      <span className="text-sm mx-auto w-1/3 text-center text-muted">
        {t(
          `list.${translationKeyPrefix ? `${translationKeyPrefix}.` : ''}pagination.showing`,
          {
            from: Math.min((currentPage - 1) * frameSize + 1, totalItems),
            to: Math.min((currentPage - 1) * frameSize + frameSize, totalItems),
            total: totalItems,
          },
        )}
      </span>
      <div className="w-1/3 flex justify-end">
        <div className="ml-auto">
          <HeroUIPagination size="sm">
            <HeroUIPagination.Content>
              <HeroUIPagination.Item>
                <HeroUIPagination.Previous
                  aria-label="previous page button"
                  isDisabled={currentPage <= 1}
                  onPress={() => onPageChange(currentPage - 1)}
                >
                  <HeroUIPagination.PreviousIcon />
                </HeroUIPagination.Previous>
              </HeroUIPagination.Item>
              {buildPageList(currentPage, totalPages).map((entry, index) =>
                entry === 'ellipsis' ? (
                  <HeroUIPagination.Item key={`ellipsis-${index}`}>
                    <HeroUIPagination.Ellipsis />
                  </HeroUIPagination.Item>
                ) : (
                  <HeroUIPagination.Item key={entry}>
                    <HeroUIPagination.Link
                      aria-label={`pagination item ${entry}${
                        entry === currentPage ? ' active' : ''
                      }`}
                      isActive={entry === currentPage}
                      className={ACTIVE_PAGE_LINK_CLASS}
                      onPress={() => onPageChange(entry)}
                    >
                      {entry}
                    </HeroUIPagination.Link>
                  </HeroUIPagination.Item>
                ),
              )}
              <HeroUIPagination.Item>
                <HeroUIPagination.Next
                  aria-label="next page button"
                  isDisabled={currentPage >= totalPages}
                  onPress={() => onPageChange(currentPage + 1)}
                >
                  <HeroUIPagination.NextIcon />
                </HeroUIPagination.Next>
              </HeroUIPagination.Item>
            </HeroUIPagination.Content>
          </HeroUIPagination>
        </div>
      </div>
    </div>
  );
};

export default ClientSidePagination;
