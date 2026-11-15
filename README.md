# Agrion V0.1

O Agrion é uma proposta da equipe Space Invaders para o NASA Space Apps Challenge 2026. A aplicação pretende apoiar decisões sobre cultivos, rotação, conservação do solo e rentabilidade com dados ambientais, conhecimento agrícola e IA. Nesta versão, a interface é um protótipo demonstrativo: os dados agrícolas não são recomendações reais, e NASA, IA e serviços meteorológicos ainda não estão conectados.

## Funcionalidades atuais e previstas

O protótipo permite cadastro demonstrativo de propriedade, descoberta de culturas, comparação de cenários, mapa ilustrativo, diário de safra, registros locais e interface de assistente sem respostas de IA. Ele usa localStorage e IndexedDB do navegador; não há contas nem sincronização. Estão previstos dados NASA, fontes agrícolas verificadas, IA e persistência PostgreSQL/PostGIS.

O primeiro acesso funcional agora permite informar nome, localizar uma propriedade com GPS ou busca MapTiler, desenhar um único perímetro sobre satélite e guardar o GeoJSON neste navegador. O fluxo não cria conta e não sincroniza dados.

## Tecnologias e estrutura

HTML5, JavaScript e CSS Tailwind v4 já compilado no protótipo; Python/Flask com Blueprints; Gunicorn; Docker Compose. `app/` contém servidor e interface, `tests/` os testes, `references/` os arquivos originais preservados e `docs/` as decisões técnicas e visuais.

## Execução local

```bash
python -m venv .venv
# Ative .venv conforme seu sistema
pip install -r requirements.txt
flask --app 'app:create_app' run --debug
```

Acesse `http://127.0.0.1:5000/` e `http://127.0.0.1:5000/api/health`.

Para habilitar o mapa, defina `MAPTILER_API_KEY` no ambiente antes de iniciar o Flask. Use uma chave de navegador do MapTiler; sem ela, a interface informa que o mapa não está configurado. A chave é enviada ao navegador e deve ter origens autorizadas no painel do MapTiler, incluindo `http://127.0.0.1:5000`, `http://127.0.0.1:8000` e `https://agrion.earth` conforme o ambiente usado. Não versione a chave.

## Docker

```bash
docker compose up -d --build
docker compose ps
```

Acesse `http://127.0.0.1:8000/`. O Compose publica somente no loopback. Logs: `docker compose logs app`.

Para o Compose, copie `.env.example` para `.env` e preencha `MAPTILER_API_KEY`. O arquivo `.env` é ignorado pelo Git. Na VM, configure a mesma variável no diretório do projeto antes de executar `docker compose up -d --build`.

## Mini Estação Meteorológica

O endpoint `POST /api/v1/stations/telemetry` recebe leituras do ESP32 com chave por estação em `X-Station-Key`. Configure `AGRION_STATION_KEYS` no `.env` da VM e mantenha o volume Docker `station-data` para preservar o SQLite. A tela do menu abre inicialmente `agrion-demo-001` e consulta a leitura mais recente a cada cinco segundos. O ID permite consulta pública; a chave é exigida apenas para envio. Consulte [o contrato e as limitações](docs/ESTACAO_METEOROLOGICA.md).

## Testes

```bash
python -m unittest discover -s tests -v
```

Execute após instalar as dependências.

## Deploy na VM

No Debian 13, em `/home/sgablopes/projects/agrion`, sincronize a versão pelo GitHub com `git pull --ff-only`, execute `docker compose up -d --build` e confirme `curl -f http://127.0.0.1:8000/api/health`. Antes de mudar Nginx, inspecione `sudo nginx -T`, identifique domínio e virtual host, faça backup do arquivo específico e adicione o proxy para `http://127.0.0.1:8000`. Valide com `sudo nginx -t` antes de `sudo systemctl reload nginx`. Preserve a configuração HTTPS existente. Não há configuração de domínio ou certificado fornecida nesta versão.

## Estado

Backend e empacotamento iniciais concluídos. O protótipo mantém suas interações locais. MapTiler está integrado ao primeiro acesso local; publicação na VM, integrações NASA/IA, banco de dados e autenticação seguem pendentes.

O cadastro geográfico usa `localStorage` na chave `agrion-property-v1`, separada do armazenamento demonstrativo legado. O registro contém versão, nomes, polígono GeoJSON em WGS84 (`[longitude, latitude]`), área em m² e hectares, localidade selecionada quando disponível e data do cadastro. Alterar de navegador ou limpar os dados locais remove o cadastro. A área é uma estimativa do contorno desenhado. A busca, imagens e GPS dependem de rede, permissões e configuração da chave. O botão **Continuar** da propriedade salva apenas sinaliza a próxima etapa.
# Agrion Discovery (em desenvolvimento)

