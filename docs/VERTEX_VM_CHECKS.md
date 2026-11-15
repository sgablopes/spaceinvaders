# Verificação do Vertex AI na VM Agrion

Execute no terminal da VM `instance-20261114-184544` como `sgablopes`. São verificações; não alteram IAM, faturamento nem fazem deploy. **Não publique o token de acesso nem os dados de resposta das chamadas em logs ou mensagens.**

```bash
cd /home/sgablopes/projects/agrion
curl -fsS -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email
curl -fsS -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/scopes
gcloud services list --enabled --project=space-invaders-514718 \
  --filter='name:aiplatform.googleapis.com' --format='value(config.name)'
```

O primeiro comando mostra a service account anexada à VM; o segundo precisa incluir `https://www.googleapis.com/auth/cloud-platform`; o terceiro deve mostrar `aiplatform.googleapis.com`. Se faltar algo, apenas reporte o resultado. Não altere a VM ou o projeto nesta etapa.

Para conferir acesso efetivo aos dois modelos sem alterar configurações, execute uma chamada curta por modelo. **Essas chamadas de inferência podem consumir cota e gerar cobrança no projeto existente.** Os códigos HTTP devem ser 200. `403` indica falta de permissão, API desabilitada ou política; `404` pode indicar modelo/região incorretos.

```bash
TOKEN="$(curl -fsS -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

curl -sS -o /tmp/agrion-extraction-check.json -w 'extracao HTTP %{http_code}\n' \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"contents":[{"role":"user","parts":[{"text":"Responda apenas OK."}]}]}' \
  'https://us-aiplatform.googleapis.com/v1/projects/space-invaders-514718/locations/us/publishers/google/models/gemini-3.5-flash-lite:generateContent'

curl -sS -o /tmp/agrion-live-check.json -w 'live HTTP %{http_code}\n' \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"contents":[{"role":"user","parts":[{"text":"Responda apenas OK."}]}]}' \
  'https://us-central1-aiplatform.googleapis.com/v1/projects/space-invaders-514718/locations/us-central1/publishers/google/models/gemini-3.8-live:generateContent'
unset TOKEN
```

Se o teste do Live por `generateContent` falhar por incompatibilidade de modalidade, isso não comprova indisponibilidade do endpoint WebSocket. Nesse caso, a verificação conclusiva exige uma conexão Live real a partir do container, após a implantação manual autorizada.

Configuração planejada do aplicativo:

```dotenv
GOOGLE_CLOUD_PROJECT=space-invaders-514718
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_CLOUD_EXTRACTION_LOCATION=us
GEMINI_LIVE_MODEL=gemini-3.8-live
GEMINI_EXTRACTION_MODEL=gemini-3.5-flash-lite
```

O Nginx do domínio `agrion.earth` também precisa encaminhar upgrade WebSocket para `/api/interview/live-session`. Verifique a configuração existente antes de alterá-la.
