{{/*
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "aiwb.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "aiwb.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "aiwb.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "aiwb.labels" -}}
helm.sh/chart: {{ include "aiwb.chart" . }}
{{ include "aiwb.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "aiwb.selectorLabels" -}}
app.kubernetes.io/name: {{ include "aiwb.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "aiwb.serviceAccountName" -}}
{{- default (include "aiwb.fullname" .) .Values.rbac.serviceAccountName }}
{{- end }}

{{/*
Construct the keycloak public URL.
Use .Values.keycloak.publicUrl if specified, otherwise construct from appDomain.
*/}}
{{- define "aiwb.keycloakPublicUrl" -}}
{{- if .Values.keycloak.publicUrl -}}
{{ .Values.keycloak.publicUrl }}
{{- else -}}
https://{{ .Values.gateway.keycloak.prefixValue }}.{{ .Values.appDomain }}
{{- end -}}
{{- end -}}

{{/*
The OIDC values. An empty oidc value derives from the keycloak block.
*/}}
{{- define "aiwb.oidcIssuer" -}}
{{- if .Values.oidc.issuer -}}
{{ .Values.oidc.issuer | trimSuffix "/" }}
{{- else -}}
{{ include "aiwb.keycloakPublicUrl" . }}/realms/{{ .Values.keycloak.realm }}
{{- end -}}
{{- end -}}

{{- define "aiwb.oidcInternalUrl" -}}
{{- if .Values.oidc.internalUrl -}}
{{ .Values.oidc.internalUrl | trimSuffix "/" }}
{{- else if .Values.oidc.issuer -}}
{{ .Values.oidc.issuer | trimSuffix "/" }}
{{- else -}}
{{ .Values.keycloak.internalUrl }}/realms/{{ .Values.keycloak.realm }}
{{- end -}}
{{- end -}}

{{- define "aiwb.oidcClientId" -}}
{{ .Values.oidc.clientId | default .Values.keycloak.clientId }}
{{- end -}}

{{- define "aiwb.oidcSecretName" -}}
{{ .Values.oidc.secretName | default .Values.keycloak.secretName }}
{{- end -}}

{{- define "aiwb.oidcJwksUrl" -}}
{{- if .Values.oidc.jwksUrl -}}
{{ .Values.oidc.jwksUrl }}
{{- else if or .Values.oidc.issuer .Values.oidc.internalUrl -}}
{{ required "oidc.jwksUrl is required when oidc.issuer or oidc.internalUrl is set" .Values.oidc.jwksUrl }}
{{- else -}}
{{ include "aiwb.oidcInternalUrl" . }}/protocol/openid-connect/certs
{{- end -}}
{{- end -}}

{{/*
Construct the AIRM UI URL for cross-app navigation.
Use .Values.airmAppUrl if specified, otherwise construct from appDomain.
*/}}
{{- define "aiwb.airmAppUrl" -}}
{{- if .Values.airmAppUrl -}}
{{ .Values.airmAppUrl }}
{{- else -}}
https://{{ .Values.gateway.airm.prefixValue }}.{{ .Values.appDomain }}
{{- end -}}
{{- end -}}
