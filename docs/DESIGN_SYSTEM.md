# Design system

Fonte oficial: [`references/agrion_tailwind.html`](../references/agrion_tailwind.html) e [`references/agrion_guia.md`](../references/agrion_guia.md). O CSS Tailwind v4.1.10 compilado está embutido no HTML. Os arquivos de fonte e build citados no guia não estão disponíveis neste repositório.

Paleta: verde principal `#385C39`, destaque `#D8E889`, fundo `#F8F8F1`, superfície branca. A tipografia usa Plus Jakarta Sans para títulos e Inter para texto, com alternativas do sistema.

Cards arredondados, botões, pílulas, campos, ícones SVG e espaçamentos seguem o protótipo. A navegação principal fica na lateral no desktop e na barra inferior no mobile. Grids e colunas reduzem conforme a largura; preservar áreas de toque e legibilidade.

Ao alterar a interface, consulte as referências, mantenha cores e componentes existentes e verifique os estados desktop/mobile. Não apresente dados demonstrativos como análise agrícola real.

## Boas-vindas

A apresentação inicial usa `app/static/agrion-hero-mobile.jpg` até 767 px e `app/static/agrion-hero-desktop.jpg` a partir de 768 px. O elemento `<picture>` seleciona a imagem e o CSS aplica um degradê para o fundo. A composição é vertical no celular e divide texto e fotografia em duas colunas no tablet e desktop. Os estilos específicos ficam em `#agrion-welcome-styles` dentro de `app/templates/index.html`, sem alterar o CSS compilado do protótipo. Os dois botões mostram apenas o aviso de funcionalidade futura; a tela não inicia cadastro nem autenticação.
