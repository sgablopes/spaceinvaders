# Integração meteorológica — API 1.4.0

Entrega de 15/11/2026, restrita a `analisys/`, na branch `analisys`. Uma FastAPI, um container, nenhuma dependência nova. NASA POWER e os cálculos anteriores foram preservados. O endpoint Meteomatics existente continua sendo exclusivo desse provedor; o novo endpoint comum e os indicadores compartilham o mesmo seletor de fontes.

## Fontes e validação

| Fonte | Estado verificado | Limitações |
| --- | --- | --- |
| NASA POWER | Histórico preservado; GDD/chuva e novos indicadores novamente verificados com consultas reais | Não fornece forecast; resolução regional e disponibilidade recente da fonte |
| Meteomatics | Autenticação válida; oito parâmetros em consulta horária e extremos/chuva de 24h retornaram dados reais. HTTP no Brasil/EUA validado | Permissões e cota pertencem à conta; teste não garante vigência futura, horizonte completo ou direito de redistribuição |
| Open-Meteo | Horários e dias UTC validados no Brasil/EUA; alternativa real testada com ausência de credenciais induzida somente em objeto local | API pública não comercial, cotas e atribuição; produtos e resolução podem diferir da Meteomatics; não garante continuidade |
| GEOS-FP | OPeNDAP real: metadados e três horários de uma célula consultados | Prova de viabilidade, sem adaptador operacional/endpoints de produção ou participação no fallback |

As credenciais fornecidas foram usadas exclusivamente no ambiente de execução do processo/container local, sem gravação em `.env`, código, imagem, documentação ou relatórios. O corpo do provedor com identificação da conta e os cabeçalhos de autenticação não são expostos. O cliente AGRION não envia credenciais. Ao recriar o container, forneça novamente `METEOMATICS_USERNAME`/`METEOMATICS_PASSWORD` pelo ambiente ou pelo gestor de segredos da implantação; a shell temporária utilizada nesta validação já foi limpa. Não execute `docker compose config` ou comandos de inspeção de ambiente para gerar relatórios, pois podem revelar segredos.

## Consumo recomendado

`POST http://127.0.0.1:8001/v1/data/weather/forecast`, operationId `get_weather_forecast`. OpenAPI em `/docs`; entre containers na rede existente, use `http://agrion-data:8000`.

```json
{
  "location": {"latitude": -16.5, "longitude": -49.3},
  "start_time": "2026-11-17T00:00:00Z",
  "end_time": "2026-11-18T00:00:00Z",
  "step_hours": 24,
  "parameters": ["temperature_min", "temperature_max", "precipitation"],
  "provider": "auto",
  "source": "mix",
  "require_complete": true
}
```

As datas são ilustrativas: atualize-as para intervalos inteiramente futuros, dentro do limite configurado (padrão sete dias). A linha válida em D+1 00:00 representa o intervalo anterior do dia D; o primeiro acumulado também deve começar no futuro. `provider` aceita `auto` (padrão), `meteomatics` e `open_meteo`. A seleção explícita não faz fallback. `source` é preservado do contrato anterior; o adaptador Open-Meteo aceita somente `mix`, mapeado para seleção `best_match`, sem substituir silenciosamente uma fonte/modelo explícito.

Em modo `auto`, primeiro tenta Meteomatics; ausência de credenciais, autenticação/permissão recusadas, cota, falha externa, timeout ou série incompleta permitem tentar Open-Meteo. **A consulta inteira deve ser atendida por uma única fonte com cobertura completa**, inclusive quando `require_complete` foi omitido. Não há combinação de valores entre provedores. Entrada inválida (422) não dispara fallback. Se nenhuma fonte atender, retorna 503 `FORECAST_PROVIDERS_UNAVAILABLE`, com códigos de motivo por provedor, sem inventar valores. Em modo de provedor explícito, `require_complete: false` permite `partial` e null; `true` recusa lacunas.

A resposta adiciona ao contrato meteorológico existente:

