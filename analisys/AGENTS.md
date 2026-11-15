# Instruções obrigatórias — análises do Agrion

## Escopo e isolamento

Este é o espaço exclusivo de desenvolvimento das análises do Agrion. Por determinação do usuário, todas as atividades deste chat e suas continuações devem seguir estas regras. Leia este arquivo antes de iniciar qualquer tarefa de análise, inclusive quando a sessão começar na raiz do repositório.

- Crie, edite, mova ou remova arquivos exclusivamente dentro de `analisys/`.
- Nunca altere arquivos da aplicação principal, nem configurações, dependências, testes, documentação ou instruções na raiz e nos demais diretórios. Isso inclui o `AGENTS.md` da raiz.
- Arquivos externos a `analisys/` podem ser consultados em modo de leitura. Leia `README.md` e `docs/ARCHITECTURE.md` da raiz antes de mudanças relevantes e consulte `references/` antes de propostas de interface.
- Necessidades de integração com a aplicação devem ser descritas em `analisys/docs/`, para implementação pelo desenvolvedor principal. Não aplique essas mudanças fora desta pasta.
- Não execute comandos, geradores ou testes que modifiquem arquivos fora de `analisys/`. Direcione caches, resultados e arquivos temporários para esta pasta quando necessário.
- Uma mudança de escopo exige instrução explícita do usuário; não presuma autorização por conveniência técnica.

## Git e colaboração

- Trabalhe exclusivamente na branch `analisys`. Confira a branch ativa e `git status --short` antes de qualquer alteração.
- Se a branch ativa for outra, não edite arquivos. Só mude para `analisys` após verificar que isso não transportará alterações de outro trabalho. Havendo ambiguidade ou alterações alheias, peça orientação.
- Preserve alterações existentes de outros desenvolvedores. Não use limpeza, reset, restauração ou exclusão para resolver conflitos sem autorização explícita.
- Ao preparar um commit, selecione caminhos específicos dentro de `analisys/`; nunca use `git add .` ou `git add -A` sem escopo. Confira o diff preparado e não inclua arquivos externos à pasta.
- Não faça merge, rebase, cherry-pick, push, deploy ou integração com a aplicação principal sem solicitação explícita.
- Uma branch não isola arquivos em um diretório compartilhado. Para trabalho simultâneo, use checkouts ou worktrees distintos. Não troque a branch de um checkout em uso pelo desenvolvedor principal.

## Organização própria

Siga também o fluxo de entrega em `docs/COLABORACAO.md`. Cada análise destinada ao desenvolvedor principal deve ter contrato de entrada e saída, testes e instruções de uso reproduzíveis. O desenvolvedor principal é responsável por conectar a análise à aplicação.

- `README.md`: propósito, execução, estrutura e estado das análises.
- `docs/`: decisões, métodos, fontes, contratos de integração e limitações.
- `src/`: código modular das análises.
- `tests/`: testes das funcionalidades de análise.
- `data/`: dados de entrada autorizados e metadados de origem.
- `outputs/`: relatórios e resultados gerados.

Crie esses subdiretórios conforme a necessidade. Dependências e configurações exclusivas das análises devem ficar em `analisys/`. FastAPI está explicitamente autorizado e é obrigatório neste serviço. Outros frameworks exigem autorização. Preserve a stack Flask + HTML + JavaScript + Tailwind da aplicação principal.

## API, dados e container

- Disponibilize os dados e resultados por uma única API FastAPI de análises. Tipos de dados diferentes devem ter endpoints distintos na mesma API; não crie uma API ou serviço HTTP separado para cada fonte, planilha ou análise. Organize os endpoints em routers e mantenha acesso a dados e cálculos em módulos separados.
- A integração do desenvolvedor principal deve consumir os contratos HTTP dessa API. Documente caminhos, parâmetros, esquemas de resposta, unidades, erros e exemplos; mantenha a documentação OpenAPI coerente com a implementação.
- Antes de implementar, inspecione os arquivos, contratos e dados efetivamente disponíveis. Escolha a solução com base no volume, frequência de atualização, consultas, concorrência e tempo de resposta esperados. Não presuma que um arquivo citado esteja disponível: registre sua ausência.
- Excel pode ser fonte de entrada. A equipe de análises pode optar por leitura validada, carga em memória/cache ou importação em banco de dados, sem nova aprovação para essa escolha, priorizando velocidade de desenvolvimento e de consulta, simplicidade e confiabilidade. Não adicione banco automaticamente; documente a decisão e as evidências disponíveis. Operações destrutivas e alterações na infraestrutura principal continuam exigindo autorização.
- Se houver importação para banco, preserve a fonte original e registre origem, versão/data da carga, validações e procedimento de atualização. Evite reprocessar a planilha inteira a cada requisição quando isso comprometer o desempenho. Mudanças de armazenamento devem preservar o contrato HTTP consumido pela aplicação.
- Isole a API de análises em container Docker próprio. Mantenha Dockerfile, configuração de Compose, dependências e instruções dentro de `analisys/`, com execução independente. Não altere o Dockerfile ou o Compose da aplicação principal.
- A porta 8000 do host pertence à aplicação principal e não pode ser ocupada pelas análises. Use uma porta de host distinta e configurável (padrão proposto: 8001, verificando disponibilidade antes de iniciar). A porta interna do container pode ser 8000 sem conflito. Documente endereços de acesso pelo host e pela rede Docker; containers distintos não compartilham `localhost`.
- Configurações de rede ou de integração necessárias fora de `analisys/` devem ser documentadas para o desenvolvedor principal. Não publique o serviço externamente nem altere a infraestrutura principal nesta etapa.
- Inclua testes dos contratos dos endpoints e dos cálculos nas novas funcionalidades. Registre como iniciar, verificar a saúde do serviço e executar os testes. Não apresente container, endpoint ou banco planejado como já implementado.

## Qualidade, dados e segurança

- Implemente testes para novas funcionalidades e atualize a documentação dentro desta pasta.
- Registre origem, período, unidades, método e limitações dos dados e resultados, conforme aplicável. Identifique explicitamente dados sintéticos, exemplos e hipóteses; nunca os apresente como reais.
- Não copie credenciais nem dados pessoais ou confidenciais da aplicação para esta pasta. Não versione segredos, ambientes virtuais, caches ou grandes conjuntos de dados sem necessidade e autorização.
- Não execute operações destrutivas ou ações em serviços de produção sem autorização explícita.
- Antes de concluir, confira o diff e o status do Git para verificar o escopo das próprias alterações. Informe verificações realizadas, limitações e pendências.

## Limite de aplicação

Este arquivo estabelece instruções de trabalho para agentes; não constitui bloqueio técnico de escrita. O `AGENTS.md` da raiz continua aplicável. Inicie as sessões de análise em `analisys/` ou forneça explicitamente este arquivo no contexto para garantir sua descoberta.
