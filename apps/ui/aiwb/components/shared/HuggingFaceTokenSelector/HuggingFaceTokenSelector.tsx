// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconPlus } from '@tabler/icons-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
} from 'react';
import { type UseFormReturn } from 'react-hook-form';

import {
  ActionButton,
  FormInput,
  FormPasswordInput,
  ManagedForm,
  Popover,
  Select,
  SelectItem,
  type Selection,
} from '@amdenterpriseai/components';

import {
  createCreateTokenSchema,
  type CreateTokenForm,
  type HuggingFaceTokenValidationLabels,
} from './validation';

export interface HuggingFaceTokenOption {
  /** Kubernetes secret name sent to the API as `hfTokenSecretName`. */
  name: string;
  /** Human-friendly label shown in the dropdown. */
  displayName: string;
}

export interface HuggingFaceTokenSelectorLabels {
  selectLabel: string;
  selectPlaceholder: string;
  addNewItemLabel: string;

  dialogTitle: string;
  dialogNameLabel: string;
  dialogNamePlaceholder: string;
  dialogTokenLabel: string;
  dialogTokenPlaceholder: string;
  dialogCancelLabel: string;
  dialogSubmitLabel: string;

  validation: HuggingFaceTokenValidationLabels;
}

export interface HuggingFaceTokenSelectorProps {
  /** Currently selected token name (controlled). */
  value: string | null | undefined;
  /** Emits the name of the newly selected token. */
  onChange: (name: string) => void;
  /** Existing tokens available to the project/namespace. */
  existingTokens: HuggingFaceTokenOption[];
  /**
   * Creates a new HF token on the backend. Implementations should
   * persist the token secret and return its server-assigned
   * `secretName`; the selector will auto-select that token after
   * creation. `displayName` is the user-entered label, distinct from
   * the returned `secretName` (the Kubernetes secret name used
   * elsewhere as `HuggingFaceTokenOption.name`).
   */
  onCreateToken: (input: {
    displayName: string;
    token: string;
  }) => Promise<{ secretName: string }>;
  /** Display label and placeholders. Required so consumers own their i18n. */
  labels: HuggingFaceTokenSelectorLabels;
  /** Helper text rendered beneath the select when there is no error. */
  description?: ReactNode;

  isRequired?: boolean;
  isDisabled?: boolean;
  isInvalid?: boolean;
  errorMessage?: string;
  className?: string;
  /** Test handle for the root select control. */
  'data-testid'?: string;
}

/** Focus the first field after react-aria's popover/dialog focus containment runs. */
const FocusFirstField = ({
  form,
}: {
  form: UseFormReturn<CreateTokenForm>;
}) => {
  useEffect(() => {
    const id = requestAnimationFrame(() => form.setFocus('name'));
    return () => cancelAnimationFrame(id);
  }, [form]);
  return null;
};

/**
 * Dropdown selector for an existing Hugging Face access token,
 * with a bottom "Add new" affordance that opens a create-token popover.
 *
 * Presentational: data loading and persistence are owned by the consumer
 * via `existingTokens` / `onCreateToken`. The selector keeps no internal
 * state about the selected token — pass `value`/`onChange` to control it.
 */
