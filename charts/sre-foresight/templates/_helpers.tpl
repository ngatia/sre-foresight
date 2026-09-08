{{- define "sre-foresight.fullname" -}}
{{- .Release.Name }}-{{ .Chart.Name -}}
{{- end -}}
