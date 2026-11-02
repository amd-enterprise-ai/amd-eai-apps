// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  AiwbDocsPage,
  aiwbDocumentationMapping,
  Button,
  RelevantDocs,
  Tab,
  Tabs,
} from '@amdenterpriseai/components';
import { IconEraser, IconSettings } from '@tabler/icons-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useTranslation } from 'next-i18next';
import { useSearchParams } from 'next/navigation';
import router from 'next/router';

import { useChatWindowScroll, useSystemToast } from '@amdenterpriseai/hooks';

import { getChatSettings, saveChatSettings } from '@/lib/app/chat-settings';

import type {
  ChatBody,
  ChatContext,
  ChatConversation,
  DebugInfo,
  Message,
} from '@/types/chat';
import type { Workload } from '@/types/workloads';
import { DEFAULT_SETTINGS, InferenceSettings } from '@/types/models';

import { BasicChatInput } from '@/components/features/chat/BasicChatInput';
import { Toolbar } from '@amdenterpriseai/layouts';
import { ModelDeploymentSelect } from './ModelDeploymentSelect';

import ChatInfoCard from './ChatInfoCard';
import { ChatMessages } from './ChatMessages';
import SettingsDrawer from './SettingsDrawer';
import { useMediaQuery } from './useMediaQuery';
import { useProject } from '@/contexts/ProjectContext';
import { DELAYED_RESPONSE_THRESHOLD_MS } from './constants';
import { streamChatResponse, type WorkloadDisplayInfo } from '@/lib/app/chat';
import { formatModelDeploymentSubtitle } from '@/lib/app/modelDeploymentDisplay';

interface ChatViewProps {
  workloads: Workload[];
  workloadDisplayInfo?: Record<string, WorkloadDisplayInfo>;
}

const checkSupportForImageInput = (tags?: string[]) =>
  tags?.some((tag: string) =>
    [
      'vision',
      'vision-language',
      'image-to-text',
      'image-text-to-text',
      'multimodal',
    ].includes(tag),
  ) ?? false;

