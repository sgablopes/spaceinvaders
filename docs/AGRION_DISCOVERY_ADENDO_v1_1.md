# Agrion Discovery — adendo v1.1

Este adendo atualiza a especificação v1 para os testes da entrevista. A arquitetura Flask, Vertex AI e persistência local permanece a mesma.

## Itens essenciais

O checklist agora tem nove campos. Aos sete campos da v1 somam-se:

- `next_crop_preference`: cultura preferida para a próxima safra, `{ "crop": "milho", "no_preference": false }`, ou ausência explícita de preferência, `{ "crop": null, "no_preference": true }`. Desconhecimento ou recusa continuam usando o estado `unknown` com motivo.
- `current_season_stage`: fase da safra atual, com `stage` canônico: `not_started`, `planning`, `soil_preparation`, `planting`, `growing`, `flowering`, `fruiting`, `harvesting`, `post_harvest`, `fallow` ou `other`; `notes` é opcional.

O idioma da conversa não altera IDs nem categorias. O Agrion pergunta os itens faltantes naturalmente, sem ordem fixa e sem repetir o que já foi informado. Os limites de tempo e o fechamento parcial da v1 continuam válidos.

## Primeiro cultivo

O perfil inclui também `current_crop` (cultura atualmente plantada) e `planting_date` (data de plantio). A data usa `date` em formato `AAAA`, `AAAA-MM` ou `AAAA-MM-DD`, preservando a precisão informada; `not_planted: true` registra que o plantio ainda não ocorreu. Perfis antigos recebem os campos pendentes sem apagar dados, e entrevistas já concluídas continuam acessíveis. Esses dados não calculam automaticamente a fase da safra.

"Nunca plantei nesta área" é resposta explícita e confirmada. Registrar `last_crop` com `crop: null` e `never_cultivated: true`, `previous_crop` com `crop: null` e `no_previous_cultivation: true`, e `last_harvest_result` com `qualitative_result: "not_applicable"`. A mesma evidência literal pode justificar os três campos. `not_applicable` significa ausência de safra anterior nessa área; não representa uma lavoura plantada que deixou de produzir.

"Vou começar agora" pode resolver `current_season_stage` como `not_started` ou `planning`, conforme o sentido da fala. Não presumir uma cultura preferida, recursos, dificuldades ou objetivo. Em vez de perguntar por dificuldades de uma colheita inexistente, perguntar por obstáculos para iniciar o cultivo.

## Dados locais de teste

Na atualização do IndexedDB `agrion-discovery` da versão 1 para 2, os stores de perfil, entrevistas, revisões e extrações pendentes são limpos. Esta etapa de desenvolvimento não migra os registros da v1. O cadastro geográfico, guardado separadamente, não é limpo.
