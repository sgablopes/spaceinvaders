# Agrion V3.1 — Versão Tailwind CSS

## O que mudou

**Nome da aplicação:** Agrion. *Flora* permanece apenas como referência ao estilo visual aprovado (cores, tipografia, geometria). O nome visível, os títulos, o cabeçalho, o assistente e os metadados HTML foram atualizados.

**Camada de estilos:** o CSS personalizado do protótipo anterior foi substituído por estilos **compilados pelo Tailwind CSS v4.1.10**, a partir do arquivo `agrion_tailwind_source.css`.

Para preservar a aparência com rigor, as classes semânticas da interface (por exemplo, `.hero`, `.card`, `.btn`, `.navitem`) foram mantidas, e suas propriedades foram recriadas com diretivas **`@apply`**. Essa é uma integração Tailwind por camada de componentes, **não uma reescrita de todas as tags HTML com classes utilitárias inline**. Os valores que precisavam permanecer exatos usam utilitários com valores arbitrários do Tailwind.

**HTML e JavaScript:** a estrutura das telas, os nomes das ações, os manipuladores de eventos, as validações, a lógica de seleção e as funções de armazenamento não foram alterados. A única alteração no corpo de JavaScript foram as menções visíveis *Flora → Agrion*.

## Arquivos

- **`agrion_v3_1_tailwind.html`** — protótipo pronto para abrir; CSS Tailwind **compilado e embutido** no HTML. Não requer instalação de Tailwind para execução.
- **`agrion_tailwind_source.css`** — código-fonte editável em Tailwind v4, com `@theme` e `@apply`.
- **`agrion.tailwind.css`** — saída compilada separada, útil para integração em projetos frontend.
- **`agrion_tailwind_template.html`** — HTML/JS original com marca Agrion e marcador do CSS compilado.
- **`build_agrion_tailwind.mjs`** — script de compilação e produção do HTML autônomo.
- **`package.json`** — dependência e comando de build.
- **`agrion_preview_home.png`**, etc. — prévias capturadas durante a revisão visual.

## Abrir e testar

Para **visualização**, basta abrir `agrion_v3_1_tailwind.html` no navegador. As fontes Google são opcionais, com alternativas locais se não houver acesso à rede.

Para testar o **IndexedDB, câmera e geolocalização** com uma origem estável, recomenda-se servir a pasta pelo localhost:

```bash
python -m http.server 8000
```

Acesse `http://localhost:8000/agrion_v3_1_tailwind.html`.

> Disponibilidade de IndexedDB, câmera e localização depende do navegador, das permissões e da origem. O protótipo não possui backend nem sincronização remota. O botão de modo campo simula conectividade.

## Editar os estilos com Tailwind

Com Node.js e npm instalados, na pasta do projeto:

```bash
npm install
npm run build
```

O comando compila `agrion_tailwind_source.css` usando Tailwind v4.1.10 e atualiza o CSS separado e o HTML autônomo. Não é necessário CDN ou JavaScript do Tailwind em produção.

**Por que usar `@apply`?** O pedido era trocar apenas a tecnologia de estilos, mantendo aparência, navegação e funcionalidades. A substituição completa das classes semânticas por centenas de utilities no DOM aumentaria desnecessariamente o risco de regressões e exigiria reescrever as strings HTML geradas pelo JavaScript.

## Testes realizados

- CSS compilado com Tailwind v4.1.10 sem erros.
- JavaScript comparado entre os dois HTML: **igual, exceto pelas substituições de nome visível**.
- Comparação das dimensões e estilos computados nos navegadores de teste em **390, 800 e 1280 px**: largura, disposição, cores, espaçamentos e tipografia preservados nas amostras; diferenças observadas foram larguras de textos causadas por *Flora → Agrion*.
- Nenhum erro de execução de JavaScript na renderização inicial nos tamanhos acima.
- A navegação entre páginas será validada adicionalmente por teste de ações no navegador sem URL local. **O navegador automatizado deste ambiente bloqueia navegação para localhost e file://**, portanto não foi possível confirmar aqui a persistência real após recarregar com uma origem estável; a lógica IndexedDB é a mesma do arquivo original.

## Compatibilidade de registros existentes

Os identificadores técnicos `flora-demo-v3-1` (localStorage) e `flora-demo-registros-v1` (IndexedDB) foram **deliberadamente preservados**. Isso permite que, sob a **mesma origem do navegador**, dados demonstrativos existentes no protótipo original continuem acessíveis na versão Agrion. Esses nomes são internos e não aparecem na interface. Uma migração de armazenamento pode ser realizada depois, junto à arquitetura de dados definitiva.

## O que NÃO foi adicionado

A migração de CSS **não** implementa APIs NASA, análise agrícola, mapa GIS real, OCR, IA conectada ou sincronização de registros. Essas limitações são as mesmas da V3.1 original.