Após cadastrar o perímetro, o agricultor pode iniciar a entrevista por voz ou preencher o formulário manual. O perfil estruturado fica no IndexedDB do navegador e usa campos e categorias canônicos, independentemente do idioma escolhido (pt-BR, en-US ou es-US). A conexão Live passa pelo Flask; o navegador não recebe credenciais Google.
O Discovery tem nove campos essenciais, incluindo preferência de plantio para a próxima safra e fase da safra atual. "Nunca plantei nesta área" resolve explicitamente os campos de culturas e colheita anteriores. A atualização do IndexedDB para a versão 2 reinicia os dados de teste do Discovery; o cadastro geográfico separado continua disponível. Consulte [o adendo técnico v1.1](docs/AGRION_DISCOVERY_ADENDO_v1_1.md).
A entrevista agora ocupa uma tela inteira, com nome da pessoa, propriedade e retrato do Agrion. A voz Orus inicia após um breve intervalo; a pessoa pode escolher o idioma antes disso ou responder em um formulário estruturado. Mudar para o formulário encerra a sessão de voz e preserva fatos já registrados. A lista de estados dos campos continua interna; a interface mostra apenas o progresso. Ao concluir, abre a visão inicial com cabeçalho agrícola, animação de preparação e um menu inferior que sobe para mostrar os atalhos. Esses atalhos ainda não executam ações.
A transcrição de entrada é recebida do Vertex AI e enviada, por turno finalizado, ao endpoint de extração; o perfil só muda depois da validação dos fatos. O formulário manual grava os mesmos campos canônicos diretamente no IndexedDB, com revisões e origem `user_edit`.

Ao recarregar, o aplicativo consulta a propriedade e a entrevista salvas neste navegador: entrevistas concluídas abrem a visão inicial, enquanto entrevistas incompletas retomam o Discovery. No menu, **Minha propriedade** abre a edição do perímetro; confirmar ou voltar retorna à visão inicial.

Configure `GOOGLE_CLOUD_PROJECT=space-invaders-514718`, `GOOGLE_CLOUD_LOCATION=us-central1` para o modelo Live e `GOOGLE_CLOUD_EXTRACTION_LOCATION=us` para `gemini-3.5-flash-lite`. O container usa Application Default Credentials da service account vinculada à Compute Engine. A API Vertex AI deve estar habilitada e a conta precisa de `aiplatform.endpoints.predict` (por exemplo, `roles/aiplatform.user`). Não crie chave Gemini e não use AI Studio. A configuração de proxy reverso precisa encaminhar o upgrade WebSocket para `/api/interview/live-session`.
Na extração, `us` e `eu` usam os endpoints multirregionais `aiplatform.us.rep.googleapis.com` e `aiplatform.eu.rep.googleapis.com`; o SDK não deve formar `us-aiplatform.googleapis.com`.
O esquema de geração limita `field` aos IDs agrícolas canônicos e `status` a `confirmed`, `uncertain` ou `unknown`; o servidor valida novamente os valores e a evidência literal antes de atualizar o perfil.
A pergunta anterior e até 40 turnos ordenados da conversa acompanham a extração como contexto temporário. Cada patch deve apontar para a fala do agricultor que contém sua evidência literal; o texto integral da conversa não é persistido sem consentimento. Uma resposta pode atualizar vários campos e complementar o mesmo campo no mesmo turno. Depois da extração inicial, uma segunda análise direcionada confere as lacunas ainda pendentes; antes de aceitar uma conclusão prematura, o aplicativo pode reanalisar o histórico em memória. Respostas curtas e valores incompletos passam por recuperação específica. O resultado qualitativo da colheita é preservado enquanto o Agrion solicita uma estimativa em quantidade ou valor financeiro, sem converter unidades nem inferir faturamento ou lucro.
Na entrevista Live, o Agrion primeiro se apresenta e pergunta se a pessoa está bem; após a resposta, convida um relato livre sobre a lavoura. O navegador envia estados canônicos do checklist quando mudam. A ferramenta de conclusão recebe os campos ainda pendentes, inclusive a estimativa da colheita. Uma despedida prematura com pendências provoca reanálise e retomada da pergunta; uma pausa prolongada com pendências também provoca uma retomada limitada. Um campo incerto exige uma pergunta de confirmação e uma nova resposta do agricultor antes da conclusão; reanálises não contam como essa resposta. O fechamento espera o fim do turno e da fila de áudio, com limites para confirmação ou despedida sem resposta.

O endpoint de token efêmero descrito na especificação original foi substituído por esse relay WebSocket porque Vertex AI com service account usa autenticação servidor a servidor. O endpoint `/api/interview/extract` usa o modelo textual do Vertex AI e retorna erros explícitos se o serviço não estiver configurado ou estiver indisponível. A abertura, a sincronização de estado e a despedida desta revisão ainda precisam ser validadas em uma conversa real no domínio HTTPS da VM; não houve deploy remoto nesta etapa.
