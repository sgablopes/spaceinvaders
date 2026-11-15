# AquaCrop — execução de safra pela API 1.5.0

Entrega restrita a `analisys/`, branch `analisys`. O motor executa no mesmo serviço FastAPI, em processo isolado por requisição. As planilhas, ZIPs, fórmulas anteriores e a aplicação principal foram preservados.

## O que funciona

`POST /v1/simulations/aquacrop`, operationId `simulate_aquacrop`, executa **AquaCrop-OSPy 3.0.12** e retorna produtividade simulada seca/fresca, desenvolvimento e balanço hídrico diário/acumulado. A consulta é síncrona; a resposta é o resultado completo e pode ser armazenada pelo consumidor. Não é uma estimativa de produtividade criada por uma fórmula substituta.

Dois modos climáticos:

- `nasa_power`: histórico diário UTC completo por coordenada, usando o cliente/cache existentes; ETo calculada a partir das entradas meteorológicas NASA pelo método documentado abaixo.
- `caller_supplied`: série diária completa com Tmin/Tmax, precipitação e ETo, com referência obrigatória. Não há consulta meteorológica nesse modo.

Escopo validado: **Maize de biblioteca, uma safra de sequeiro, plantio no primeiro dia da simulação**, solo genérico `SandyLoam` ou `Loam` selecionado explicitamente, água inicial e CO₂ declarados. O dicionário e as tabelas de entrada continuam consultáveis em `/api/v1/aquacrop/...`; as cinco abas originais permanecem vazias. A simulação recebe entradas pelo JSON, sem preenchê-las na planilha.

### Motor escolhido e pendência da versão oficial 7.3

