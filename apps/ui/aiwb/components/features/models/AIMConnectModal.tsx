// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ActionButton,
  CopySnippet,
  Modal,
  Switch,
  Tab,
  Tabs,
} from '@amdenterpriseai/components';
import { useState } from 'react';

import { useTranslation } from 'next-i18next';

import { useProject } from '@/contexts/ProjectContext';
import { getInferenceApiPath, type InferenceCapability } from '@/lib/app/aims';

interface Props {
  onOpenChange: (isOpen: boolean) => void;
  onChatRequested: (serviceId: string) => void;
  isOpen: boolean;
  serviceId?: string;
  endpoints?: { internal?: string; external?: string };
  modelName?: string;
  /**
   * Capability the deployment exposes; selects the endpoint path and snippet
   * shape. Required so a transcription deployment can never silently fall back
   * to the chat snippet at a caller that forgot to pass it.
   */
  capability: InferenceCapability;
}

// Speech-to-text is a multipart file upload that returns a `text` field, so it
// cannot reuse the JSON chat body/response parsing.
const getTranscriptionExamples = (
  url: string,
  modelName?: string,
): Record<string, string> => {
  const model = modelName ?? '';
  return {
    curl: `curl -X POST "${url}" \\
  -H "Authorization: Bearer UPDATE_YOUR_API_KEY_HERE" \\
  -F "file=@audio.wav" \\
  -F "model=${model}"`,
    python: `import requests

url = "${url}"
headers = {
    "Authorization": "Bearer UPDATE_YOUR_API_KEY_HERE"
}
data = {"model": "${model}"}

# The context manager closes the audio file once the request completes.
with open("audio.wav", "rb") as audio:
    files = {"file": audio}
    response = requests.post(url, headers=headers, files=files, data=data)

result = response.json()
print(result["text"])`,
    javascript: `const url = '${url}';
// Obtain the audio as a File or Blob, e.g. from an <input type="file"> element:
const audioFile = document.querySelector('input[type="file"]').files[0];

const form = new FormData();
form.append('file', audioFile);
form.append('model', '${model}');

fetch(url, {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer UPDATE_YOUR_API_KEY_HERE'
  },
  body: form
})
  .then(response => response.json())
  .then(result => console.log(result.text))
  .catch(error => console.error('Error:', error));`,
  };
};

const getChatExamples = (
  url: string,
  modelName?: string,
  backend?: string,
): Record<string, string> => {
  const model = modelName ?? '';
  // Precise backend routing through the unified gateway: send the deployment UUID
  // and the model name as the x-ai-eg-backend / x-ai-eg-model headers so the
  // gateway's 3-condition route (host + x-ai-eg-backend + x-ai-eg-model) matches
  // at routing time and wins over the model-name fallback — which otherwise routes
  // by model name alone and can hit a different deployment when the same model is
  // deployed in another project. Only emitted when routing through the gateway.
  const curlRoutingHeaders = backend
    ? `  -H "x-ai-eg-backend: ${backend}" \\\n  -H "x-ai-eg-model: ${model}" \\\n`
    : '';
  const pythonRoutingHeaders = backend
    ? `    "x-ai-eg-backend": "${backend}",\n    "x-ai-eg-model": "${model}",\n`
    : '';
  const jsRoutingHeaders = backend
    ? `  'x-ai-eg-backend': '${backend}',\n  'x-ai-eg-model': '${model}',\n`
    : '';
  return {
    curl: `curl -X POST "${url}" \\
  -H "Authorization: Bearer UPDATE_YOUR_API_KEY_HERE" \\
  -H "Content-Type: application/json" \\
${curlRoutingHeaders}  -d '{
    "model": "${model}",
    "messages": [
      {
        "content": "Hello",
        "role": "user"
      }
    ],
    "stream": false
  }'`,
    python: `import requests

url = "${url}"
headers = {
    "Authorization": "Bearer UPDATE_YOUR_API_KEY_HERE",
${pythonRoutingHeaders}    "Content-Type": "application/json"
}
data = {
    "model": "${model}",
    "messages": [
        {"role": "user", "content": "Hello"}
    ],
    "stream": False
}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(result["choices"][0]["message"]["content"])`,
    javascript: `const url = '${url}';
const headers = {
  'Authorization': 'Bearer UPDATE_YOUR_API_KEY_HERE',
${jsRoutingHeaders}  'Content-Type': 'application/json'
};
const data = {
  model: '${model}',
  messages: [
    { role: 'user', content: 'Hello' }
  ],
  stream: false
};

fetch(url, {
  method: 'POST',
  headers: headers,
  body: JSON.stringify(data)
})
  .then(response => response.json())
  .then(result => console.log(result.choices[0].message.content))
  .catch(error => console.error('Error:', error));`,
  };
};

