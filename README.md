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

Após cadastrar o perímetro, o agricultor pode abrir uma entrevista por voz ou texto. O perfil estruturado fica no IndexedDB do navegador e usa campos e categorias canônicos, independentemente do idioma escolhido (pt-BR, en-US ou es-ES). A conexão Live passa pelo Flask; o navegador não recebe credenciais Google.

Configure `GOOGLE_CLOUD_PROJECT=space-invaders-514718`, `GOOGLE_CLOUD_LOCATION=us-central1` para o modelo Live e `GOOGLE_CLOUD_EXTRACTION_LOCATION=us` para `gemini-3.5-flash-lite`. O container usa Application Default Credentials da service account vinculada à Compute Engine. A API Vertex AI deve estar habilitada e a conta precisa de `aiplatform.endpoints.predict` (por exemplo, `roles/aiplatform.user`). Não crie chave Gemini e não use AI Studio. A configuração de proxy reverso precisa encaminhar o upgrade WebSocket para `/api/interview/live-session`.

O endpoint de token efêmero descrito na especificação original foi substituído por esse relay WebSocket porque Vertex AI com service account usa autenticação servidor a servidor. O endpoint `/api/interview/extract` usa o modelo textual do Vertex AI e retorna erros explícitos se o serviço não estiver configurado ou estiver indisponível. Ainda faltam validação real de áudio, permissões e modelos no projeto GCP, e teste no domínio HTTPS da VM; não houve deploy remoto.
