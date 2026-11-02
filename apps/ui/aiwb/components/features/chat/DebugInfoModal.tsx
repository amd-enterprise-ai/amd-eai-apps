// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Accordion, AccordionItem, Modal } from '@amdenterpriseai/components';
import { IconInfoCircle } from '@tabler/icons-react';
import React from 'react';

import { useTranslation } from 'next-i18next';

import { DebugInfo } from '@/types/chat';
import { Message } from '@/types/chat';

import { MemoizedChatMessage } from './MemoizedChatMessage';

interface DebugInfoModalProps {
  debugInfo: DebugInfo;
  onClose: () => void;
  isOpen: boolean;
}

export const DebugInfoModal: React.FC<DebugInfoModalProps> = ({
  debugInfo,
  onClose,
  isOpen,
}) => {
  const { t } = useTranslation('chat');

  return (
    <>
      {isOpen && (
        <Modal
          onClose={onClose}
          title={t('debugInfoModal.title') || ''}
          subTitle={t('debugInfoModal.subTitle') || ''}
          size="lg"
        >
          <div>
            <Accordion>
              <AccordionItem title={t('debugInfoModal.promptsTitle')}>
                <div className="mb-6 p-6 rounded-md bg-accent-soft text-accent-soft">
                  <IconInfoCircle className="inline mr-1.5 text-accent" />
                  {t('debugInfoModal.promptsDescription')}
                </div>
                <div className="mb-6 p-6 bg-default rounded-md">
                  {debugInfo.messages && debugInfo.messages.length > 0 ? (
                    debugInfo.messages.map(
                      (message: Message, index: number) => (
                        <MemoizedChatMessage
                          key={index}
                          message={message}
                          showCursorOnMessage={false}
                          allowEdit={false}
                          allowCopy={false}
                        />
                      ),
                    )
                  ) : (
                    <div>{t('debugInfoModal.noPromptMessages')}</div>
                  )}
                </div>
              </AccordionItem>
              <AccordionItem title={t('debugInfoModal.tokenUsageTitle')}>
                {debugInfo.usage ? (
                  <div>
                    <div>
                      <span className="font-semibold text-foreground">
                        {t('debugInfoModal.promptTokens')}
                      </span>
                      &nbsp;
                      <span className="rounded px-2 py-1 dark:text-muted text-foreground">
                        {debugInfo.usage.prompt_tokens}
                      </span>
                    </div>
                    <div>
                      <span className="font-semibold text-foreground">
                        {t('debugInfoModal.completionTokens')}
                      </span>
                      &nbsp;
                      <span className=" rounded px-2 py-1 dark:text-muted text-foreground">
                        {debugInfo.usage.completion_tokens}
                      </span>
                    </div>
                    <div>
                      <span className="font-semibold text-foreground">
                        {t('debugInfoModal.totalTokens')}
                      </span>
                      &nbsp;
                      <span className="rounded px-2 py-1 dark:text-muted text-foreground">
                        {debugInfo.usage.total_tokens}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="text-foreground italic">
                    {t('debugInfoModal.noTokenUsage')}
                  </div>
                )}
              </AccordionItem>
            </Accordion>
          </div>
        </Modal>
      )}
    </>
  );
};
