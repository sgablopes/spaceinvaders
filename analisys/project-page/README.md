# Apresentação pública do AGRION

Página estática independente, criada na branch `project-presentation` a partir da `origin/main` em `5828bc9`. O uso desta branch é a exceção explicitamente solicitada pelo usuário para a página; os arquivos continuam restritos a `analisys/`.

Página voltada à apresentação aos jurados do NASA Space Apps Challenge. Ordem: descrição breve do projeto → vídeo pitch → repositório principal para avaliação técnica. O cartão de dados e análises e o link separado da API foram removidos. A seção de código não inclui convites para colaborar ou acompanhar o desenvolvimento.

## Abrir localmente

De dentro desta pasta, execute `python -B -m http.server 8002 --bind 127.0.0.1` e abra `http://127.0.0.1:8002/`. Também é possível abrir `index.html` diretamente. Não há framework, serviço de API novo, dependências de build ou credenciais. As fontes Google são opcionais; há alternativas locais. As imagens foram copiadas dos assets existentes, sem alterar os originais.

## Vídeo pitch

Preencha somente `pitchUrl` em `config.js` com o link público fornecido pela equipe. Até ele ser informado, o espaço do vídeo mostra um estado de publicação futura, sem vídeo fictício. YouTube e Vimeo são incorporados apenas após o clique da pessoa; MP4/WebM HTTPS usa vídeo nativo. Outros links HTTPS abrem externamente. Não há autoplay ao abrir a página. YouTube usa o domínio de privacidade `youtube-nocookie.com`.

O link de código aponta para `sgablopes/spaceinvaders`. O cartão ocupa uma coluna também no desktop.

O cabeçalho inclui o botão verde **Voltar para o site**, antes de **O projeto**, apontando para `https://agrion.earth`. O atalho da seção de código chama-se **Repositório GitHub**. No celular, os dois botões ficam visíveis em uma linha própria.

## Integração e publicação

O diretório inteiro pode ser servido por hospedagem estática ou por uma rota/subdiretório definida pelo desenvolvedor principal, preservando os caminhos relativos. Não foram modificados Flask, FastAPI, Nginx, Docker, aplicação principal ou infraestrutura. Não houve publicação externa. O endereço público final e o link definitivo do vídeo dependem da equipe.

Testes: `python -B -m unittest discover -s tests -q`. Os testes de resolução do player usam `node --test tests/player.test.cjs` quando Node está disponível.

Nesta entrega, os quatro testes de estrutura/links/assets passaram. Os seis testes JavaScript passaram no runtime Node disponível ao assistente; o executável `node` não está no PATH do terminal local. A conferência visual automatizada ficou bloqueada pelo host de navegador indisponível e pela expiração da solicitação de acesso à janela do Chrome; não se declara revisão visual desktop/mobile concluída.

O vídeo foi confirmado pela equipe como ainda em produção. A página fica deliberadamente em estado “em breve” até receber o link; nenhum vídeo de demonstração ou repositório adicional foi inventado. Não houve commit/push desta página nesta etapa.
