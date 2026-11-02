// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { cn } from '@heroui/react';
import { Input, type InputProps } from '../../Input/InputPrimitive';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FieldValues, Path, UseFormReturn } from 'react-hook-form';

import { useTranslation } from 'next-i18next';

import DragOverlay from './DragOverlay';
import EmptyFileUpload from './EmptyFileUpload';
import FileElement from './FileElement';
import FileUploadFooter from './FileUploadFooter';
import { createFileList, validateFileInput } from './utils';

interface Props<T extends FieldValues>
  extends Omit<InputProps, 'form' | 'name'> {
  form: UseFormReturn<T>;
  name: Path<T>;
  accept?: string;
  multiple?: boolean;
}

/**
 * A file upload component that integrates with React Hook Form.
 * Supports both single and multiple file selection with drag-and-drop functionality.
 *
 * @template T - The form data type extending FieldValues
 *
 * @param props - The component props
 * @param props.form - React Hook Form instance for form state management
 * @param props.name - The field name in the form, used as the key for storing file data
 * @param props.accept - File type restrictions (e.g., ".pdf,.jpg" or "image/*")
 * @param props.multiple - Controls file storage behavior:
 *   - When `false`: Stores a single File object in the form
 *   - When `true`: Stores a FileList object containing multiple files in the form
 *
 * @returns A React element containing the file upload interface
 *
 * @example
 * // Single file upload
 * <FormFileUpload
 *   form={form}
 *   name="avatar"
 *   accept="image/*"
 *   description="Upload your profile picture"
 *   multiple={false}
 * />
 * // Form data will contain: { avatar: File | null }
 *
 * @example
 * // Multiple file upload
 * <FormFileUpload
 *   form={form}
 *   name="documents"
 *   accept=".pdf,.doc,.docx"
 *   description="Upload your documents"
 *   multiple={true}
 * />
 * // Form data will contain: { documents: FileList | null }
 *
 * @remarks
 * - The component automatically validates file types based on both MIME type and file extension
 * - Drag-and-drop is supported with visual feedback for valid/invalid files
 * - Files are stored differently based on the `multiple` prop:
 *   - Single mode: Direct File object or null
 *   - Multiple mode: FileList object or null (even for single files)
 * - The component syncs with React Hook Form's validation system
 * - File input is reset after each selection to allow re-selecting the same files
 */
