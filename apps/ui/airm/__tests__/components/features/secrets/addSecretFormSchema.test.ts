// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { SecretScope, SecretStatus, SecretType } from '@/types/enums/secrets';
import type { Secret } from '@/types/secrets';
import { SecretUseCase } from '@amdenterpriseai/types';

import { createAddSecretFormSchema } from '@/components/features/secrets/addSecretFormSchema';
import { EXTERNAL_SECRETS_KIND } from '@/components/features/secrets/constants';
import { createManifestYamlValidators } from '@/components/features/secrets/secretManifestYaml';

const t = (key: string, options?: Record<string, unknown>) =>
  options && Object.keys(options).length > 0
    ? `${key}:${JSON.stringify(options)}`
    : key;

const validExternalSecretYaml = `
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: unique-secret-name
spec:
  refreshInterval: 1m
  secretStoreRef:
    kind: ClusterSecretStore
    name: vault
  target:
    name: app-secrets
    creationPolicy: Owner
  data: []
`;

const invalidExternalGroupYaml = validExternalSecretYaml.replace(
  'apiVersion: external-secrets.io/v1beta1',
  'apiVersion: external-secrets.com/v1alpha1',
);

/** apiVersion group must equal external-secrets.io, not merely start with it */
const invalidExternalGroupPrefixYaml = validExternalSecretYaml.replace(
  'apiVersion: external-secrets.io/v1beta1',
  'apiVersion: external-secrets.iofoo/v1beta1',
);

function makeSchema(secrets: Secret[] = []) {
  const { validateExternalSecretYaml, validateKubernetesSecretYaml } =
    createManifestYamlValidators();
  return createAddSecretFormSchema({
    t,
    secrets,
    validateExternalSecretYaml,
    validateKubernetesSecretYaml,
  });
}

const baseValidInput = {
  scope: SecretScope.ORGANIZATION,
  type: SecretType.EXTERNAL_SECRET,
  useCase: SecretUseCase.GENERIC,
  projectIds: [] as string[],
  manifest: validExternalSecretYaml,
};

