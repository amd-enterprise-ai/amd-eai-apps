// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';

import { useTranslation } from 'next-i18next';

import { useSystemToast } from '@amdenterpriseai/hooks';
import { getPageTranslations } from '@/lib/server/i18n';

import { useProject } from '@/contexts/ProjectContext';

import { ChatView } from '@/components/features/chat/ChatView';
import { RelevantDocs } from '@amdenterpriseai/components';
import { listChattableWorkloads } from '@/lib/app/chat';
import {
  DOCS_WORKBENCH_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';

const ChatPage: React.FC & WithDocumentationLink = () => {
  const { toast } = useSystemToast();
  const { t } = useTranslation('chat');
  const { activeProject } = useProject();

  // Load chattable workloads using optimized endpoint
  const {
    data: chattableData,
    error: workloadsError,
    isPending,
  } = useQuery({
    queryKey: ['workloads', activeProject, 'chattable'],
    queryFn: () => listChattableWorkloads(activeProject!),
    enabled: !!activeProject,
  });

  const workloadDisplayInfo = chattableData?.workloadDisplayInfo ?? {};

  // Handle workloads loading error
  useEffect(() => {
    if (workloadsError) {
      toast.error(t('errors.workloadLoadingFailed'));
    }
  }, [workloadsError, toast, t]);

  return (
    <div className="flex flex-col flex-1 h-full w-full">
      <div className="flex flex-1 h-full w-full">
        {!isPending && (
          <ChatView
            workloads={chattableData?.workloads ?? []}
            workloadDisplayInfo={workloadDisplayInfo}
          />
        )}
      </div>
    </div>
  );
};

export async function getServerSideProps(context: { locale: any }) {
  const { locale } = context;

  return {
    props: {
      ...(await getPageTranslations(locale, ['chat', 'models'])),
    },
  };
}
export default ChatPage;

ChatPage.documentationLink = `${DOCS_WORKBENCH_BASE}/inference/chat.html`;
