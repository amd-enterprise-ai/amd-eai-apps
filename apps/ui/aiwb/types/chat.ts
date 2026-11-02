// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

export interface TextContent {
  type: 'text';
  text: string;
}

export interface ImageUrlContent {
  type: 'image_url';
  // biome-ignore lint/style/useNamingConvention: OpenAI API snake_case field
  image_url: {
    url: string;
  };
}

export type ContentItem = TextContent | ImageUrlContent;

export interface Message {
  role: 'assistant' | 'user' | 'system' | 'function';
  content: string | ContentItem[];
}

// Type definition for the chat request body
// This type must be compatible with both our API and OpenAI's API
// OpenAI-compatible endpoints follow snake_case convention
export interface ChatBody {
  model?: string;
  messages: Message[];
  stream: boolean;
  // biome-ignore lint/style/useNamingConvention: OpenAI API snake_case field
  stream_options: Record<string, any>;
  temperature: number;
  // biome-ignore lint/style/useNamingConvention: OpenAI API snake_case field
  frequency_penalty?: number;
  // biome-ignore lint/style/useNamingConvention: OpenAI API snake_case field
  presence_penalty?: number;
}

export interface DebugInfo {
  messages: Message[];
  usage?: TokenUsage;
}

export interface ChatContext {
  messages: Message[];
  model: string;
  usage?: TokenUsage;
}

export interface ChatMessageWithDebug extends Message {
  debugInfo?: DebugInfo;
}

export interface ChatConversation {
  messages: ChatMessageWithDebug[];
  streaming: boolean; // Is the conversation still streaming
}

export interface TokenUsage {
  // biome-ignore lint/style/useNamingConvention: OpenAI API snake_case field
  prompt_tokens: number;
  // biome-ignore lint/style/useNamingConvention: OpenAI API snake_case field
  total_tokens: number;
  // biome-ignore lint/style/useNamingConvention: OpenAI API snake_case field
  completion_tokens: number;
}

export interface InferenceChunk {
  context?: { [key: string]: any };
  content?: string;
}

export interface StreamingChatResponse {
  choices?: Array<{
    delta?: {
      content?: string;
    };
  }>;
  context?: any;
  usage?: TokenUsage;
}

export const INFERENCE_CHUNK_DELIMITER = 'data: ';
