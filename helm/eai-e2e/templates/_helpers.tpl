# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{/*
Construct the keycloak public URL.
Use .Values.keycloak.publicUrl if specified, otherwise construct from known values.
*/}}
{{- define "eai-e2e.keycloakPublicUrl" -}}
{{- if .Values.keycloak.publicUrl -}}
{{ .Values.keycloak.publicUrl }}
{{- else -}}
https://{{ .Values.kgateway.keycloak.prefixValue }}.{{ .Values.appDomain }}
{{- end -}}
{{- end -}}

{{/*
Identity the e2e runner authenticates to the API server as.
*/}}
{{- define "eai-e2e.username" -}}
{{- .Values.e2eUsername | default (printf "devuser@%s" .Values.appDomain) | trim -}}
{{- end -}}

{{/*
Non-administrator identity the RBAC suites authenticate as.

Produces the account the RBAC suites look for: the local part of the e2e identity
replaced with "teammember", as in the shared E2E credentials library.

The two agree on every well-formed identity. This is deliberately the stricter of the
two on malformed ones: the library takes the segment after the FIRST "@" and accepts
inputs like "a@b@c" or "@example.com", where this refuses to guess. Being stricter is
safe in the one direction that matters — anything this renders, the library resolves
identically — and such an identity is a typo far more often than an intention, so
naming it here beats provisioning an account whose only symptom is the suites skipping.

The identity is trimmed because callers use this via `include ... | quote`; stray
whitespace would survive into the env var and produce an account no one can log in as.
*/}}
{{- define "eai-e2e.teamMemberUsername" -}}
{{- if hasKey .Values.teamMember "username" -}}
{{- fail "teamMember.username is unsupported: the RBAC suites derive the account from e2eUsername" -}}
{{- end -}}
{{/*
Require exactly local@domain rather than picking a segment out of whatever is given.
TeamMemberCredentials._resolve_username takes the segment after the FIRST "@", so on a
multi-"@" identity any other choice here provisions an account the suites never look
up — they would skip while provisioning reported success. Failing the render keeps the
two derivations from disagreeing silently.
*/}}
{{- $identity := include "eai-e2e.username" . | trim -}}
{{- $identityParts := splitList "@" $identity -}}
{{- if or (ne (len $identityParts) 2) (not (first $identityParts)) (not (last $identityParts)) -}}
{{- fail (printf "cannot derive a team member username from %q: it must look like local@domain" $identity) -}}
{{- end -}}
{{- printf "teammember@%s" (last $identityParts) -}}
{{- end -}}

{{/*
Pod template for the team-member provisioning Job.

Kept as its own template so the Job name can be derived from a digest of exactly what
gets applied. A Job's pod template is immutable and this chart is deployed with
`helm template | kubectl apply`, so anything that changes here must change the Job name
too — hashing the rendered result is what keeps those two in step without a hand-listed
set of inputs that can fall behind.
*/}}
{{- define "eai-e2e.teamMemberPodTemplate" -}}
metadata:
  labels:
    {{- include "eai-e2e.labels" . | nindent 4 }}
spec:
  restartPolicy: Never
  {{- with .Values.teamMember.imagePullSecrets }}
  # The image is public, so this only buys registry rate-limit headroom. The secret is
  # created by whoever provisions the namespace, not by this chart, so it is a value:
  # set it empty on a cluster that has no such secret.
  imagePullSecrets:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  containers:
    - name: provision
      image: {{ printf "%s:%s" .Values.teamMember.image.repository .Values.teamMember.image.tag | quote }}
      imagePullPolicy: {{ .Values.teamMember.image.pullPolicy }}
      command: ["python3", "/scripts/provision-team-member.py"]
      env:
        - name: KEYCLOAK_URL
          value: {{ .Values.keycloak.internalUrl | quote }}
        - name: KEYCLOAK_REALM
          value: {{ .Values.keycloak.realm | quote }}
        - name: KEYCLOAK_ADMIN_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: {{ .Values.teamMember.adminClientSecret.name }}
              key: {{ .Values.teamMember.adminClientSecret.clientIdKey }}
        - name: KEYCLOAK_ADMIN_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: {{ .Values.teamMember.adminClientSecret.name }}
              key: {{ .Values.teamMember.adminClientSecret.clientSecretKey }}
        - name: TEAM_MEMBER_USERNAME
          value: {{ include "eai-e2e.teamMemberUsername" . | quote }}
        # The suites derive the team member's password from the e2e identity's when no
        # override is set, so both accounts must share this secret.
        - name: TEAM_MEMBER_PASSWORD
          valueFrom:
            secretKeyRef:
              name: {{ .Values.teamMember.userCredentialsSecret.name }}
              key: {{ .Values.teamMember.userCredentialsSecret.passwordKey }}
        - name: TEAM_MEMBER_FIRST_NAME
          value: {{ .Values.teamMember.firstName | quote }}
        - name: TEAM_MEMBER_LAST_NAME
          value: {{ .Values.teamMember.lastName | quote }}
      volumeMounts:
        - name: provisioner
          mountPath: /scripts
          readOnly: true
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        allowPrivilegeEscalation: false
        seccompProfile:
          type: RuntimeDefault
        capabilities:
          drop:
            - ALL
  volumes:
    - name: provisioner
      configMap:
        name: e2e-team-member-provisioner
{{- end -}}

{{/*
Standard labels.
*/}}
{{- define "eai-e2e.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