const AIMConnectModal = ({
  onOpenChange,
  onChatRequested,
  isOpen,
  serviceId,
  endpoints,
  modelName,
  capability,
}: Props) => {
  const { t } = useTranslation('models', { keyPrefix: 'aimCatalog' });
  const { t: tc } = useTranslation('common');
  const { aiGatewayEnabled, aiGatewayUrl } = useProject();
  const [selectedLanguage, setSelectedLanguage] = useState<string>('curl');
  const [useInternalUrl, setUseInternalUrl] = useState<boolean>(false);

  const isTranscription = capability === 'transcription';
  const apiPath = getInferenceApiPath(capability);

  // The unified Envoy AI Gateway routes JSON chat completions through a single
  // endpoint (256KB-oriented). Speech-to-text is a large multipart upload, so
  // it targets the per-service workloads URL instead — never the gateway.
  const gatewayUrl =
    !isTranscription && aiGatewayEnabled && aiGatewayUrl
      ? `${aiGatewayUrl.replace(/\/$/, '')}${apiPath}`
      : '';
  const useGateway = !!gatewayUrl;

  const handleClose = () => {
    if (onOpenChange) {
      onOpenChange(false);
    }
  };

  const handleConfirm = () => {
    if (serviceId) {
      onChatRequested(serviceId);
      onOpenChange(false);
    }
  };

  const externalUrl = useGateway
    ? gatewayUrl
    : endpoints?.external
      ? `${endpoints.external}${apiPath}`
      : '';

  // Label the primary URL as the unified inference endpoint when routing
  // through the gateway, otherwise as the per-service external URL.
  const externalUrlLabel = useGateway
    ? t('actions.connect.modal.inferenceUrl')
    : t('actions.connect.modal.externalUrl');

  const internalUrl = endpoints?.internal
    ? `${endpoints.internal}${apiPath}`
    : '';

  // Fall back to the external URL when the internal toggle is on but there is no
  // internal endpoint, so the snippet never points at an empty URL.
  const urlToUse =
    useInternalUrl && internalUrl ? internalUrl : externalUrl || internalUrl;
  // Only the unified gateway routes by the x-ai-eg-backend / x-ai-eg-model
  // headers; the per-service internal URL targets the deployment directly, so
  // emit the routing headers only when the snippet points at the gateway.
  const routeViaGateway = useGateway && !useInternalUrl;
  // Empty model when unresolved — a display-name fallback silently 404s.
  const codeExamples = isTranscription
    ? getTranscriptionExamples(urlToUse, modelName)
    : getChatExamples(
        urlToUse,
        modelName,
        routeViaGateway ? serviceId : undefined,
      );
  const codeBlock = codeExamples[selectedLanguage] || codeExamples.curl;

  return (
    <>
      {isOpen && (
        <Modal
          size="lg"
          title={t('actions.connect.modal.title') as string}
          onClose={handleClose}
          footer={
            <>
              <ActionButton secondary onPress={handleClose}>
                {tc('actions.close.title')}
              </ActionButton>
              {/* The chat playground only applies to chat deployments; hide it
                  for transcription, which has no interactive chat surface. */}
              {!isTranscription && (
                <ActionButton
                  primary
                  onPress={handleConfirm}
                  isDisabled={!serviceId}
                >
                  {t('actions.connect.modal.openChat')}
                </ActionButton>
              )}
            </>
          }
        >
          <div className="space-y-4">
            {externalUrl ? (
              <div>
                <label className="block text-sm text-muted mb-2">
                  {externalUrlLabel}
                </label>
                <CopySnippet className="w-full" aria-label={externalUrlLabel}>
                  {externalUrl}
                </CopySnippet>
              </div>
            ) : null}
            {internalUrl ? (
              <div>
                <label className="block text-sm text-muted mb-2">
                  {t('actions.connect.modal.internalUrl')}
                </label>
                <CopySnippet
                  className="w-full"
                  aria-label={t('actions.connect.modal.internalUrl')}
                >
                  {internalUrl}
                </CopySnippet>
              </div>
            ) : null}

            <div>
              <h4 className="uppercase mb-2 mt-4 font-bold">
                {t('actions.connect.modal.codeTitle')}
              </h4>
              <label className="block text-sm font-medium text-muted mb-3">
                {t('actions.connect.modal.codeExample')}
              </label>
              {externalUrl && internalUrl && (
                <div className="flex items-center justify-between mb-3">
                  <Switch
                    isSelected={useInternalUrl}
                    onValueChange={setUseInternalUrl}
                    size="sm"
                  >
                    {t('actions.connect.modal.useInternalUrl')}
                  </Switch>
                </div>
              )}
              <Tabs
                selectedKey={selectedLanguage}
                onSelectionChange={(key) => setSelectedLanguage(key as string)}
                aria-label={t('actions.connect.modal.codeExample')}
                className="mb-3"
              >
                <Tab
                  key="curl"
                  title={t('actions.connect.modal.languages.curl')}
                />
                <Tab
                  key="python"
                  title={t('actions.connect.modal.languages.python')}
                />
                <Tab
                  key="javascript"
                  title={t('actions.connect.modal.languages.javascript')}
                />
              </Tabs>
              <CopySnippet
                className="w-full"
                data-testid="connect-code-snippet"
                aria-label={t('actions.connect.modal.codeExample')}
              >
                {codeBlock}
              </CopySnippet>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
};

export default AIMConnectModal;
