{{/*
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
*/}}

{{/*
Body-authz ceiling in bytes, validated.

Sprig's int64 coerces a non-numeric value to 0 rather than erroring, so "4Mi" — a natural mistake
given the field is discussed in MiB — would render maxRequestBytes: 0 and reject every request on
the header-less path. config.Load() does refuse to start on 0, but the error names the controller,
not the chart, sending the operator to the wrong layer. Fail at template time instead.
*/}}
{{- define "aigw.bodyAuthMaxRequestBytes" -}}
{{- $v := .Values.controller.bodyAuthMaxRequestBytes -}}
{{- $n := $v | int64 -}}
{{- if le $n 0 -}}
{{- fail (printf "controller.bodyAuthMaxRequestBytes must be a plain integer number of bytes, got %v. Quantity suffixes such as 4Mi are not supported here and silently become 0; use 4194304." $v) -}}
{{- end -}}
{{- $n -}}
{{- end -}}
