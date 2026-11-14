# Agrion V0.1

O Agrion é uma proposta da equipe Space Invaders para o NASA Space Apps Challenge 2026. A aplicação pretende apoiar decisões sobre cultivos, rotação, conservação do solo e rentabilidade com dados ambientais, conhecimento agrícola e IA. Nesta versão, a interface é um protótipo demonstrativo: os dados agrícolas não são recomendações reais, e NASA, IA e serviços meteorológicos ainda não estão conectados.

## Funcionalidades atuais e previstas

O protótipo permite cadastro demonstrativo de propriedade, descoberta de culturas, comparação de cenários, mapa ilustrativo, diário de safra, registros locais e interface de assistente sem respostas de IA. Ele usa localStorage e IndexedDB do navegador; não há contas nem sincronização. Estão previstos dados NASA, fontes agrícolas verificadas, IA e persistência PostgreSQL/PostGIS.

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

## Docker

```bash
docker compose up -d --build
docker compose ps
```

Acesse `http://127.0.0.1:8000/`. O Compose publica somente no loopback. Logs: `docker compose logs app`.

## Testes

```bash
python -m unittest discover -s tests -v
```

Execute após instalar as dependências.

## Deploy na VM

No Debian 13, em `/home/sgablopes/projects/agrion`, sincronize a versão pelo GitHub com `git pull --ff-only`, execute `docker compose up -d --build` e confirme `curl -f http://127.0.0.1:8000/api/health`. Antes de mudar Nginx, inspecione `sudo nginx -T`, identifique domínio e virtual host, faça backup do arquivo específico e adicione o proxy para `http://127.0.0.1:8000`. Valide com `sudo nginx -t` antes de `sudo systemctl reload nginx`. Preserve a configuração HTTPS existente. Não há configuração de domínio ou certificado fornecida nesta versão.

## Estado

Backend e empacotamento iniciais concluídos. O protótipo mantém suas interações locais. Publicação na VM, integrações externas, banco de dados e autenticação pendentes.
