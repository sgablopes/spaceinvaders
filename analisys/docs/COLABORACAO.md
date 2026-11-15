# Colaboração e entrega das análises

## Responsabilidades

Este trabalho desenvolve métodos, módulos, uma única API FastAPI, seu container Docker, testes e documentação exclusivamente em `analisys/`, na branch `analisys`. O desenvolvedor principal mantém a aplicação e implementa o consumo dos endpoints entregues. O merge leva a pasta de análises para a branch de destino; conectar a interface e a aplicação à API exige trabalho explícito do desenvolvedor principal.

## Isolamento do ambiente

Cada desenvolvedor deve usar seu próprio clone ou worktree. Os dois podem trabalhar no mesmo repositório remoto, mas não devem alternar branches no mesmo diretório durante trabalho simultâneo.

O checkout usado neste chat está na branch `analisys`. Antes de iniciar outra sessão nele, verifique a branch ativa e as alterações pendentes. A criação de um segundo checkout ou worktree não faz parte desta configuração inicial e ainda deve ser organizada antes do trabalho simultâneo.

## Ciclo de entrega

1. Definir uma análise pequena e seu critério de aceitação: pergunta respondida, fontes, entradas disponíveis e resultado esperado.
2. Documentar seu contrato em `analisys/docs/`: campos de entrada e saída, tipos, unidades, campos obrigatórios, versões, erros e comportamento quando faltam dados.
3. Inspecionar as fontes disponíveis e registrar a escolha entre leitura de Excel, cache ou importação em banco, considerando velocidade, volume e atualização. Implementar módulos reutilizáveis em `analisys/src/`, separando acesso a dados, cálculos e routers da única API FastAPI, sem depender da interface, do navegador ou de arquivos internos da aplicação.
4. Adicionar testes em `analisys/tests/`, incluindo casos relevantes de dados ausentes, inválidos e limites do método. Identificar fixtures sintéticas como tais.
5. Registrar instruções de execução, dependências, exemplo de uso, fontes e limitações. Se houver API externa, documentar configuração e tratamento de indisponibilidade sem incluir credenciais.
6. Preparar uma entrega com commits restritos a `analisys/` e abrir uma revisão/PR para a branch de integração acordada com o desenvolvedor principal. Push e abertura da PR dependem de solicitação explícita; este documento não os executa nem os autoriza automaticamente.
7. Revisar contrato e resultados com o desenvolvedor principal. Fazer merge após os critérios de aceitação e os testes passarem e houver aprovação explícita para integrar.
8. O desenvolvedor principal implementa ou atualiza a ligação com Flask, endpoints e interface em seu próprio trabalho, testa o fluxo completo e decide a publicação.

Entregar por análise validada evita acumular todo o trabalho em um único merge grande. A branch `analisys` pode continuar recebendo as próximas análises após cada integração.

## Como o outro desenvolvedor consome o trabalho

Cada entrega deve indicar os endpoints HTTP, seus esquemas OpenAPI, o comando de teste e um exemplo reproduzível de requisição e resposta. Os caminhos serão definidos com a primeira implementação, sem prometer endpoints ainda inexistentes. Tipos de dados diferentes terão endpoints distintos na mesma API.

Após o merge, a aplicação deve consumir a API FastAPI pelo contrato HTTP acordado. Evite copiar a lógica para dentro da aplicação, pois isso cria duas implementações para manter. As dependências de análise ficam no container próprio, com configuração dentro de `analisys/`.

A aplicação principal mantém a porta 8000 do host. Para as análises, a proposta inicial é publicar uma porta configurável 8001 do host para a porta interna 8000 do container, verificando disponibilidade antes de iniciar. Entregue instruções de acesso pelo host e entre containers; nesse último caso, use o nome do serviço em uma rede Docker compartilhada quando ela estiver configurada. A configuração dessa integração na aplicação principal cabe ao outro desenvolvedor; não altere seu Compose neste trabalho.

O contrato deve distinguir valores calculados, dados observados e hipóteses. Resultado sem dados suficientes deve indicar a limitação explicitamente, sem preencher lacunas com números apresentados como reais. Mudanças incompatíveis em uma interface já consumida devem ser documentadas com instruções de migração e combinadas antes da integração.

## Critérios para integrar

- Método, fontes, unidades e limitações documentados.
- Contrato de entrada, saída e erros revisável e reproduzível.
- Testes pertinentes aprovados, com comando e resultado registrados na entrega.
- Nenhum segredo ou dado privado incluído.
- Diff da entrega restrito a `analisys/`.
- Dependências e adaptações necessárias na aplicação informadas ao desenvolvedor principal.
- Aprovação explícita para merge; deploy decidido separadamente.

## Estado da entrega de dados

A branch `analisys` contém a API FastAPI, índice SQLite das fontes locais, cliente GAEZ externo, configuração Docker independente e testes. O contrato de consumo e as limitações estão em [API.md](API.md). A aplicação principal não foi modificada; sua integração HTTP continua com o desenvolvedor principal. Commit e push desta entrega foram solicitados pelo usuário; consulte o histórico Git para seus identificadores. Não houve PR, merge ou deploy remoto nesta entrega.

A continuação incorpora NASA POWER e conecta automaticamente seus dados a I01/I02 no mesmo container e Swagger, com núcleo anterior versionado. As quatro operações de análise e as pendências estão em [DELIVERY_AUTOMATIC_INDICATORS.md](DELIVERY_AUTOMATIC_INDICATORS.md). As continuações posteriores ao commit inicial ainda precisam de commit/push quando solicitados.

O conector Meteomatics de forecast também pertence à mesma API; não altera o modo histórico NASA. Seu consumo e a pendência de credenciais/permissões estão em [DELIVERY_METEOMATICS.md](DELIVERY_METEOMATICS.md). Não apresente a presença do endpoint ou a configuração de credenciais como prova de previsão autenticada validada.

A continuação [DELIVERY_WEATHER.md](DELIVERY_WEATHER.md) registra a validação autenticada real, o seletor Meteomatics/Open-Meteo compartilhado pelos indicadores e a prova de acesso pontual GEOS-FP. A prova de transporte não substitui validação agronômica nem confirma integrações ainda pendentes.

A [entrega AquaCrop](DELIVERY_AQUACROP.md) disponibiliza `simulate_aquacrop` no mesmo OpenAPI: motor AquaCrop-OSPy 3.0.12, Maize de sequeiro, NASA/FAO-56 ou clima próprio e parâmetros explicitamente assumidos. O desenvolvedor principal deve conectar esse contrato ao assistente para executar simulações, preservando a distinção de produtividade simulada versus observada e de OSPy versus FAO oficial 7.3.

A [entrega FAOSTAT](DELIVERY_FAOSTAT.md) acrescenta consulta de preços históricos e seleção explícita de USD/t no I14. O desenvolvedor principal deve preservar ano, unidade, flag e hipótese do cenário, sem apresentar preços como custos ou previsões. O CSV de 214 MB é distribuído separadamente, fora do Git; precisa estar em `analisys/` junto à planilha de países antes do build Docker. Os índices derivados não são versionados.