export const FormFileUpload = <T extends FieldValues>({
  form,
  name,
  className,
  accept,
  placeholder,
  multiple = false,
  ...props
}: Props<T>): React.ReactElement => {
  const { t } = useTranslation('sharedComponents', {
    keyPrefix: 'FormFileUpload',
  });

  const registration = form.register(name);
  const errorMessage = form.formState.errors[name as string]?.message as string;
  const [files, setFiles] = useState<File[]>([]);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const [canDrop, setCanDrop] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Watch the form value to sync with component state
  const formValue = form.watch(name);

  // Sync form value with component state
  useEffect(() => {
    if (formValue) {
      if (multiple) {
        setFiles(formValue ? Array.from(formValue as FileList) : []);
      } else {
        setFiles([formValue as File]);
      }
    } else {
      setFiles([]);
    }
  }, [formValue, multiple]);

  const handleRemoveFile = useCallback(
    (indexToRemove: number) => {
      const updatedFiles = files.filter((_, index) => index !== indexToRemove);
      setFiles(updatedFiles);

      // Update form value
      if (multiple) {
        const formValue =
          updatedFiles.length > 0 ? createFileList(updatedFiles) : null;
        form.setValue(name, formValue as T[Path<T>], {
          shouldValidate: true,
        });
        if (!formValue && fileInputRef.current) fileInputRef.current.value = '';
      } else {
        form.setValue(name, null as T[Path<T>], {
          shouldValidate: true,
        });
        if (fileInputRef.current) fileInputRef.current.value = '';
      }
    },
    [files, multiple, form, name],
  );

  /**
   * Processes new files by adding them to the existing files (if multiple) or replacing them (if single)
   * and updates the form value accordingly
   */
  const processNewFiles = useCallback(
    (newFiles: File[]) => {
      if (multiple) {
        const updatedFiles = [...files, ...newFiles];
        setFiles(updatedFiles);
        form.setValue(name, createFileList(updatedFiles) as T[Path<T>], {
          shouldValidate: true,
        });

        if (fileInputRef.current) {
          try {
            fileInputRef.current.files = createFileList(updatedFiles);
          } catch (error) {
            // Wrapped in try-catch because files property is read-only in some environments (e.g., tests)
            console.warn(error);
          }
        }
      } else {
        const newFile = newFiles[0] || null;
        setFiles(newFile ? [newFile] : []);
        form.setValue(name, newFile as T[Path<T>], {
          shouldValidate: true,
        });

        if (fileInputRef.current) {
          try {
            fileInputRef.current.files = newFile
              ? createFileList([newFile])
              : createFileList([]);
          } catch (error) {
            console.warn(error);
          }
        }
      }
    },
    [files, multiple, form, name],
  );

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFiles = e.target.files ? Array.from(e.target.files) : [];
      processNewFiles(selectedFiles);
    },
    [processNewFiles],
  );

  const openFileUploadDialog = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  // Drag and drop event handlers
  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();

      if (props?.isReadOnly) return;

      if (!isDragOver) {
        setIsDragOver(true);
        const canDropFiles = validateFileInput(
          e.dataTransfer,
          multiple,
          accept,
        );
        setCanDrop(canDropFiles);
      }
    },
    [props?.isReadOnly, isDragOver, multiple, accept],
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    // Only set isDragOver to false if we're leaving the main container
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
      setCanDrop(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();

      setIsDragOver(false);
      setCanDrop(false);

      if (props?.isReadOnly) return;

      const droppedFiles = Array.from(e.dataTransfer.files);

      if (!validateFileInput(droppedFiles, multiple, accept)) return;

      processNewFiles(droppedFiles);
    },
    [props?.isReadOnly, multiple, accept, processNewFiles],
  );

  return (
    <Input
      {...props}
      {...registration}
      onChange={handleFileChange}
      ref={fileInputRef}
      name={name}
      classNames={{
        input: 'sr-only flex-none w-0 min-w-0 p-0 border-0',
        inputWrapper: cn(
          'h-auto p-1 relative w-full',
          '[&_[data-slot=input-group-prefix]]:flex-1',
          '[&_[data-slot=input-group-prefix]]:min-w-0',
          '[&_[data-slot=input-group-prefix]]:w-full',
          '[&_[data-slot=input-group-prefix]]:p-0',
          '[&_[data-slot=input-group-prefix]]:border-0',
          '[&_[data-slot=input-group-prefix]]:rounded-none',
        ),
      }}
      className={cn(className, {
        'text-opacity-disabled': props?.isReadOnly,
        'text-foreground': props?.isReadOnly,
      })}
      type="file"
      accept={accept}
      multiple={multiple}
      isInvalid={!!errorMessage}
      errorMessage={errorMessage}
      startContent={
        <div
          className="flex flex-col w-full min-w-0 gap-1"
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {isDragOver && (
            <DragOverlay multiple={multiple} canDrop={canDrop} t={t} />
          )}
          {files.length > 0 ? (
            <>
              <div className="flex flex-col w-full min-w-0 gap-1">
                {files.map((file, index) => (
                  <FileElement
                    key={index}
                    file={file}
                    onRemove={() => handleRemoveFile(index)}
                    t={t}
                  />
                ))}
              </div>
              {multiple && (
                <FileUploadFooter
                  multiple={multiple}
                  files={files}
                  onAddFiles={openFileUploadDialog}
                  t={t}
                />
              )}
            </>
          ) : (
            <EmptyFileUpload
              placeholder={placeholder}
              multiple={multiple}
              onUpload={openFileUploadDialog}
              t={t}
            />
          )}
        </div>
      }
    />
  );
};

FormFileUpload.displayName = 'FormFileUpload';

export default FormFileUpload;
