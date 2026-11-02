// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconRepeat, IconX, IconPhoto } from '@tabler/icons-react';
import {
  Dispatch,
  DragEvent,
  KeyboardEvent,
  MutableRefObject,
  SetStateAction,
  useEffect,
  useState,
  useRef,
} from 'react';
import Image from 'next/image';

import { useTranslation } from 'next-i18next';
import { useSystemToast } from '@amdenterpriseai/hooks';

import { isMobile } from '@/lib/app/browser';
import {
  fileToBase64DataUrl,
  isSupportedImageFormat,
  isImageFileTooLarge,
  formatFileSize,
  MAX_IMAGE_FILE_SIZE,
  MAX_TOTAL_ATTACHMENT_SIZE,
} from '@/lib/app/image-utils';

import { Message, ContentItem, ImageUrlContent } from '@/types/chat';

import { ChatTextArea } from './ChatTextArea';

interface Props {
  content: string;
  enableImageInput: boolean;
  setContent: Dispatch<SetStateAction<string>>;
  onSend: (message: Message) => void;
  onRegenerate?: () => void;
  onScrollDownClick: () => void;
  stopConversationRef: MutableRefObject<boolean>;
  textareaRef: MutableRefObject<HTMLTextAreaElement | null>;
  showScrollDownButton: boolean;
  allowRegenerate: boolean;
  disabled: boolean;
  messageIsStreaming: boolean;
  /** Tighter layout when nested with the below-`lg` intro column */
  embedded?: boolean;
}

interface AttachedImage {
  id: string;
  dataUrl: string;
  name: string;
  size: number;
}