export const HuggingFaceTokenSelector = ({
  value,
  onChange,
  existingTokens,
  onCreateToken,
  labels,
  description,
  isRequired,
  isDisabled,
  isInvalid,
  errorMessage,
  className,
  'data-testid': dataTestId,
}: HuggingFaceTokenSelectorProps) => {
  const anchorRef = useRef<HTMLDivElement>(null);
  const [isSelectOpen, setIsSelectOpen] = useState(false);
  const [isPopoverOpen, setIsPopoverOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const selectedKeys = useMemo<Set<string>>(
    () => (value ? new Set([value]) : new Set()),
    [value],
  );

  const handleSelectionChange = useCallback(
    (keys: Selection) => {
      if (keys === 'all') return;
      const next = Array.from(keys)[0];
      if (typeof next === 'string') {
        onChange(next);
      }
    },
    [onChange],
  );

  const resetPopover = useCallback(() => {
    setSubmitError(null);
    setIsSubmitting(false);
  }, []);

  const handlePopoverClose = useCallback(() => {
    if (isSubmitting) return;
    setIsPopoverOpen(false);
    resetPopover();
    setIsSelectOpen(true);
  }, [isSubmitting, resetPopover]);

  const handlePopoverOpenChange = useCallback(
    (open: boolean) => {
      if (open) {
        setIsPopoverOpen(true);
        return;
      }
      handlePopoverClose();
    },
    [handlePopoverClose],
  );

  const handleAddNewClick = useCallback(
    (event: MouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
      event.stopPropagation();
      setIsSelectOpen(false);
      setIsPopoverOpen(true);
    },
    [],
  );

  const handleFormSuccess = useCallback(
    async (data: CreateTokenForm) => {
      setIsSubmitting(true);
      setSubmitError(null);
      try {
        const created = await onCreateToken({
          displayName: data.name.trim(),
          token: data.token.trim(),
        });
        onChange(created.secretName);
        setIsPopoverOpen(false);
        resetPopover();
      } catch (err) {
        setSubmitError(err instanceof Error ? err.message : String(err));
        setIsSubmitting(false);
      }
    },
    [onChange, onCreateToken, resetPopover],
  );

  const defaultFormValues = useMemo(() => ({ name: '', token: '' }), []);

  const createTokenSchema = useMemo(
    () => createCreateTokenSchema(labels.validation, existingTokens),
    [labels.validation, existingTokens],
  );

  return (
    <div ref={anchorRef} className={className}>
      <Select
        label={labels.selectLabel}
        placeholder={labels.selectPlaceholder}
        description={description}
        variant="secondary"
        selectedKeys={selectedKeys}
        onSelectionChange={handleSelectionChange}
        isOpen={isSelectOpen}
        onOpenChange={setIsSelectOpen}
        isRequired={isRequired}
        isDisabled={isDisabled}
        isInvalid={isInvalid}
        errorMessage={errorMessage}
        data-testid={dataTestId}
        bottomContent={
          <button
            type="button"
            className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-accent hover:bg-default-100"
            data-testid="hf-token-selector-add-new"
            onClick={handleAddNewClick}
          >
            <IconPlus size={16} aria-hidden />
            {labels.addNewItemLabel}
          </button>
        }
      >
        {existingTokens.map((token) => (
          <SelectItem key={token.name} textValue={token.displayName}>
            {token.displayName}
          </SelectItem>
        ))}
      </Select>

      <Popover isOpen={isPopoverOpen} onOpenChange={handlePopoverOpenChange}>
        <Popover.Content
          triggerRef={anchorRef}
          placement="bottom"
          className="w-80 overflow-visible border border-border"
        >
          <Popover.Arrow />
          <Popover.Dialog>
            <ManagedForm<CreateTokenForm>
              validationSchema={createTokenSchema}
              defaultValues={defaultFormValues}
              isActioning={isSubmitting}
              onFormSuccess={handleFormSuccess}
              renderFields={(form) => (
                <div className="flex flex-col gap-4 p-1">
                  <FocusFirstField form={form} />
                  <Popover.Heading className="text-base font-semibold">
                    {labels.dialogTitle}
                  </Popover.Heading>
                  <FormInput
                    form={form}
                    name="name"
                    label={labels.dialogNameLabel}
                    placeholder={labels.dialogNamePlaceholder}
                    isDisabled={isSubmitting}
                    isRequired
                    autoComplete="off"
                    data-testid="hf-token-selector-dialog-name"
                  />
                  <FormPasswordInput
                    form={form}
                    name="token"
                    label={labels.dialogTokenLabel}
                    placeholder={labels.dialogTokenPlaceholder}
                    isDisabled={isSubmitting}
                    isRequired
                    autoComplete="off"
                    preventPasswordManagerPrompt
                    data-1p-ignore
                    data-lpignore="true"
                    data-bwignore
                    data-testid="hf-token-selector-dialog-token"
                  />
                  {submitError ? (
                    <p className="text-danger text-sm" role="alert">
                      {submitError}
                    </p>
                  ) : null}
                  <div className="flex w-full justify-between pt-1">
                    <ActionButton
                      tertiary
                      aria-label={labels.dialogCancelLabel}
                      onPress={handlePopoverClose}
                      isDisabled={isSubmitting}
                    >
                      {labels.dialogCancelLabel}
                    </ActionButton>
                    <ActionButton
                      primary
                      type="submit"
                      aria-label={labels.dialogSubmitLabel}
                      isLoading={isSubmitting}
                      isDisabled={!form.formState.isValid || isSubmitting}
                      data-testid="hf-token-selector-dialog-submit"
                    >
                      {labels.dialogSubmitLabel}
                    </ActionButton>
                  </div>
                </div>
              )}
            />
          </Popover.Dialog>
        </Popover.Content>
      </Popover>
    </div>
  );
};
