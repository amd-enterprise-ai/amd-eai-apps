// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useState } from 'react';

import { Tab, Tabs } from '../../../src/Tabs';

export default {
  title: 'Components/Tabs',
} satisfies StoryDefault;

export const FlatImports: Story = () => {
  const [selectedKey, setSelectedKey] = useState('overview');

  return (
    <div className="w-full max-w-lg p-4">
      <Tabs selectedKey={selectedKey} onSelectionChange={setSelectedKey}>
        <Tab key="overview" title="Overview">
          <p className="p-4 text-sm">Overview content (flat Tab import).</p>
        </Tab>
        <Tab key="details" title="Details">
          <p className="p-4 text-sm">Details content (flat Tab import).</p>
        </Tab>
      </Tabs>
    </div>
  );
};

export const CompoundSyntax: Story = () => {
  const [selectedKey, setSelectedKey] = useState('metrics');

  return (
    <div className="w-full max-w-lg p-4">
      <Tabs selectedKey={selectedKey} onSelectionChange={setSelectedKey}>
        <Tabs.Tab key="metrics" title="Metrics">
          <p className="p-4 text-sm">Metrics panel (Tabs.Tab compound).</p>
        </Tabs.Tab>
        <Tabs.Tab key="logs" title="Logs">
          <p className="p-4 text-sm">Logs panel (Tabs.Tab compound).</p>
        </Tabs.Tab>
      </Tabs>
    </div>
  );
};

export const FitContent: Story = () => {
  const [selectedKey, setSelectedKey] = useState('curl');

  return (
    <div className="w-full max-w-lg p-4">
      <Tabs
        selectedKey={selectedKey}
        onSelectionChange={setSelectedKey}
        aria-label="Code language"
      >
        <Tab key="curl" title="cURL" />
        <Tab key="python" title="Python" />
        <Tab key="javascript" title="JavaScript" />
      </Tabs>
    </div>
  );
};

export const FullWidth: Story = () => {
  const [selectedKey, setSelectedKey] = useState('overview');

  return (
    <div className="w-full max-w-lg p-4">
      <Tabs
        selectedKey={selectedKey}
        onSelectionChange={setSelectedKey}
        fullWidth
        variant="secondary"
      >
        <Tab key="overview" title="Overview">
          <p className="p-4 text-sm">
            Full-width tab strip with panel content.
          </p>
        </Tab>
        <Tab key="details" title="Details">
          <p className="p-4 text-sm">Equal-width tabs span the container.</p>
        </Tab>
      </Tabs>
    </div>
  );
};

export const SecondaryFitContent: Story = () => {
  const [selectedKey, setSelectedKey] = useState('overview');

  return (
    <div className="w-full max-w-lg p-4">
      <Tabs
        selectedKey={selectedKey}
        onSelectionChange={setSelectedKey}
        variant="secondary"
        aria-label="Secondary fit-content tabs"
      >
        <Tab key="overview" title="Overview">
          <p className="p-4 text-sm">
            Border spans the container; tab labels stay content-sized.
          </p>
        </Tab>
        <Tab key="details" title="Details">
          <p className="p-4 text-sm">
            Panel content below the full-width rule.
          </p>
        </Tab>
      </Tabs>
    </div>
  );
};