export const ChatView = ({
  workloads,
  workloadDisplayInfo = {},
}: ChatViewProps) => {
  // JS media query is required here — at <lg the DOM structure changes entirely:
  // ChatInfoCard and BasicChatInput are co-located in a single scrollable column
  // so they never clip. At lg+ they're separate (card centred, input fixed at bottom).
  // Pure CSS can't conditionally move BasicChatInput between two parent elements,
  // and rendering it twice would break the shared textareaRef/stopConversationRef.
  const isLgUp = useMediaQuery('(min-width: 1024px)');
  const { toast } = useSystemToast();
  const { t } = useTranslation('chat');
  const { t: tModels } = useTranslation('models');
  const workloadDescriptions = useMemo(() => {
    const map: Record<string, string> = {};
    for (const [id, info] of Object.entries(workloadDisplayInfo)) {
      const line = formatModelDeploymentSubtitle(tModels, info);
      if (line !== '') map[id] = line;
    }
    return map;
  }, [workloadDisplayInfo, tModels]);
  const { activeProject } = useProject();
  const searchParams = useSearchParams();
  const workloadParam = searchParams?.get('workload');

  const [firstLoading, setFirstLoading] = useState<boolean>(false);
  const firstDelayedResponseTimer = useRef<
    string | number | NodeJS.Timeout | undefined
  >(undefined);
  const [
    firstDelayedResponseNotification,
    setFirstDelayedResponseNotification,
  ] = useState<boolean>(false);
  const [firstMessageIsStreaming, setFirstMessageIsStreaming] =
    useState<boolean>(false);

  const [secondLoading, setSecondLoading] = useState<boolean>(false);
  const secondDelayedResponseTimer = useRef<
    string | number | NodeJS.Timeout | undefined
  >(undefined);
  const [
    secondDelayedResponseNotification,
    setSecondDelayedResponseNotification,
  ] = useState<boolean>(false);
  const [secondMessageIsStreaming, setSecondMessageIsStreaming] =
    useState<boolean>(false);

  const [chatMode, setChatMode] = useState<'chat' | 'compare'>('chat');

  const [firstConversation, setFirstConversation] = useState<ChatConversation>({
    messages: [],
    streaming: false,
  });
  const initialSelectedWorkload =
    !workloadParam && workloads.length === 1 ? workloads[0] : undefined;
  const [firstModelWorkload, setFirstModelWorkload] = useState<
    Workload | undefined
  >(initialSelectedWorkload);
  const [firstSettings, setFirstSettings] = useState<InferenceSettings>(
    getChatSettings() || DEFAULT_SETTINGS,
  );

  // Second model configurations
  const [secondConversation, setSecondConversation] =
    useState<ChatConversation>({
      ...firstConversation,
    });
  const [secondModelWorkload, setSecondModelWorkload] = useState<
    Workload | undefined
  >(initialSelectedWorkload);
  const [secondSettings, setSecondSettings] = useState<InferenceSettings>(
    getChatSettings() || DEFAULT_SETTINGS,
  );

  const [syncSettings, setSyncSettings] = useState<boolean>(false);

  const [firstSettingsDrawerOpen, setFirstSettingsDrawerOpen] =
    useState<boolean>(false);
  const [secondSettingsDrawerOpen, setSecondSettingsDrawerOpen] =
    useState<boolean>(false);

  const messagesEndRef1 = useRef<HTMLDivElement>(null);
  const messagesEndRef2 = useRef<HTMLDivElement>(null);
  const chatContainerRef1 = useRef<HTMLDivElement>(null);
  const chatContainerRef2 = useRef<HTMLDivElement>(null);
  const stopConversationRef = useRef<boolean>(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [chatInputContent, setChatInputContent] = useState<string>('');

  const enableImageInput =
    checkSupportForImageInput(
      firstModelWorkload && workloadDisplayInfo[firstModelWorkload.id]?.tags,
    ) &&
    (secondModelWorkload && chatMode === 'compare'
      ? checkSupportForImageInput(
          workloadDisplayInfo[secondModelWorkload.id]?.tags,
        )
      : true);

  function constructMessagesToSendToLLM(
    conversationMessages: Message[],
    systemPrompt: Message | undefined,
  ): Message[] {
    // Add a system prompt if specified, and remove extra fields from past messages
    const messages = [...conversationMessages];
    if (systemPrompt) {
      messages.unshift(systemPrompt);
    }
    return messages.map(
      (message) =>
        ({
          content: message.content,
          role: message.role,
        }) as Message,
    );
  }

  const getChatBody = (
    settings: InferenceSettings,
    messages: Message[],
    workload: Workload,
  ): ChatBody => {
    // Prepare the system prompt message if settings.systemPrompt is not empty
    const systemPromptMessage = settings.systemPrompt
      ? ({ role: 'system', content: settings.systemPrompt } as Message)
      : undefined;

    const chatBody = {
      stream: true,
      stream_options: {
        include_usage: true,
      },
      temperature: settings.temperature,
      frequency_penalty: settings.frequencyPenalty,
      presence_penalty: settings.presencePenalty,
    };

    return {
      ...chatBody,
      messages: constructMessagesToSendToLLM(messages, systemPromptMessage),
    } as ChatBody;
  };

  const populateDebugInformationOnLastMessage = (
    context: ChatContext | undefined,
    conversation: ChatConversation,
    conversationSetter: (conversation: ChatConversation) => void,
    sentMessages: Message[],
  ): ChatConversation => {
    const debugInfo: DebugInfo = {
      messages: sentMessages,
      usage: context?.usage,
    };

    const updatedMessages = conversation.messages;
    const lastElement = updatedMessages.pop();
    updatedMessages.push({
      ...lastElement,
      debugInfo: debugInfo,
    } as Message);
    conversation = {
      ...conversation,
      messages: updatedMessages,
    };
    conversationSetter(conversation);

    return conversation;
  };

  const handleSend = useCallback(
    async (
      conversation: ChatConversation,
      chatBody: ChatBody,
      workloadId: string,
      conversationSetter: (conversation: ChatConversation) => void,
      conversationRef: 'first' | 'second',
    ) => {
      if (conversationRef === 'first') {
        setFirstDelayedResponseNotification(false);
        firstDelayedResponseTimer.current = setTimeout(() => {
          setFirstDelayedResponseNotification(true);
        }, DELAYED_RESPONSE_THRESHOLD_MS);
        setFirstLoading(true);
      } else {
        setSecondDelayedResponseNotification(false);
        secondDelayedResponseTimer.current = setTimeout(() => {
          setSecondDelayedResponseNotification(true);
        }, DELAYED_RESPONSE_THRESHOLD_MS);
        setSecondLoading(true);
      }
      conversation.streaming = true;
      conversationSetter(conversation);
      try {
        const { responseStream, context } = await streamChatResponse(
          workloadId,
          chatBody,
          activeProject || '',
          stopConversationRef,
        );

        if (conversationRef === 'first') {
          clearTimeout(firstDelayedResponseTimer.current);
          setFirstDelayedResponseNotification(false);
          setFirstLoading(false);
        } else {
          clearTimeout(secondDelayedResponseTimer.current);
          setSecondDelayedResponseNotification(false);
          setSecondLoading(false);
        }

        let text = '';
        let updatedMessages: Message[] = [...conversation.messages];
        updatedMessages.push({
          role: 'assistant',
          content: text,
        });

        const responseStreamReader = responseStream.getReader();
        while (true) {
          const { value, done } = await responseStreamReader.read();

          if (done) {
            conversation = {
              ...conversation,
              streaming: false,
            };
            if (conversationRef === 'first') {
              setFirstMessageIsStreaming(false);
            } else {
              setSecondMessageIsStreaming(false);
            }
            conversationSetter(conversation);
            break;
          }
          text += value;
          const lastElement = updatedMessages.pop();
          updatedMessages.push({
            ...lastElement,
            content: text,
          } as Message);

          conversation = {
            ...conversation,
            messages: updatedMessages,
          };
          conversationSetter(conversation);
        }

        conversation = populateDebugInformationOnLastMessage(
          await context,
          conversation,
          conversationSetter,
          chatBody.messages,
        );
      } catch (error) {
        console.error('Error streaming chat response: ', error);
        toast.error(t('errors.chatResponseFailed'));
        if (conversation.messages.at(-1)?.role === 'user') {
          conversation.messages.pop();
        }

        if (conversationRef === 'first') {
          setFirstMessageIsStreaming(false);
          setFirstLoading(false);
          clearTimeout(firstDelayedResponseTimer.current);
          setFirstDelayedResponseNotification(false);
        } else {
          setSecondMessageIsStreaming(false);
          setSecondLoading(false);
          clearTimeout(secondDelayedResponseTimer.current);
          setSecondDelayedResponseNotification(false);
        }
        conversationSetter({
          ...conversation,
          streaming: false,
        });
      }
    },
    [stopConversationRef, toast, t, activeProject],
  );

  const updateSettings = (
    settings: InferenceSettings,
    settingsSetter: (settings: InferenceSettings) => void,
  ) => {
    saveChatSettings(settings);
    if (chatMode === 'compare' && syncSettings) {
      setFirstSettings(settings);
      setSecondSettings(settings);
    } else {
      settingsSetter(settings);
    }
  };

  const onFirstModelWorkloadChange = useCallback(
    (workloadId: string) => {
      const workload = workloads.find((w) => w.id === workloadId);

      if (workload) {
        setFirstModelWorkload(workload);

        const url = new URL(window.location.href);
        url.searchParams.set('workload', workload.id);
        router.push(url.toString(), undefined, { shallow: true });
      }
    },
    [workloads],
  );

  useEffect(() => {
    if (workloadParam) {
      onFirstModelWorkloadChange(workloadParam);
    }
  }, [workloadParam, onFirstModelWorkloadChange, workloads]);

  const onSecondModelWorkloadChange = (workloadId: string) => {
    const workload = workloads.find((w) => w.id === workloadId);

    if (workload) {
      setSecondModelWorkload(workload);
    }
  };

  const onMessage = (message: Message) => {
    setFirstMessageIsStreaming(true);
    setFirstLoading(false);

    if (!firstModelWorkload) {
      return;
    }

    firstConversation.messages = [...firstConversation.messages, message];

    const firstChatBody = getChatBody(
      firstSettings,
      firstConversation.messages,
      firstModelWorkload,
    );

    handleSend(
      firstConversation,
      firstChatBody,
      firstModelWorkload.id,
      setFirstConversation,
      'first',
    );

    if (chatMode === 'compare' && secondModelWorkload) {
      setSecondMessageIsStreaming(true);
      setSecondLoading(false);

      secondConversation.messages = [...secondConversation.messages, message];

      const secondChatBody = getChatBody(
        secondSettings,
        secondConversation.messages,
        secondModelWorkload,
      );
      handleSend(
        secondConversation,
        secondChatBody,
        secondModelWorkload.id,
        setSecondConversation,
        'second',
      );
    }
  };

  const clearAll = () => {
    setFirstConversation({ ...firstConversation, messages: [] });
    setSecondConversation({ ...secondConversation, messages: [] });
  };

  const { showScrollDownButton, handleScroll, handleScrollDown } =
    useChatWindowScroll(
      [messagesEndRef1, messagesEndRef2],
      [chatContainerRef1, chatContainerRef2],
    );

  // Always scroll to bottom when messages change or streaming
  useEffect(() => {
    messagesEndRef1.current?.scrollIntoView({ behavior: 'smooth' });
    if (chatMode === 'compare') {
      messagesEndRef2.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [
    firstConversation.messages,
    secondConversation.messages,
    firstConversation.streaming,
    secondConversation.streaming,
    chatMode,
  ]);

  return (
    <div className="relative flex flex-col w-full h-full">
      <Toolbar>
        <Tabs
          selectedKey={chatMode}
          onSelectionChange={(key) => setChatMode(key as 'chat' | 'compare')}
          aria-label={t('modes.label')}
        >
          <Tab
            key="chat"
            title={t('modes.chat')}
            aria-label={t('modes.chat')}
          />
          <Tab
            key="compare"
            title={t('modes.compare')}
            aria-label={t('modes.compare')}
          />
        </Tabs>
        <div className="max-w-full w-full lg:w-auto mt-[-50px] lg:mt-0 lg:ml-auto flex flex-wrap gap-4 items-center">
          <div className="w-full lg:w-auto text-right">
            <Button
              size="md"
              variant="light"
              className="ml-auto lg:ml-0"
              startContent={<IconEraser size={16} stroke="2" />}
              isDisabled={
                firstMessageIsStreaming ||
                secondMessageIsStreaming ||
                (firstConversation.messages.length === 0 &&
                  secondConversation.messages.length === 0)
              }
              aria-label={t('actions.clearAll')}
              onPress={clearAll}
            >
              {t('actions.clearAll')}
            </Button>
          </div>

          <div className="flex items-center gap-2 w-full md:w-[calc(50%-8px)] lg:w-auto">
            <ModelDeploymentSelect
              workloads={workloads}
              onModelDeploymentChange={onFirstModelWorkloadChange}
              selectedModelId={firstModelWorkload?.id}
              label={t('actions.selectModel') ?? ''}
              workloadDescriptions={workloadDescriptions}
            />
            <Button
              isIconOnly
              variant="light"
              size="md"
              disabled={!firstModelWorkload}
              onPress={() => setFirstSettingsDrawerOpen(true)}
              aria-label={t('modelSettings.showSettings')}
            >
              <IconSettings
                size="16"
                className={!firstModelWorkload ? 'text-muted' : ''}
              />
            </Button>
            <SettingsDrawer
              settings={firstSettings}
              onSettingsChange={(settings) => {
                updateSettings(settings, setFirstSettings);
              }}
              showSyncSettings={chatMode === 'compare'}
              syncSettings={syncSettings}
              onSyncSettingsChange={(sync) => {
                setSyncSettings(sync);
                if (sync) {
                  setSecondSettings({ ...firstSettings });
                }
              }}
              selectedModelWorkload={firstModelWorkload}
              isOpen={firstSettingsDrawerOpen}
              onOpenChange={setFirstSettingsDrawerOpen}
            />
          </div>
          {chatMode === 'compare' && (
            <div className="flex items-center gap-2 w-full md:w-[calc(50%-8px)] lg:w-auto">
              <ModelDeploymentSelect
                workloads={workloads}
                onModelDeploymentChange={onSecondModelWorkloadChange}
                selectedModelId={secondModelWorkload?.id}
                label={t('actions.selectModel') ?? ''}
                workloadDescriptions={workloadDescriptions}
              />
              <Button
                isIconOnly
                variant="light"
                size="md"
                disabled={!secondModelWorkload}
                onPress={() => setSecondSettingsDrawerOpen(true)}
                aria-label={t('modelSettings.showSettings')}
              >
                <IconSettings
                  size="16"
                  className={!secondModelWorkload ? 'opacity-50' : ''}
                />
              </Button>
              <SettingsDrawer
                settings={secondSettings}
                onSettingsChange={(settings) => {
                  updateSettings(settings, setSecondSettings);
                }}
                showSyncSettings={chatMode === 'compare'}
                syncSettings={syncSettings}
                onSyncSettingsChange={(sync) => {
                  setSyncSettings(sync);
                  if (sync) {
                    setFirstSettings({ ...secondSettings });
                  }
                }}
                selectedModelWorkload={secondModelWorkload}
                isOpen={secondSettingsDrawerOpen}
                onOpenChange={setSecondSettingsDrawerOpen}
              />
            </div>
          )}
        </div>
      </Toolbar>
      <div className="flex flex-1 flex-col min-h-0">
        {firstConversation.messages.length === 0 ? (
          !isLgUp ? (
            <div className="flex flex-1 flex-col">
              <div className="mx-auto flex w-full max-w-[480px] flex-col px-4 pt-6 pb-8 sm:px-5">
                <ChatInfoCard mode={chatMode} variant="belowDesktop" />
                <div className="mt-10 w-full sm:mt-12">
                  <BasicChatInput
                    content={chatInputContent}
                    enableImageInput={enableImageInput}
                    setContent={setChatInputContent}
                    stopConversationRef={stopConversationRef}
                    textareaRef={textareaRef}
                    onSend={onMessage}
                    onScrollDownClick={handleScrollDown}
                    showScrollDownButton={showScrollDownButton}
                    messageIsStreaming={
                      firstMessageIsStreaming || secondMessageIsStreaming
                    }
                    disabled={
                      !firstModelWorkload ||
                      (chatMode === 'compare' && !secondModelWorkload)
                    }
                    allowRegenerate={false}
                    embedded
                    aria-label={t('chatInput.label')}
                  />
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 flex-col">
              <div className="my-auto flex justify-center">
                <ChatInfoCard mode={chatMode} />
              </div>
            </div>
          )
        ) : (
          <div className="flex flex-1 min-h-0 w-full overflow-x-scroll overflow-y-hidden justify-center">
            <div
              ref={chatContainerRef1}
              onScroll={handleScroll}
              className={
                'flex pt-6 overflow-y-scroll ' +
                (chatMode !== 'compare' ? 'w-full' : 'w-1/2 max-w-[50%]')
              }
            >
              <ChatMessages
                compareMode={chatMode === 'compare'}
                conversation={firstConversation}
                onConversationUpdated={setFirstConversation}
                messagesEndRef={messagesEndRef1}
                loading={firstLoading}
                delayedResponseNotification={firstDelayedResponseNotification}
                messageIsStreaming={firstMessageIsStreaming}
              />
            </div>
            {chatMode === 'compare' && (
              <div
                ref={chatContainerRef2}
                onScroll={handleScroll}
                className="w-1/2 max-w-[50%] pt-6 overflow-y-scroll "
              >
                <ChatMessages
                  compareMode={chatMode === 'compare'}
                  conversation={secondConversation}
                  onConversationUpdated={setSecondConversation}
                  messagesEndRef={messagesEndRef2}
                  loading={secondLoading}
                  delayedResponseNotification={
                    secondDelayedResponseNotification
                  }
                  messageIsStreaming={secondMessageIsStreaming}
                />
              </div>
            )}
          </div>
        )}
        {(firstConversation.messages.length > 0 || isLgUp) && (
          <BasicChatInput
            content={chatInputContent}
            enableImageInput={enableImageInput}
            setContent={setChatInputContent}
            stopConversationRef={stopConversationRef}
            textareaRef={textareaRef}
            onSend={onMessage}
            onScrollDownClick={handleScrollDown}
            showScrollDownButton={showScrollDownButton}
            messageIsStreaming={
              firstMessageIsStreaming || secondMessageIsStreaming
            }
            disabled={
              !firstModelWorkload ||
              (chatMode === 'compare' && !secondModelWorkload)
            }
            allowRegenerate={false}
            aria-label={t('chatInput.label')}
          />
        )}
        {firstConversation.messages.length === 0 && (
          <RelevantDocs docs={aiwbDocumentationMapping[AiwbDocsPage.CHAT]} />
        )}
      </div>
    </div>
  );
};