describe('createAddSecretFormSchema', () => {
  it('reports translated keys when scope, type, or use case is cleared', () => {
    const schema = makeSchema();
    const result = schema.safeParse({
      ...baseValidInput,
      scope: '',
      type: '',
      useCase: '',
      manifest: '',
    });
    expect(result.success).toBe(false);
    const messages = result.error!.issues.map((i) => i.message);
    expect(messages).toContain('form.add.field.scope.error.required');
    expect(messages).toContain('form.add.field.type.error.required');
    expect(messages).toContain('form.add.field.useCase.error.required');
    expect(
      messages.some((m) =>
        m.startsWith('form.add.field.manifest.error.required:'),
      ),
    ).toBe(true);
  });

  it('reports use case required and manifest YAML error together when both fail', () => {
    const schema = makeSchema();
    const result = schema.safeParse({
      ...baseValidInput,
      useCase: '',
      manifest: invalidExternalGroupYaml,
    });
    expect(result.success).toBe(false);
    const paths = result.error!.issues.map((i) => i.path[0]);
    expect(paths).toContain('useCase');
    expect(paths).toContain('manifest');
    const manifestMessages = result
      .error!.issues.filter((i) => i.path[0] === 'manifest')
      .map((i) => i.message);
    expect(
      manifestMessages.some((m) =>
        m.includes('form.add.field.manifest.error.yaml.incorrectGroup'),
      ),
    ).toBe(true);
  });

  it('rejects ExternalSecret YAML when apiVersion group is a false prefix of external-secrets.io', () => {
    const schema = makeSchema();
    const result = schema.safeParse({
      ...baseValidInput,
      manifest: invalidExternalGroupPrefixYaml,
    });
    expect(result.success).toBe(false);
    const manifestMessages = result
      .error!.issues.filter((i) => i.path[0] === 'manifest')
      .map((i) => i.message);
    expect(
      manifestMessages.some((m) =>
        m.includes('form.add.field.manifest.error.yaml.incorrectGroup'),
      ),
    ).toBe(true);
  });

  it('still surfaces manifest YAML errors when type is cleared (invalid type + bad YAML)', () => {
    const schema = makeSchema();
    const result = schema.safeParse({
      ...baseValidInput,
      type: '',
      manifest: invalidExternalGroupYaml,
    });
    expect(result.success).toBe(false);
    const paths = result.error!.issues.map((i) => i.path[0]);
    expect(paths).toContain('type');
    expect(paths).toContain('manifest');
    const manifestMsg = result.error!.issues.find(
      (i) => i.path[0] === 'manifest',
    )?.message;
    expect(manifestMsg).toBeDefined();
    expect(manifestMsg).toContain(EXTERNAL_SECRETS_KIND);
    expect(manifestMsg).toContain(
      'form.add.field.manifest.externalSecret.name',
    );
  });

  it('reports project and manifest errors together when project scope has no project and YAML is invalid', () => {
    const schema = makeSchema();
    const result = schema.safeParse({
      ...baseValidInput,
      scope: SecretScope.PROJECT,
      projectIds: [],
      manifest: invalidExternalGroupYaml,
    });
    expect(result.success).toBe(false);
    const paths = result.error!.issues.map((i) => i.path[0]);
    expect(paths).toContain('projectIds');
    expect(paths).toContain('manifest');
    const messages = result.error!.issues.map((i) => i.message);
    expect(messages).toContain('form.add.field.projectIds.error.required');
    expect(
      messages.some((m) =>
        m.includes('form.add.field.manifest.error.yaml.incorrectGroup'),
      ),
    ).toBe(true);
  });

  it('accepts a valid organization-scoped external secret payload', () => {
    const schema = makeSchema();
    const result = schema.safeParse(baseValidInput);
    expect(result.success).toBe(true);
  });

  it('rejects S3 use case for project scope with translated s3 error', () => {
    const schema = makeSchema();
    const result = schema.safeParse({
      ...baseValidInput,
      scope: SecretScope.PROJECT,
      useCase: SecretUseCase.S3,
      projectIds: ['1'],
    });
    expect(result.success).toBe(false);
    expect(
      result.error!.issues.some(
        (i) =>
          i.message === 'form.add.field.useCase.error.s3NotAllowedForProject',
      ),
    ).toBe(true);
  });

  it('reports duplicate manifest name when secret already exists', () => {
    const existing: Secret = {
      name: 'unique-secret-name',
      displayName: '',
      id: 's1',
      type: SecretType.EXTERNAL_SECRET,
      status: SecretStatus.UNASSIGNED,
      statusReason: null,
      scope: SecretScope.ORGANIZATION,
      projectSecrets: [],
      createdAt: '',
      updatedAt: '',
      createdBy: 'a',
      updatedBy: 'a',
    };
    const schema = makeSchema([existing]);
    const result = schema.safeParse(baseValidInput);
    expect(result.success).toBe(false);
    expect(
      result.error!.issues.some((i) =>
        i.message.includes('form.add.field.manifest.error.yaml.duplicateName'),
      ),
    ).toBe(true);
  });

  it('reports duplicate name when scope is cleared and duplicate is org-scoped', () => {
    const existing: Secret = {
      name: 'unique-secret-name',
      displayName: '',
      id: 's1',
      type: SecretType.EXTERNAL_SECRET,
      status: SecretStatus.UNASSIGNED,
      statusReason: null,
      scope: SecretScope.ORGANIZATION,
      projectSecrets: [],
      createdAt: '',
      updatedAt: '',
      createdBy: 'a',
      updatedBy: 'a',
    };
    const schema = makeSchema([existing]);
    const result = schema.safeParse({
      ...baseValidInput,
      scope: '',
      manifest: validExternalSecretYaml,
    });
    expect(result.success).toBe(false);
    const paths = result.error!.issues.map((i) => i.path[0]);
    expect(paths).toContain('scope');
    expect(paths).toContain('manifest');
    const manifestMessages = result
      .error!.issues.filter((i) => i.path[0] === 'manifest')
      .map((i) => i.message);
    expect(
      manifestMessages.some((m) =>
        m.includes('form.add.field.manifest.error.yaml.duplicateName'),
      ),
    ).toBe(true);
  });

  it('reports duplicate name when scope is cleared and duplicate is project-scoped', () => {
    const existing = {
      name: 'unique-secret-name',
      displayName: '',
      id: 's2',
      type: SecretType.EXTERNAL_SECRET,
      status: SecretStatus.UNASSIGNED,
      statusReason: null,
      scope: SecretScope.PROJECT,
      projectSecrets: [
        { id: 'ps1', project: { id: 'proj-1', name: 'My Project' } },
      ],
      createdAt: '',
      updatedAt: '',
      createdBy: 'a',
      updatedBy: 'a',
    } as Secret;
    const schema = makeSchema([existing]);
    const result = schema.safeParse({
      ...baseValidInput,
      scope: '',
      projectIds: [],
      manifest: validExternalSecretYaml,
    });
    expect(result.success).toBe(false);
    const paths = result.error!.issues.map((i) => i.path[0]);
    expect(paths).toContain('scope');
    expect(paths).toContain('manifest');
    const manifestMessages = result
      .error!.issues.filter((i) => i.path[0] === 'manifest')
      .map((i) => i.message);
    expect(
      manifestMessages.some((m) =>
        m.includes('form.add.field.manifest.error.yaml.duplicateName'),
      ),
    ).toBe(true);
  });
});