- `provider_requested`, `provider_used`, `fallback_used` e `provider_failures[]` (provedor, código e status da falha);
- `result.series[]` com `valid_time`, `interval_start`, campos meteorológicos e `missing_parameters`;
- `result.parameters` com unidade, campo, parâmetro da fonte e semântica temporal;
- `provenance` com URL sem segredos, data de acesso, licença e, para Open-Meteo, coordenadas/elevação da célula retornada;
- hashes, cache, limitações e avisos. `provider_generated_at`/`forecast_reference_time` não são inferidos quando não há emissão/ciclo identificável.

Exemplo Python, com datas futuras calculadas e sem credenciais no cliente:

```python
from datetime import datetime, timedelta, timezone
import httpx

start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
payload = {
    "location": {"latitude": -16.5, "longitude": -49.3},
    "start_time": start.isoformat(), "end_time": (start + timedelta(hours=3)).isoformat(),
    "step_hours": 1, "parameters": ["temperature", "precipitation", "relative_humidity", "wind_speed"],
    "provider": "auto", "require_complete": True,
}
response = httpx.post("http://127.0.0.1:8001/v1/data/weather/forecast", json=payload, timeout=180)
response.raise_for_status()
forecast = response.json()
print(forecast["provider_used"], forecast["fallback_used"])
```

`POST /v1/data/meteomatics/forecast` permanece disponível sem fallback e com o esquema anterior. `/v1/capabilities` descobre os dois contratos. As quatro operações de análise continuam sendo as mesmas; não foi criado outro serviço HTTP.

## Parâmetros e diferenças entre provedores

| Parâmetro comum | Meteomatics existente | Open-Meteo implementado |
| --- | --- | --- |
| temperature | `t_2m:C`, instantâneo | `temperature_2m`, °C, instantâneo horário |
| relative_humidity | `relative_humidity_2m:p`, % | `relative_humidity_2m`, % |
| wind_speed | `wind_speed_10m:ms`, m/s | `wind_speed_10m`, solicitado em m/s |
| solar_radiation | `global_rad:W`, W/m² instantâneo | `shortwave_radiation_instant`, W/m² instantâneo; não usa a média horária como instantâneo |
| precipitation | `precip_{hours}h:mm`, acumulado anterior | Soma completa de `precipitation` das horas anteriores; uma hora ausente invalida o acumulado |
| temperature_mean/min/max | Produtos do intervalo de 1/3/6/24 horas | Produtos diários UTC `temperature_2m_mean/min/max`, somente step=24 e validade à meia-noite |

