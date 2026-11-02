// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  CodeBlock,
  MarkdownCodeBlock,
  MemoizedReactMarkdown,
  Skeleton,
} from '@amdenterpriseai/components';
import {
  IconBug,
  IconCircleCheck,
  IconCopy,
  IconEdit,
  IconRobot,
  IconTerminal2,
  IconTrash,
  IconUserBolt,
} from '@tabler/icons-react';
import { FC, memo, useEffect, useRef, useState } from 'react';
import Image from 'next/image';

import { useTranslation } from 'next-i18next';

import { ContentItem, DebugInfo, Message } from '@/types/chat';
import { extractTextContent } from '@/lib/app/image-utils';

import { DebugInfoModal } from './DebugInfoModal';

import rehypeMathjax from 'rehype-mathjax/svg';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';

export interface Props {
  message: Message;
  showCursorOnMessage: Boolean;
  allowEdit: Boolean;
  allowCopy: Boolean;
  debugInfo?: DebugInfo;
  onEdit?: (editedMessage: Message) => void;
  onDelete?: () => void;
  messageIsStreaming?: boolean;
  isLoading?: boolean;
}

export const ChatMessage: FC<Props> = memo(
  ({
    message,
    onEdit,
    onDelete,
    allowEdit,
    allowCopy,
    debugInfo,
    showCursorOnMessage,
    messageIsStreaming,
    isLoading = false,
  }) => {
    const { t } = useTranslation('chat');

    const [isEditing, setIsEditing] = useState<boolean>(false);
    const [isTyping, setIsTyping] = useState<boolean>(false);
    const [messageContent, setMessageContent] = useState<string>(
      extractTextContent(message.content),
    );
    const [messagedCopied, setMessageCopied] = useState(false);
    const [showDebug, setShowDebug] = useState(false);

    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const toggleEditing = () => {
      setIsEditing(!isEditing);
    };

    const toggleDebugPanel = () => {
      setShowDebug(!showDebug);
    };

    const handleInputChange = (
      event: React.ChangeEvent<HTMLTextAreaElement>,
    ) => {
      setMessageContent(event.target.value);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'inherit';
        textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
      }
    };

    const handleEditMessage = () => {
      if (extractTextContent(message.content) === messageContent) {
        setIsEditing(false);
        return;
      }

      let newContent: string | ContentItem[];
      if (typeof message.content === 'string') {
        newContent = messageContent;
      } else {
        // Replace text items with the edited text, preserve all image_url items.
        // If no text item existed originally, prepend one.
        const nonTextItems = message.content.filter(
          (item) => item.type !== 'text',
        );
        const textItem: ContentItem = { type: 'text', text: messageContent };
        newContent = [textItem, ...nonTextItems];
      }

      onEdit?.({ ...message, content: newContent });
      setIsEditing(false);
    };

    const handleDeleteMessage = () => {
      onDelete?.();
    };

    const handlePressEnter = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !isTyping && !e.shiftKey) {
        e.preventDefault();
        handleEditMessage();
      }
    };

    const copyOnClick = () => {
      if (!navigator.clipboard) return;

      const textToCopy = extractTextContent(message.content);
      navigator.clipboard.writeText(textToCopy).then(() => {
        setMessageCopied(true);
        setTimeout(() => {
          setMessageCopied(false);
        }, 2000);
      });
    };

    useEffect(() => {
      setMessageContent(extractTextContent(message.content));
    }, [message.content]);

    useEffect(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'inherit';
        textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
      }
    }, [isEditing]);

    return (
      <div className="group mb-4" style={{ overflowWrap: 'anywhere' }}>
        <div className="relative flex flex-col text-base">
          <div className="my-4 font-bold">
            <div className="flex flex-row items-center rounded-full">
              {message.role === 'assistant' && (
                <div className="flex w-full">
                  <div className="flex min-w-full w-full flex-row items-center">
                    <div className="bg-accent text-white rounded-full p-1 mr-2">
                      <IconRobot size={16} stroke="1.5" />
                    </div>
                    <div className="text-foreground">
                      {t('roles.assistant')}
                    </div>
                  </div>
                  <div className="h-6 pt-0.5 ml-4 inline-flex items-baseline space-x-2">
                    {allowCopy && (
                      <div className="flex">
                        {messagedCopied ? (
                          <IconCircleCheck
                            size={16}
                            stroke={2}
                            className="text-white bg-accent p-1 rounded-full"
                          />
                        ) : (
                          <button
                            className="invisible group-hover:visible focus:visible text-accent hover:text-accent-soft-hover"
                            onClick={copyOnClick}
                          >
                            <IconCopy stroke={2} size={16} />
                          </button>
                        )}
                      </div>
                    )}
                    {debugInfo && (
                      <div>
                        <DebugInfoModal
                          isOpen={showDebug}
                          onClose={toggleDebugPanel}
                          debugInfo={debugInfo}
                        />

                        <button
                          onClick={toggleDebugPanel}
                          className="invisible group-hover:visible focus:visible text-accent hover:text-accent-soft-hover"
                          aria-label="debug-info"
                        >
                          <IconBug size={16} stroke="1.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
              {message.role === 'user' && (
                <div className="flex justify-start w-full">
                  <div className="flex items-center">
                    <div className="bg-accent text-white rounded-full p-1 mr-2">
                      <IconUserBolt size={16} stroke="1.5" />
                    </div>
                    <div className="text-foreground">{t('roles.user')}</div>
                  </div>
                  {allowEdit && !isEditing && (
                    <div className="h-6 pt-0.5 ml-4">
                      <button
                        className="invisible group-hover:visible focus:visible text-accent hover:text-accent-soft-hover "
                        onClick={toggleEditing}
                      >
                        <IconEdit size={16} stroke="1.5" />
                      </button>
                      <button
                        className="ml-2 invisible group-hover:visible focus:visible text-accent hover:text-accent-soft-hover "
                        onClick={handleDeleteMessage}
                      >
                        <IconTrash size={16} stroke="1.5" />
                      </button>
                    </div>
                  )}
                </div>
              )}
              {message.role === 'system' && (
                <div className="flex justify-start w-full">
                  <div className="flex items-center">
                    <div className="bg-accent rounded-full p-1 mr-2">
                      <IconTerminal2 size={16} stroke="1.5" />
                    </div>
                    <div className="text-foreground">{t('roles.system')}</div>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="leading-relaxed w-full">
            {message.role === 'user' ? (
              <div className="flex w-full">
                {isEditing ? (
                  <div className="flex w-full flex-col ">
                    <textarea
                      ref={textareaRef}
                      className="w-full focus:ring-0 focus:border-accent shadow-lg focus:outline-2 outline-none border-2 border-default/75 dark:bg-zinc-600 light:bg-zinc-200 text-foreground dark:focus:border-accent rounded-md resize-none"
                      value={messageContent}
                      onChange={handleInputChange}
                      onKeyDown={handlePressEnter}
                      onCompositionStart={() => setIsTyping(true)}
                      onCompositionEnd={() => setIsTyping(false)}
                      style={{
                        fontFamily: 'inherit',
                        fontSize: 'inherit',
                        lineHeight: 'inherit',
                        padding: '0',
                        margin: '0',
                        overflow: 'hidden',
                      }}
                    />

                    <div className="my-4 flex justify-start space-x-4">
                      <button
                        className="h-10 rounded-md bg-accent px-4 py-1 text-sm font-medium text-white enabled:hover:bg-accent-soft-hover disabled:opacity-50"
                        onClick={handleEditMessage}
                        disabled={messageContent.trim().length <= 0}
                      >
                        {t('edit.saveAndSubmit')}
                      </button>
                      <button
                        className="h-10 rounded-md border border-default px-4 py-1 text-sm font-medium text-foreground hover:bg-default dark:border-muted dark:hover:bg-default-hover"
                        onClick={() => {
                          setMessageContent(
                            extractTextContent(message.content),
                          );
                          setIsEditing(false);
                        }}
                      >
                        {t('edit.cancel')}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex-1">
                    {/* Display text content */}
                    {typeof message.content === 'string' ? (
                      <div className="whitespace-pre-wrap user-message text-foreground">
                        {message.content}
                      </div>
                    ) : (
                      <>
                        {/* Display text from content items */}
                        {message.content.map((item, index) => {
                          if (item.type === 'text') {
                            return (
                              <div
                                key={index}
                                className="whitespace-pre-wrap user-message text-foreground mb-4"
                              >
                                {item.text}
                              </div>
                            );
                          }
                          return null;
                        })}
                        {/* Display images from content items */}
                        {message.content.some(
                          (item) => item.type === 'image_url',
                        ) && (
                          <div className="flex flex-wrap gap-2 mt-2">
                            {message.content
                              .filter((item) => item.type === 'image_url')
                              .map((item, index) => {
                                if (item.type === 'image_url') {
                                  return (
                                    <div
                                      key={index}
                                      className="relative rounded-lg overflow-hidden border border-default"
                                    >
                                      <Image
                                        src={item.image_url.url}
                                        alt={t('chatInput.attachedImageAlt', {
                                          index: index + 1,
                                        })}
                                        width={200}
                                        height={200}
                                        className="max-h-50 w-auto"
                                      />
                                    </div>
                                  );
                                }
                                return null;
                              })}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-row">
                <div className="flex-1 overflow-x-auto">
                  {isLoading ? (
                    <>
                      <Skeleton className="mb-2 rounded-lg w-3/4 h-4"></Skeleton>
                      <Skeleton className="mb-2 rounded-lg w-5/6 h-4"></Skeleton>
                      <Skeleton className="rounded-lg w-1/2 h-4"></Skeleton>
                    </>
                  ) : (
                    <MemoizedReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[rehypeMathjax]}
                      components={{
                        code({ className, children, ...props }) {
                          if (
                            children &&
                            typeof children === 'string' &&
                            children.length
                          ) {
                            if (children[0] == '▍') {
                              return (
                                <span className="animate-pulse cursor-slate mt-1">
                                  ▍
                                </span>
                              );
                            }
                            if (children && typeof children === 'string') {
                              children = children.replace('▍', '`▍`');
                            }
                          }

                          const match = /language-(\w+)/.exec(className || '');

                          return className ? (
                            <MarkdownCodeBlock
                              key={Math.random()}
                              language={match?.[1] || ''}
                              value={String(children).replace(/\n$/, '')}
                              {...props}
                            />
                          ) : (
                            <span {...props}>
                              <CodeBlock size="sm" className="px-1 py-0.5">
                                {children}
                              </CodeBlock>
                            </span>
                          );
                        },
                        table({ children }) {
                          return (
                            <table className="border-collapse border border-black px-3 py-1 dark:border-white ">
                              {children}
                            </table>
                          );
                        },
                        a({ children, href }) {
                          return (
                            <a
                              href={href}
                              className="text-accent dark:text-accent font-semibold"
                            >
                              {children}
                            </a>
                          );
                        },
                        th({ children }) {
                          return (
                            <th className="wrap-break-word border border-black bg-gray-500 px-3 py-1 text-white dark:border-white">
                              {children}
                            </th>
                          );
                        },
                        td({ children }) {
                          return (
                            <td className="wrap-break-word border border-black px-3 py-1 dark:border-white ">
                              {children}
                            </td>
                          );
                        },
                        p({ children }) {
                          return (
                            <div className="text-foreground mb-4 leading-8">
                              {children}
                            </div>
                          );
                        },
                        li({ children }) {
                          return (
                            <li className="text-foreground mb-4 leading-8">
                              {children}
                            </li>
                          );
                        },
                      }}
                    >
                      {`${extractTextContent(message.content)}${
                        messageIsStreaming && showCursorOnMessage ? '▍' : ''
                      }`}
                    </MemoizedReactMarkdown>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  },
);
ChatMessage.displayName = 'ChatMessage';
