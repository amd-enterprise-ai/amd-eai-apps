// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Accordion, AccordionItem } from '../Accordion/Accordion';
import type { Selection } from '../Select/Select';
import { useTranslation } from 'next-i18next';
import { useLocalStorage } from '@amdenterpriseai/hooks';

import { RelevantDocsCard } from './RelevantDocsCard';

export interface DocEntry {
  title: string;
  description: string;
  url: string;
}

const STORAGE_KEY = 'relevantDocsAccordion';

/**
 * The component uses HeroUI's Accordion component to implement an expand/collapse block.
 * For controlling the state selected keys are used. Empty selection — closed, non-empty selection with AccordionItem in the array — open.
 */
const DEFAULT_VALUE = [STORAGE_KEY];

export interface RelevantDocsProps {
  docs: DocEntry[];
}

export const RelevantDocs = ({ docs }: RelevantDocsProps) => {
  const { t } = useTranslation('sharedComponents', {
    keyPrefix: 'RelevantDocs',
  });
  const [storedKeys, setStoredKeys] = useLocalStorage<string[]>(
    STORAGE_KEY,
    DEFAULT_VALUE,
  );

  if (docs.length === 0) return null;

  const displayEntries = docs.slice(0, 3);
  const selectedKeys = new Set(
    Array.isArray(storedKeys) ? storedKeys : DEFAULT_VALUE,
  );

  const handleToggle = (keys: Selection) =>
    setStoredKeys(
      keys instanceof Set ? Array.from(keys).map(String) : DEFAULT_VALUE,
    );

  return (
    <section className="mt-auto pt-4 pb-4 flex flex-col">
      <Accordion
        selectedKeys={selectedKeys}
        onSelectionChange={handleToggle}
        selectionMode="single"
      >
        <AccordionItem
          key={STORAGE_KEY}
          id={STORAGE_KEY}
          title={t('title')}
          classNames={{ content: 'px-0' }}
        >
          <div className="grid grid-cols-1 min-[1100px]:grid-cols-3 gap-2 w-full">
            {displayEntries.map((entry) => (
              <RelevantDocsCard key={entry.url} {...entry} />
            ))}
          </div>
        </AccordionItem>
      </Accordion>
    </section>
  );
};

RelevantDocs.displayName = 'RelevantDocs';