O mapeamento respeita as [definições oficiais Open-Meteo](https://open-meteo.com/en/docs): precipitação horária refere-se à hora anterior, os produtos diários agregam horas e a coordenada retornada pertence à célula da previsão. Assim, **extremos Open-Meteo não são apresentados como equivalentes a extremos sub-horários ou de outro provedor**. Solicitações térmicas de 1/3/6h sem equivalente são recusadas (`OPEN_METEO_PARAMETER_UNSUPPORTED`). Não se calcula extrema horária própria para preencher esse contrato.

Por solicitação do usuário, as três fontes operacionais **NASA POWER, Meteomatics e Open-Meteo não fazem checagens adicionais de consistência da resposta**. Foram removidos os bloqueios por comparação de coordenadas (incluindo distância da célula), faixas físicas e Tmin maior que Tmax. Também não se rejeitam os dados por formato da versão Meteomatics, datas adicionais, repetições, ordem dos timestamps, tamanho divergente de arrays Open-Meteo, tipo de geometria NASA, comparação estrita de período/base temporal NASA ou unidade esperada NASA/Open-Meteo.

O conector continua lendo somente o intervalo e os parâmetros solicitados. Na Meteomatics, parâmetros não solicitados são ignorados; em repetições do mesmo parâmetro/horário prevalece o último registro recebido, sem média ou correção. Se houver várias coordenadas na mesma entrada Meteomatics, a leitura usa a primeira, sem comparação com o ponto solicitado. Na Open-Meteo, valores sem timestamp não entram na série; timestamps sem valor ficam ausentes. A soma de precipitação continua exigindo todas as horas do intervalo, sem substituir lacunas por zero. Valores fora de faixas usuais são preservados, não truncados ou corrigidos.

Unidades efetivamente informadas pela NASA/Open-Meteo ficam nos metadados (`°C` e `C` são apenas grafias equivalentes); não se converte Kelvin para Celsius nem polegadas para milímetros. A NASA informa a base temporal retornada, sem forçar UTC quando a fonte declara LST. Open-Meteo continua interpretando os epochs retornados como instantes UTC e registra `source_timezone`/`source_utc_offset_seconds` da fonte na procedência; dias/intervalos continuam associados a timestamps exatos, sem reamostragem. Os nomes dos campos legados permanecem por compatibilidade; **consulte sempre a unidade em `result.parameters`**. Campos ausentes ou sem correspondência ficam null; a ausência não é preenchida. Na Meteomatics a unidade faz parte do código de parâmetro: um código diferente não é presumido equivalente ao solicitado.

Permanecem os requisitos mínimos de leitura/serialização JSON (estrutura utilizável, datas interpretáveis, números finitos e distintos de booleanos), erros HTTP/autenticação/cota/timeout, indicação de erro pelo próprio provedor e a opção explícita `require_complete`. As validações de entrada e dos cálculos agronômicos existentes não foram removidas. `status=ok` passa a significar somente cobertura da consulta; não é uma certificação dos valores ou da coerência científica. A política é informada em `quality.warnings`. Usam-se `cell_selection=nearest` e ajuste de altitude padrão do provedor, registrados na procedência. Não se atribui resolução fixa, modelo/ciclo único ou medição de talhão ao conjunto `best_match`.

Verificação desta alteração: **107 testes aprovados** e consultas HTTP reais das três fontes no container local saudável. Para a solicitação de latitude -16.51234567/longitude -49.31234567, a NASA retornou -16.512/-49.312 e a resposta foi aceita, preservando ambos os pontos no contrato. Meteomatics e Open-Meteo retornaram duas previsões horárias completas de temperatura/precipitação. Evidência sanitizada em `.runtime/weather-unchecked-response-check.json`, fora do Git. As fixtures com metadados divergentes, duplicatas e valores fora das faixas são explicitamente sintéticas e verificam somente o comportamento do conector.

Segundo os [termos Open-Meteo](https://open-meteo.com/en/terms), a API pública é para uso não comercial, sob CC BY 4.0, com menos de 10.000 chamadas/dia, 5.000/hora e 600/minuto. O AGRION deve manter atribuição a Open-Meteo e às fontes meteorológicas, inclusive após a integração pelo desenvolvedor principal. Uso comercial exige contratação/configuração apropriada; esta entrega não efetua assinatura nem implementa o endpoint comercial. O cache reduz chamadas, mas não é um limitador de cota distribuído.

Configuração exclusiva do serviço: `OPEN_METEO_TIMEOUT_SECONDS=30`, `OPEN_METEO_CACHE_TTL_SECONDS=300`, `OPEN_METEO_CACHE_ENTRIES=64` e `OPEN_METEO_MAX_FORECAST_DAYS=7` (máximo 16). O Compose repassa os valores do ambiente. Cache limitado por processo, sem credenciais e sem reutilizar entradas vencidas. Horizonte maior depende da disponibilidade real das fontes; configure limites compatíveis para ambas.

## Conexão com indicadores

I03/I05 com `data_kind: "forecast"` e sem série própria usam automaticamente o seletor. I08 também o utiliza quando a precipitação é omitida em todos os dias. Séries manuais e NASA histórica continuam independentes. Nenhum cálculo foi reimplementado.

Em cada indicador, `provenance` preserva o provedor escolhido, `fallback_used`, `fallback_reasons` e `forecast_basis`. Open-Meteo usa `daily_aggregated_hourly_values`; Meteomatics usa `provider_24h_interval_product`. O dia é associado ao início do intervalo diário, preservando a base UTC. A qualidade continua marcada como cenário quando se utiliza previsão.

I05 permanece triagem de exposição, sem previsão de dano por estádio/cultivar. I07/I08 continuam exigindo ETo e Kc explícitos e I08 continua exigindo os demais fluxos. A existência de uma variável ETo no catálogo Open-Meteo não foi usada para alterar o método/escopo desta entrega. I09/I10/I11/I13 continuam dependentes dos métodos/dados documentados na [entrega de indicadores](DELIVERY_INDICATORS.md).

## GEOS-FP: viabilidade comprovada, adaptador ainda pendente

O [catálogo oficial NCCS OPeNDAP](https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/fcast) publica coleções forecast GEOS-FP. A estratégia viável é selecionar variável, ciclo, intervalo temporal e célula remotamente por projeção DAP, sem baixar NetCDF global. GEOS-FP é distinto de GEOS-CF e FP-IT; não foi usada a API de composição como se fosse meteorologia FP.

`tools/probe_geos_fp.py` consulta somente DDS/DAS da coleção `tavg1_2d_slv_Nx.latest` e três tempos de `t2m` numa célula. Índices são derivados dos metadados regulares, com recusa de coleções incompatíveis/sem três horários futuros e limite de leitura de 64 KiB por resposta. Cada leitura é encerrada se exceder o limite. Em 15/11/2026, o teste real recebeu 8.342 bytes de DDS, 7.876 de DAS e **164 bytes de valores pontuais**. Para (-16,5; -49,3), a célula selecionada foi (-16,5; -49,375), com passos de latitude 0,25° e longitude 0,3125°. A série retornou valores reais não ausentes; o script registra valores brutos sem conversão agronômica.

Na consulta, `latest` oferecia 33 horários, de 15/11/2026 03:30 UTC até 16/11/2026 11:30 UTC, não um horizonte de sete dias garantido. Essa é uma evidência do momento, não propriedade fixa do produto. Os tempos médios em meia hora não são instantes horários intercambiáveis com os outros provedores. O [catálogo de produtos GMAO](https://gmao.gsfc.nasa.gov/gmao-products/geos-near-real-time-data-products/) e a [especificação oficial GEOS-FP](https://gmao.gsfc.nasa.gov/media/publications/zbly36ziNFDQeVqPhUoFbmYmvh/GEOS_5_FP_File_Specification_ON4v2_0_fqkxorzhgte_FgpliLt.pdf) são a referência para unidades/coleções, não os nomes abreviados isoladamente.

Antes de promover para produção: fixar ciclos disponíveis (evitar mudança de `latest` entre leituras), verificar coordenadas/tempos retornados contra o ciclo, ler e validar unidades/FillValue/intervalos de cada variável e coleção; selecionar chuva/radiação adequadas; definir cálculo/validação de extremos diários e política de cobertura/frescura. Também falta normalizar o contrato comum e testar falhas/atualizações reais. **GEOS-FP não foi ligado ao fallback nem anunciado como fonte operacional dos indicadores.** O transporte pontual é viável e não demanda biblioteca pesada ou download global; a semântica meteorológica ainda exige esse trabalho específico.

## Testes e reprodução

A partir de `analisys/`:

```sh
python -B -m unittest discover -s tests -q
python -B tools/verify_meteomatics.py
python -B tools/verify_weather.py
python -B tools/verify_automatic_indicators.py
python -B tools/verify_indicators.py
python -B tools/probe_geos_fp.py
```

71 testes determinísticos aprovados: os 58 anteriores e 13 novos cobrindo normalização Open-Meteo, intervalos, lacunas, unidades, cache limitado, falhas, fallback sem mistura, credenciais não refletidas, procedência nos indicadores e seleção/limite de leitura GEOS-FP. Fixtures são sintéticas e não validam acurácia meteorológica.

Os scripts de rede salvam relatórios sem segredos em `.runtime/` (não versionada). `verify_weather.py` concluiu 14 casos: Meteomatics/Open-Meteo/auto horários no Brasil/EUA; produtos diários de ambas; I03/I05 com previsão real; fallback com ausência de credenciais induzida somente no objeto local e Open-Meteo real; I08 com chuva forecast real e **ETo/Kc/fluxos controlados**. Oito parâmetros Meteomatics também passaram em consulta autenticada separada; relatório local `meteomatics-authenticated-check.json`. Saúde do container local confirmada em `127.0.0.1:8001`.

Essas provas confirmam transporte, normalização, autenticação e consumo, não acurácia de previsão ou recomendação agronômica. Não houve mudança no Flask, PR, merge, publicação remota ou contratação de serviços.