export const BasicChatInput = ({
  content,
  enableImageInput,
  setContent,
  onSend,
  onRegenerate,
  onScrollDownClick,
  stopConversationRef,
  textareaRef,
  showScrollDownButton,
  allowRegenerate,
  disabled,
  messageIsStreaming,
  embedded = false,
}: Props) => {
  const { t } = useTranslation('chat');
  const { toast } = useSystemToast();

  const [isTyping, setIsTyping] = useState<boolean>(false);
  const [sendDisabled, setSendDisabled] = useState(true);
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setSendDisabled(value.trim().length === 0 && attachedImages.length === 0);

    setContent(value);
  };

  const processImageFiles = async (files: File[]) => {
    // Capture the current total before processing this batch so we can check
    // the cumulative size without waiting for async reads to complete.
    let currentTotalSize = attachedImages.reduce(
      (sum, img) => sum + img.size,
      0,
    );

    for (const file of files) {
      if (!isSupportedImageFormat(file)) {
        toast.error(t('errors.invalidImageFile', { fileName: file.name }));
        continue;
      }

      if (isImageFileTooLarge(file)) {
        toast.error(
          t('errors.imageTooLarge', {
            fileName: file.name,
            maxSize: formatFileSize(MAX_IMAGE_FILE_SIZE),
          }),
        );
        continue;
      }

      if (currentTotalSize + file.size > MAX_TOTAL_ATTACHMENT_SIZE) {
        toast.error(
          t('errors.totalAttachmentTooLarge', {
            maxSize: formatFileSize(MAX_TOTAL_ATTACHMENT_SIZE),
          }),
        );
        continue;
      }

      try {
        const dataUrl = await fileToBase64DataUrl(file);
        const newImage: AttachedImage = {
          id: `${Date.now()}-${Math.random()}`,
          dataUrl,
          name: file.name,
          size: file.size,
        };

        currentTotalSize += file.size;
        setAttachedImages((prev) => [...prev, newImage]);
        setSendDisabled(false);
      } catch (error) {
        toast.error(t('errors.failedToReadImage', { fileName: file.name }));
      }
    }
  };

  const handleImageSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.currentTarget.files;
    if (!files) return;

    await processImageFiles(Array.from(files));

    // Reset the input so the same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (!enableImageInput) return;
    e.preventDefault();
    e.stopPropagation();
    if (!isDragOver) {
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    if (!enableImageInput) return;
    e.preventDefault();
    e.stopPropagation();
    // Only hide overlay when leaving the container, not a child element
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  };

  const handleDrop = async (e: DragEvent<HTMLDivElement>) => {
    if (!enableImageInput) return;
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    await processImageFiles(files);
  };

  const removeImage = (imageId: string) => {
    setAttachedImages((prev) => {
      const updated = prev.filter((img) => img.id !== imageId);
      setSendDisabled(content.trim().length === 0 && updated.length === 0);
      return updated;
    });
  };

  const constructMessage = (): Message => {
    if (attachedImages.length === 0) {
      return { role: 'user', content };
    }

    const contentItems: ContentItem[] = [];

    // Add text content first if there's any text
    if (content.trim().length > 0) {
      contentItems.push({
        type: 'text',
        text: content,
      });
    }

    // Add all attached images
    for (const image of attachedImages) {
      contentItems.push({
        type: 'image_url',
        // biome-ignore lint: OpenAI Vision API uses snake_case
        image_url: {
          url: image.dataUrl,
        },
      } as ImageUrlContent);
    }

    // If only images and no text, add a default text content
    if (
      contentItems.length === attachedImages.length &&
      attachedImages.length > 0
    ) {
      contentItems.unshift({
        type: 'text',
        text: ' ',
      });
    }

    return {
      role: 'user',
      content: contentItems,
    };
  };

  const handleSend = () => {
    if (messageIsStreaming) {
      return;
    }

    if (!content.trim() && attachedImages.length === 0) {
      return;
    }

    try {
      const message = constructMessage();
      onSend(message);
      setContent('');
      setAttachedImages([]);
      setSendDisabled(true);

      if (window.innerWidth < 640 && textareaRef?.current) {
        textareaRef.current.blur();
      }
    } catch (error) {
      toast.error(t('errors.failedToSendMessage'));
    }
  };

  const handleStopConversation = () => {
    stopConversationRef.current = true;
    setTimeout(() => {
      stopConversationRef.current = false;
    }, 1000);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !isTyping && !isMobile() && !e.shiftKey) {
      e.preventDefault();

      if (!sendDisabled) {
        handleSend();
      }
    }
  };

  useEffect(() => {
    if (textareaRef?.current) {
      textareaRef.current.style.height = 'inherit';
      textareaRef.current.style.height = `${textareaRef.current?.scrollHeight}px`;
      textareaRef.current.style.overflow = `${
        textareaRef?.current?.scrollHeight > 400 ? 'auto' : 'hidden'
      }`;
    }

    if (content.length > 0) {
      setSendDisabled(false);
    }
  }, [content, textareaRef]);

  return (
    <div
      className={
        embedded
          ? 'flex w-full justify-start py-0'
          : 'flex justify-center py-6 md:py-12'
      }
    >
      <div
        className={
          embedded
            ? 'relative flex w-full max-w-none'
            : 'flex justify-center mx-2 md:mx-8 w-full md:w-2/3 lg:w-1/2 max-w-125'
        }
      >
        <div
          className="flex flex-col w-full gap-3 relative"
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Drag-and-drop overlay */}
          {isDragOver && (
            <div
              className="absolute inset-0 z-10 flex flex-row items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-accent bg-accent/10 pointer-events-none"
              data-testid="drag-overlay"
            >
              <IconPhoto size={24} className="text-accent" />
              <span className="text-accent font-medium text-sm">
                {t('chatInput.dropImages')}
              </span>
            </div>
          )}
          {/* Attached Images Preview */}
          {attachedImages.length > 0 && (
            <div className="flex flex-wrap gap-2 px-4 pt-3">
              {attachedImages.map((image) => (
                <div key={image.id} className="relative group">
                  <Image
                    src={image.dataUrl}
                    alt={image.name}
                    width={64}
                    height={64}
                    className="h-16 w-16 rounded-lg object-cover border border-gray-200"
                  />
                  <button
                    type="button"
                    onClick={() => removeImage(image.id)}
                    className="absolute -top-2 -right-2 bg-red-500 rounded-full p-1 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100 transition-opacity"
                    title={t('chatInput.removeImage', { fileName: image.name })}
                    aria-label={t('chatInput.removeImage', {
                      fileName: image.name,
                    })}
                  >
                    <IconX size={14} className="text-white" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <ChatTextArea
            content={content}
            enableImageInput={enableImageInput}
            handleChange={handleChange}
            handleKeyDown={handleKeyDown}
            setIsTyping={setIsTyping}
            textareaRef={textareaRef}
            disabled={disabled}
            messageIsStreaming={messageIsStreaming}
            sendDisabled={sendDisabled}
            handleSend={handleSend}
            handleStopConversation={handleStopConversation}
            showScrollDownButton={showScrollDownButton}
            onScrollDownClick={onScrollDownClick}
            onAttachImage={() => fileInputRef.current?.click()}
            hasAttachedImages={attachedImages.length > 0}
            isDragOver={isDragOver}
          />

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*"
            onChange={handleImageSelect}
            className="hidden"
            aria-label={t('chatInput.attachImages')}
          />
        </div>

        {allowRegenerate && !messageIsStreaming && (
          <button
            className="absolute -top-4 shadow-lg left-0 right-0 mx-auto mb-3 flex w-fit items-center gap-3 rounded-lg bg-accent py-2 px-4 text-white md:mb-0 md:mt-2"
            onClick={onRegenerate}
          >
            <IconRepeat size={16} /> {t('chatInput.regenerateResponse')}
          </button>
        )}
      </div>
    </div>
  );
};
