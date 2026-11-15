# Mini Estação Meteorológica

O firmware envia `POST /api/v1/stations/telemetry` com `Content-Type: application/json` e `X-Station-Key`. Configure `AGRION_STATION_KEYS` na VM como JSON, por exemplo `{"agrion-demo-001":"<chave-aleatoria>"}`. A chave não deve ser publicada. Sem configuração válida, o envio recebe `401`.

Corpo: `{"station_id":"agrion-demo-001","measurements":{"rain_detected":true,"temperature_c":26.5,"humidity_pct":72.3,"vento_estimado_m_s":3.2}}`. Campos ausentes são gravados como `null`. `yl38_d0`, `lm393_nivel`, `motor_adc_raw` e `wind_voltage_mv` são ignorados. Sucesso retorna `201` com `received_at` em UTC, atribuído no servidor. Envio a cada cinco segundos pode gerar 17.280 registros por dia por estação.

Consultas públicas: `GET /api/v1/stations/{station_id}/telemetry/latest` retorna `reading: null` sem dados. `GET /api/v1/stations/{station_id}/telemetry?from=<ISO-8601>&to=<ISO-8601>&limit=100` retorna até 500 leituras, da mais recente para a mais antiga. IDs conhecidos permitem consulta sem chave. A interface consulta a última leitura a cada cinco segundos quando visível e guarda apenas o ID escolhido no navegador.

O SQLite fica em `/var/lib/agrion/stations.sqlite3` no volume nomeado `station-data`; mantenha esse volume ao recriar o container e inclua-o nos backups. Não execute `docker compose down -v` se quiser preservar as leituras. Ainda não há retenção automática, paginação por cursor ou vínculo com propriedades. As leituras são dados reais recebidos, mas a velocidade do vento permanece identificada como estimativa do firmware.
