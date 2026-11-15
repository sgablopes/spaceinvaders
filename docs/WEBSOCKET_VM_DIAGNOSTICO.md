# Diagnóstico do WebSocket no domínio agrion.earth

Na VM, execute estes comandos de leitura. Um upgrade WebSocket correto retorna HTTP `101 Switching Protocols` **tanto** no acesso local quanto no domínio público. O `curl` termina pelo limite de tempo; isso é esperado após o `101`.

```bash
cd /home/sgablopes/projects/agrion
docker compose ps
docker compose logs --tail=80 app
sudo nginx -T 2>&1 | grep -n -E 'server_name agrion.earth|location |proxy_pass|proxy_http_version|proxy_set_header (Host|Upgrade|Connection)|proxy_read_timeout'

curl --http1.1 -i -N --max-time 4 \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  -H 'Origin: https://agrion.earth' \
  http://127.0.0.1:8000/api/interview/live-session

curl --http1.1 -i -N --max-time 4 \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  -H 'Origin: https://agrion.earth' \
  https://agrion.earth/api/interview/live-session
```

- Local `101`, domínio sem `101`: revisar o `server` HTTPS do Nginx.
- Ambos sem `101`: revisar Gunicorn/Flask, imagem atual e logs do container.
- Ambos `101`, mas sessão fecha: revisar `docker compose logs app` por fase `vm_credentials`, `vertex_connect`, `vertex_setup` ou `relay`; conferir também `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` e a service account da VM.

No bloco `server` HTTPS existente de `agrion.earth`, a rota precisa encaminhar os cabeçalhos de upgrade. Esta é a configuração a comparar com o arquivo real; **não substitua o virtual host inteiro**:

```nginx
location = /api/interview/live-session {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 360s;
    proxy_send_timeout 360s;
}
```

Após qualquer edição autorizada do Nginx, validar `sudo nginx -t` antes de `sudo systemctl reload nginx`. Nunca cole tokens de acesso ou transcrições nos relatórios de erro.

O Agrion limita por padrão a 8 tentativas Live por hora por IP e por processo. Tentativas repetidas de diagnóstico podem atingir esse limite. O cabeçalho `X-Forwarded-For` acima permite que o Flask identifique o visitante atrás do Nginx; sem ele, todos podem parecer vir do proxy local. A nova versão do aplicativo mostra `Limite de conexões por hora atingido` quando este for o motivo, em vez de sugerir uma falha genérica de WebSocket.