O planejamento menciona AquaCrop 7.3. Foi auditado o [código Python oficial FAO 7.3](https://github.com/un-fao/fao-AquaCrop/releases/tag/v7.3), indicado no [portal FAO](https://www.fao.org/aquacrop/). A execução local com os arquivos oficiais `Maize.CRO`, `SandyLoam.SOL` e clima Davis encontrou dois erros internos:

1. `AttributeError: rep_sum ... CRSalt` na saída agregada;
2. desativando somente essa saída, `TypeError: RequiredTimeNew() missing ... VirtualTimeCC` durante o cálculo.

Nenhuma rotina científica foi corrigida/reescrita para contornar esses erros. O ZIP auditado tem SHA-256 `1eebc1b29f639cfba4528f515f38556482852009342937d64606332867e37cfc`; os arquivos oficiais ficaram somente na área local ignorada `.runtime/`, fora do Git e da imagem Docker. O arquivo climático citado no IDE, `AGRION_CONTRATO_CLIMA_DIARIO_PARA_DADOS.md`, não foi encontrado neste checkout; não foi presumido como disponível.

Para entregar uma execução viável foi integrado o [AquaCrop-OSPy](https://github.com/aquacropos/aquacrop), pacote **3.0.12**, com suas próprias rotinas/parâmetros e licença Apache-2.0. **É uma implementação científica de AquaCrop; não é a distribuição oficial FAO 7.3 e não se afirma equivalência aos resultados 7.3.** Essa diferença é explícita no OpenAPI, catálogo e em `engine.official_fao_7_3=false` em toda resposta. A versão oficial 7.3 continua pendente de correção/validação upstream ou escolha posterior de outro motor oficial validado.

Dependências científicas fixadas: `aquacrop==3.0.12`, `pandas==2.2.3`, `numpy==2.2.6`. Pandas 3 apresentou arrays somente de leitura incompatíveis com a rotina de chuva do motor; a compatibilidade foi resolvida por versão de dependência, sem alterar o algoritmo. O subprocesso usa o modo `DEVELOPMENT=True` suportado pelo pacote, com as rotinas Python/NumPy; não depende de módulos compilados específicos de outra plataforma. Os parâmetros e o código instalado são identificados por hashes no resultado.

## Consumo

Iniciar/reconstruir na raiz, usando o arquivo local ignorado:

```sh
docker compose --env-file analisys/.env -f analisys/compose.yaml up -d --build
```

Swagger: `http://127.0.0.1:8001/docs`. Entre containers na rede existente: `http://agrion-data:8000`. Somente o serviço de análises é atualizado.

Exemplo **de cenário** que foi executado com clima NASA real, sem alegar solo/manejo medidos:

```json
{
  "scenario_id": "maize_nasa_2024",
  "start_date": "2024-10-01",
  "end_date": "2025-05-28",
  "crop": "Maize",
  "location": {"latitude": -16.5, "longitude": -49.3},
  "weather": {
    "source": "nasa_power",
    "reference": "NASA POWER UTC; ETo FAO-56 PM com limites de nebulosidade ASCE declarados"
  },
  "soil": {
    "preset": "SandyLoam", "depth_m": 2.4,
    "reference": "Perfil genérico do motor; hipótese, não solo medido/geolocalizado",
    "kind": "assumed_engine_preset"
  },
  "initial_water": {
    "method": "FC", "reference": "Capacidade de campo inicial assumida, não medida", "kind": "assumed"
  },
  "co2": {
    "concentration_ppm": 369.41,
    "reference": "Concentração de referência do motor; cenário de base, NÃO concentração atmosférica observada em 2024"
  },
  "management": {"irrigation": "rainfed", "reference": "Cenário declarado de sequeiro"},
  "assumptions_reference": "Milho e solo genéricos sem calibração local; resultado não representa produtividade observada do talhão"
}
```

Envie esse objeto por POST a `/v1/simulations/aquacrop`. Exemplo Python usando o payload salvo pelo consumidor:

```python
import json
from pathlib import Path
import httpx

payload = json.loads(Path("cenario.json").read_text(encoding="utf-8"))
response = httpx.post("http://127.0.0.1:8001/v1/simulations/aquacrop", json=payload, timeout=240)
response.raise_for_status()
simulation = response.json()
yield_t_ha = simulation["result"]["dry_yield_t_ha"]
water = simulation["result"]["water_balance"]
daily = simulation["result"]["daily"]
```

Para usar clima próprio, substitua `weather` por `{"source":"caller_supplied","reference":"origem e método da série","daily":[...]}`. Cada dia deve conter `date` (YYYY-MM-DD), `tmin_c`, `tmax_c` (°C), `precipitation_mm` (lâmina diária mm) e `eto_mm_day` (mm/dia). A resposta NASA/FAO usada na primeira execução pode ser repetida desse modo para reproduzir o resultado. Declare se a série é cenário/sintética na referência; o serviço não a certifica como observada.

## Entradas, parâmetros e hipóteses

| Entrada | Contrato / origem |
| --- | --- |
| Período | 1–300 dias inclusivos, uma safra, plantio em `start_date`; uma janela curta é recusada como safra incompleta. Plantio em 29/02 não é suportado pelo calendário de referência do motor |
| Cultura | Somente `Maize` de biblioteca 3.0.12. Calendário de 132 dias antes dos efeitos/ajustes do motor; densidade, fenologia, colheita e resposta hídrica permanecem as do pacote |
| Solo | `SandyLoam` ou `Loam`, perfil genérico explicitamente assumido; profundidade declarada **2,4–3 m**, 12 compartimentos iguais. Limite evita extensão silenciosa de um perfil raso pelo motor para acomodar a raiz do Maize padrão |
| Água inicial | `FC` capacidade de campo, `WP` ponto de murcha ou `SAT` saturação da biblioteca; todos exigem referência e declaração de hipótese |
| CO₂ | Concentração constante explícita em ppm e referência. Não se usa silenciosamente a projeção A1B do arquivo CO₂ padrão do pacote |
| Manejo | Somente `rainfed`, sem irrigação. Sem lençol freático no adaptador, sem efeitos de rotação, fertilidade, salinidade ou daninhas |
| Elevação | Para ETo NASA: `elevation_m` opcional; se ausente usa a terceira coordenada válida da geometria NASA. Sem ambas, erro explícito |
| Clima | Todos os dias UTC, sem duplicatas, datas externas ou lacunas; Tmin≤Tmax; valores finitos, chuva não negativa; nenhuma série futura NASA |

Não há perfil HWSD validado neste checkout: raster e banco MDB estão ausentes. Não foram criadas pedotransferências nem valores de FC/WP/SAT/Ksat a partir de textura sem validação. Perfis medidos/customizados continuam pendentes; um preset é uma hipótese científica de cenário, não uma consulta de solo da propriedade.

Os parâmetros hidráulicos completos, curva de escoamento, água prontamente evaporável e parâmetros da cultura selecionada acompanham `inputs.parameters`, com hash. Exemplos do preset SandyLoam: FC=0,22, WP=0,10, SAT=0,41 m³/m³ e Ksat=1.200 mm/dia; são valores **do motor**, não medições locais. O campo `depth_m=2.4` é escolha explícita do cenário; não foi inferido da coordenada.

As tabelas FAO-56 existentes continuam disponíveis. Seus Kc de ETc padrão não foram usados para sobrescrever o coeficiente de transpiração e demais parâmetros internos de AquaCrop: são contratos/modelos diferentes. I01/I02/I03/I05/I07/I08/I14 continuam preservados. I07/I08 ainda recebem ETo explícita; o consumidor pode aproveitar `weather[].eto_mm_day` desta simulação. A fachada antiga I13 e calibração produtiva regional continuam pendentes; o novo SIM entrega diretamente o cenário mecanístico.

## NASA → ETo

O endpoint NASA mantém os seis parâmetros e comportamentos padrão anteriores. Foram adicionadas seleções opcionais `WS2M` (vento a 2 m em m/s), `T2MDEW` (ponto de orvalho em °C) e `PS` (pressão em kPa). Unidades e disponibilidade foram conferidas na fonte real. A simulação consulta esses três, `T2M_MIN`, `T2M_MAX`, `PRECTOTCORR` e `ALLSKY_SFC_SW_DWN` (MJ/m²/dia), com `require_complete=true`, pelo mesmo cliente/cache. [Documentação NASA POWER](https://power.larc.nasa.gov/docs/services/api/temporal/daily/)

ETo diária: [FAO-56, capítulos 2–4](https://www.fao.org/4/X0490E/x0490e08.htm), equação 6 de Penman-Monteith; pressão psicrométrica da PS, vapor real do ponto de orvalho, saturação a partir de Tmin/Tmax, radiação extraterrestre pela latitude/dia, céu claro pela elevação, albedo de referência 0,23 e fluxo de calor diário G=0. O termo de nebulosidade usa `Rs/Rso` limitado a **0,3–1**, explicitamente conforme [ASCE-EWRI 2005](https://content-hub.uidaho.edu/api/public/content/9d9ea3f325e945158730b61661e8add8?v=cc545c86), sem apresentá-lo como coeficiente agronômico calibrado. Cada dia identifica se houve esse limite em `inputs.eto_diagnostics`.

O domínio do adaptador é latitude ±60°, elevação −400 a 5.000 m. Umidade inconsistente, ETo negativa/não finita e valores incompatíveis são recusados. ETo para o motor deve estar entre 0,1 e 50 mm/dia; não se aplica silenciosamente o truncamento mínimo usado por alguns leitores do pacote. O exemplo publicado FAO-56 nº 18 foi reproduzido: **3,87969 mm/dia**, frente a 3,88 do manual. A implementação de ETo é reutilizável e separada do motor; não foi criada uma segunda API.

## Resultados e interpretação

- `engine`: identificação, versão, distinção de FAO 7.3, versões NumPy/pandas, hash do código e dos parâmetros;
- `result.dry_yield_t_ha` / `fresh_yield_t_ha`: produtividade simulada em t/ha; fresca segue a fração de matéria seca do parâmetro da cultura;
- `result.crop_mature` / `crop_dead`: término por maturidade ou morte simulada; morte não é disfarçada como maturidade. Safra não concluída não retorna produtividade parcial como colheita;
- `result.daily`: apenas os dias efetivamente simulados, com armazenamento do perfil em mm, fluxos, evaporação, transpiração, escoamento, drenagem, crescimento de raízes e cobertura;
- `result.water_balance`: totais somente da safra executada e armazenamento inicial/final. Fechamento verificado por dia e no total, tolerância numérica de **0,0001 mm**, sem significado de precisão agronômica;
- `weather`: série completa solicitada, incluindo eventual trecho posterior à maturidade não utilizado. `simulated_days` e `last_simulated_date` delimitam o trecho consumido;
- `harvest_timestamp_engine`: horário de fim do último passo do motor, borda exclusiva seguinte ao dia civil; não confundir com uma data observada de colheita;
- `provenance`, `inputs`, `method`, `quality`, `traceability`: fontes, diagnósticos ETo, hipóteses e hashes para reprodução. `quality.kind=scenario`, `field_validated=false`.

O balanço é conferido independentemente a partir dos fluxos do motor: estoque inicial + precipitação + irrigação + ascensão capilar + entrada subterrânea − estoque final no solo − água superficial final − evaporação − transpiração − escoamento − percolação profunda. A água do perfil é `Σ(theta × espessura × 1000)`, convertendo m³/m³ e m para mm; não é a soma da água somente na zona radicular variável.

### Execução NASA real de referência

Cenário JSON acima, em 15/11/2026, com histórico NASA de 01/10/2024 a 28/05/2025:

| Resultado do cenário | Valor |
| --- | --- |
| Motor / cultura | AquaCrop-OSPy 3.0.12 / Maize genérico |
| Dias efetivamente simulados | 132, último dia civil 09/02/2025 |
| Produtividade seca **simulada** | 14,37098 t/ha |
| Precipitação consumida na safra | 874,17 mm |
| Estoque inicial / final no perfil | 528,00 / 517,63041 mm |
| Evaporação / transpiração | 127,96271 / 370,66763 mm |
| Escoamento / percolação profunda | 50,37033 / 335,53891 mm |
| Irrigação, ascensão e entrada subterrânea | 0 mm no cenário de sequeiro sem lençol |
| Resíduo total de conservação | ordem de 10⁻¹² mm; ≈−1,71×10⁻¹² mm no container Linux |

Esse número de produtividade depende de milho genérico, perfil profundo assumido, água inicial FC, CO₂ de referência e ausência das limitações não simuladas. **Não constitui previsão validada para a propriedade nem observação de produção.** Fechar o balanço e reproduzir a execução valida a integração numérica, não calibra o modelo para a região/cultivar.

## Operação, falhas e testes

Uma execução concorrente por processo do serviço; manter um worker como no Dockerfile atual. Cada trabalho roda em subprocesso sem credenciais de meteorologia, sem rede necessária ao cálculo e sem parâmetros de caminho/código fornecidos pelo cliente. Limite de 300 dias e `AQUACROP_TIMEOUT_SECONDS=90` (configurável entre 5 e 180). Timeout encerra o subprocesso; arquivos temporários ficam no volume `.runtime/` e são removidos ao terminar. Não há fila, persistência de trabalhos ou armazenamento automático de resultados na API.

Erros: 422 entrada inválida, ETo incompatível ou `SEASON_INCOMPLETE`; 404 lacunas NASA; 429 `SIMULATION_BUSY`; 502 falha/saída inválida/fechamento hídrico inválido; 503 dependência/versão/elevação ausente; 504 timeout. Nenhuma falha devolve produtividade inventada ou troca silenciosa de motor. Falhas de aquisição NASA preservam seus códigos de origem. Não há simulação de safra futura a partir de somente sete dias de forecast nem preenchimento de meses ausentes.

A partir de `analisys/`:

```sh
python -B -m unittest discover -s tests -q
python -B tools/verify_aquacrop.py
```

O primeiro inclui **82 testes**, com 11 novos para ETo publicada, equações/unidades, simulação real do motor com clima de teste identificado como sintético, replay determinístico, sensibilidade à hipótese de solo, integração NASA simulada, lacunas, safra curta, limites, timeout, ocupação, proteção de credenciais e OpenAPI. Preserva verificações dos arquivos originais e das demais integrações.

O script HTTP exige container iniciado e rede real: executa o cenário com NASA, repete com a mesma série explícita e compara o hash de resultados. Salva `.runtime/aquacrop-http-check.json`, não versionado. O relatório contém entradas, hipóteses, diagnósticos, parâmetros e resultados. O arquivo oficial 7.3 auditado não é dependência operacional da implementação.

A prova HTTP passou no container Linux, com replay exato do hash da saída. O teste automático de conservação tem tolerância numérica; diferenças residuais de arredondamento entre plataformas não são precisão agronômica. O motor só é aceito como terminado com maturidade ou morte simulada; corte por data-limite sem uma dessas condições é recusado como safra incompleta.

Pendências: FAO oficial 7.3; calibração/validação de campo; solo medido/HWSD; irrigação/eventos e outros manejos; culturas além da Maize validada; efeitos de rotação e demais estresses; integração de I13; ligação pelo desenvolvedor principal ao assistente/Flask. O assistente deve descobrir `simulate_aquacrop` em `/v1/capabilities`/OpenAPI, solicitar as hipóteses obrigatórias e consumir a resposta — não copiar a lógica para a aplicação principal.
