// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  IconArrowDown,
  IconPlayerPlay,
  IconPlayerStop,
  IconPaperclip,
} from '@tabler/icons-react';
import { MutableRefObject } from 'react';

import { useTranslation } from 'next-i18next';
import { Button } from '@amdenterpriseai/components';

interface Props {
  content: string;
  enableImageInput: boolean;
  handleChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  setIsTyping: (isTyping: boolean) => void;
  textareaRef: MutableRefObject<HTMLTextAreaElement | null>;
  disabled: boolean;
  sendDisabled: boolean;
  messageIsStreaming: boolean;
  handleSend: () => void;
  handleStopConversation: () => void;
  showScrollDownButton: boolean;
  onScrollDownClick: () => void;
  onAttachImage?: () => void;
  hasAttachedImages?: boolean;
  isDragOver?: boolean;
}

export const ChatTextArea = ({
  content,
  enableImageInput,
  handleChange,
  handleKeyDown,
  setIsTyping,
  textareaRef,
  disabled,
  sendDisabled,
  messageIsStreaming,
  handleSend,
  handleStopConversation,
  showScrollDownButton,
  onScrollDownClick,
  onAttachImage,
  hasAttachedImages,
  isDragOver,
}: Props) => {
  const { t } = useTranslation('chat');

  return (
    <div className="w-full">
      <div className="relative flex flex-row justify-center items-center">
        <textarea
          id="chat-input"
          aria-label={t('chatInput.label')}
          data-testid="chat-input"
          ref={textareaRef}
          disabled={disabled}
          className="py-4 w-full max-h-27.5 md:max-h-50 lg:max-h-100 shadow-lg focus:ring-0 border-0 outline-none bg-default disabled:hover:bg-default-hover/75 rounded-3xl resize-none pl-6 pr-32 text-foreground"
          style={{
            resize: 'none',
            bottom: `${textareaRef?.current?.scrollHeight}px`,
            overflow: `${
              textareaRef.current && textareaRef.current.scrollHeight > 400
                ? 'auto'
                : 'hidden'
            }`,
          }}
          placeholder={
            isDragOver
              ? ''
              : disabled
                ? t('chatInput.placeholderDisabled')
                : t('chatInput.placeholder')
          }
          value={content}
          rows={1}
          onCompositionStart={() => setIsTyping(true)}
          onCompositionEnd={() => setIsTyping(false)}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
        />

        {/* Attach Image Button */}
        {onAttachImage &&
          !messageIsStreaming &&
          !disabled &&
          enableImageInput && (
            <Button
              id="attach-image-button"
              className={`absolute right-16 ${hasAttachedImages ? 'text-success' : ''}`}
              color={hasAttachedImages ? 'success' : 'default'}
              isIconOnly
              radius="full"
              disabled={disabled}
              onPress={onAttachImage}
              data-testid="attach-image-button"
              variant="light"
              title={t('chatInput.attachImage')}
              aria-label={t('chatInput.attachImage')}
            >
              <IconPaperclip size={18} />
            </Button>
          )}

        {!messageIsStreaming && (
          <Button
            id="send-button"
            className="absolute right-1.5"
            color="primary"
            isIconOnly
            radius="full"
            disabled={sendDisabled || disabled}
            onPress={handleSend}
            data-testid="send-button"
          >
            <IconPlayerPlay size={16} />
          </Button>
        )}

        {messageIsStreaming && (
          <Button
            className="absolute right-1.5"
            isIconOnly
            radius="full"
            onPress={handleStopConversation}
          >
            <IconPlayerStop size={16} />
          </Button>
        )}

        {showScrollDownButton && (
          <Button
            className="absolute -top-16 right-1.5 md:top-2 md:-right-16 bg-default-hover/75"
            onPress={onScrollDownClick}
            isIconOnly
            radius="full"
          >
            <IconArrowDown size={16} />
          </Button>
        )}
      </div>
    </div>
  );
};
