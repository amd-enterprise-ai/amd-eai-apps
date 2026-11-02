// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Button, Spinner } from '@amdenterpriseai/components';

type Props = {
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string;
  showNoValidCombinationsWarning?: boolean;
  noValidCombinationsMessage?: string;
  showBaseImageOptionsWarning?: boolean;
  baseImageOptionsWarningMessage?: string;
  showEmptyAcceleratorsWarning: boolean;
  emptyAcceleratorsMessage: string;
  loadingMessage: string;
  loadErrorMessage: string;
  retryLabel: string;
  onRetry: () => void;
};

export function RuntimeProfileCatalogStatus({
  isLoading,
  isError,
  errorMessage,
  showNoValidCombinationsWarning = false,
  noValidCombinationsMessage,
  showBaseImageOptionsWarning = false,
  baseImageOptionsWarningMessage,
  showEmptyAcceleratorsWarning,
  emptyAcceleratorsMessage,
  loadingMessage,
  loadErrorMessage,
  retryLabel,
  onRetry,
}: Props) {
  if (showNoValidCombinationsWarning && noValidCombinationsMessage) {
    return (
      <p
        className="text-sm text-warning"
        data-testid="runtime-profile-no-valid-combinations"
      >
        {noValidCombinationsMessage}
      </p>
    );
  }
  if (isError) {
    return (
      <div
        className="flex flex-col gap-2 rounded-md border border-danger/40 bg-danger-soft p-3 text-sm"
        data-testid="runtime-profile-catalog-error"
      >
        <p className="text-danger">{errorMessage ?? loadErrorMessage}</p>
        <Button size="sm" variant="flat" onPress={onRetry}>
          {retryLabel}
        </Button>
      </div>
    );
  }
  if (isLoading) {
    return (
      <div
        className="flex items-center gap-2 text-sm text-muted"
        data-testid="runtime-profile-catalog-loading"
      >
        <Spinner size="sm" />
        <span>{loadingMessage}</span>
      </div>
    );
  }
  if (showBaseImageOptionsWarning && baseImageOptionsWarningMessage) {
    return (
      <p
        className="text-sm text-warning"
        data-testid="runtime-profile-base-image-options-warning"
      >
        {baseImageOptionsWarningMessage}
      </p>
    );
  }
  if (showEmptyAcceleratorsWarning) {
    return (
      <p
        className="text-sm text-warning"
        data-testid="runtime-profile-empty-accelerators"
      >
        {emptyAcceleratorsMessage}
      </p>
    );
  }
  return null;
}
