{{/*
Expand the name of the chart.
*/}}
{{- define "rapids-orchestrator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "rapids-orchestrator.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "rapids-orchestrator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "rapids-orchestrator.labels" -}}
helm.sh/chart: {{ include "rapids-orchestrator.chart" . }}
{{ include "rapids-orchestrator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "rapids-orchestrator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "rapids-orchestrator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend labels
*/}}
{{- define "rapids-orchestrator.backend.labels" -}}
{{ include "rapids-orchestrator.labels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Backend selector labels
*/}}
{{- define "rapids-orchestrator.backend.selectorLabels" -}}
{{ include "rapids-orchestrator.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "rapids-orchestrator.frontend.labels" -}}
{{ include "rapids-orchestrator.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Frontend selector labels
*/}}
{{- define "rapids-orchestrator.frontend.selectorLabels" -}}
{{ include "rapids-orchestrator.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
PostgreSQL labels
*/}}
{{- define "rapids-orchestrator.postgresql.labels" -}}
{{ include "rapids-orchestrator.labels" . }}
app.kubernetes.io/component: database
{{- end }}

{{/*
PostgreSQL selector labels
*/}}
{{- define "rapids-orchestrator.postgresql.selectorLabels" -}}
{{ include "rapids-orchestrator.selectorLabels" . }}
app.kubernetes.io/component: database
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "rapids-orchestrator.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "rapids-orchestrator.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
PostgreSQL connection string
*/}}
{{- define "rapids-orchestrator.postgresql.connectionString" -}}
{{- printf "postgresql://%s:$(POSTGRES_PASSWORD)@%s-postgresql:%d/%s" .Values.postgresql.auth.username (include "rapids-orchestrator.fullname" .) (.Values.postgresql.service.port | int) .Values.postgresql.auth.database }}
{{- end }}
