# Design system

Fonte oficial: [`references/agrion_tailwind.html`](../references/agrion_tailwind.html) e [`references/agrion_guia.md`](../references/agrion_guia.md). O CSS Tailwind v4.1.10 compilado está embutido no HTML. Os arquivos de fonte e build citados no guia não estão disponíveis neste repositório.

Paleta: verde principal `#385C39`, destaque `#D8E889`, fundo `#F8F8F1`, superfície branca. A tipografia usa Plus Jakarta Sans para títulos e Inter para texto, com alternativas do sistema.

Cards arredondados, botões, pílulas, campos, ícones SVG e espaçamentos seguem o protótipo. A navegação principal fica na lateral no desktop e na barra inferior no mobile. Grids e colunas reduzem conforme a largura; preservar áreas de toque e legibilidade.

Ao alterar a interface, consulte as referências, mantenha cores e componentes existentes e verifique os estados desktop/mobile. Não apresente dados demonstrativos como análise agrícola real.

## Boas-vindas

A apresentação inicial usa `app/static/agrion-hero-mobile.jpg` até 767 px e `app/static/agrion-hero-desktop.jpg` a partir de 768 px. O elemento `<picture>` seleciona a imagem e o CSS aplica um degradê para o fundo. A composição é vertical no celular e divide texto e fotografia em duas colunas no tablet e desktop. Os estilos específicos ficam em `#agrion-welcome-styles` dentro de `app/templates/index.html`, sem alterar o CSS compilado do protótipo. O botão **Entrar** inicia a identificação sem criar conta ou autenticação.

## Primeiro acesso e propriedade

A tela de boas-vindas mantém imagem, textos e benefícios, com um único botão **Entrar**. A identificação usa card claro, campos arredondados e botão verde. O mapa usa satélite como fundo, busca sobreposta e um painel de terreno: inferior no mobile e lateral no desktop. O polígono tem borda `#D8E889` e preenchimento semitransparente `#385C39`. Os controles de desenho seguem o mesmo padrão de botões do Agrion. Estilos adicionais ficam em `app/static/property-flow.css`; o CSS Tailwind compilado e as telas demonstrativas permanecem preservados.
# Agrion Discovery

O Discovery ocupa uma tela inteira após o cadastro da propriedade. O cabeçalho mostra o nome da pessoa e da propriedade; o retrato circular usa `app/static/agrion-avatar.jpeg`. A tela mantém a paleta Agrion (`#385C39`, `#D8E889`, `#F8F8F1`), Plus Jakarta Sans e Inter, superfícies claras e controles arredondados. A composição é vertical no celular e ganha largura de leitura no desktop.

Na entrevista por voz, o idioma fica visível antes do início automático, após um breve intervalo. O texto da conversa usa `textContent`. O formulário estruturado aparece ao escolher **Responder manualmente em vez de conversar** e interrompe a sessão de voz. O checklist permanece interno; a pessoa vê apenas a barra de progresso, que chega a 100% quando uma entrevista é concluída.

Após o Discovery, a visão inicial usa o cabeçalho com marca e propriedade. O botão **Menu** permanece na borda inferior e eleva um painel com cartões para Clima, Medições de campo, Planejamento, Mercado agrícola, Notícias e pesquisas e Minha propriedade. O Assistente Agrion fica na tela principal; os demais atalhos não conectados são apenas apresentação.

Na última linha do menu, o botão largo **Apagar dados** pede confirmação antes de limpar neste navegador a propriedade, conversas, perfis, entrevistas, análises e registros do protótipo. Outras abas do Agrion devem ser fechadas antes da exclusão.

## Central de Inteligência — fase inicial

Após o Discovery, a animação sobre a imagem permanece enquanto o Core prepara os destaques do perfil na primeira abertura. Em seguida, a área é substituída pela dashboard: propriedade, cultura, fase e plantio informados, destaques, análise diária e recomendações com referências. Previsão, chuva acumulada e fase estimada são carregadas em seções independentes e identificam a origem e a natureza dos dados. Resultados antigos mostram a data de salvamento. Mercado, notícias, medições e histórico aguardam integrações; falhas de análise inicial permitem nova tentativa. O botão do assistente e o menu inferior mantêm seu comportamento. Em telas pequenas os cartões ficam em uma coluna; em telas maiores os indicadores ocupam até três colunas.

O cartão de monitoramento oferece uma simulação opcional de vento e chuva, desligada inicialmente. Alertas simulados aparecem destacados e identificados como simulação, com reconhecimento e histórico local. Nenhuma leitura é apresentada como proveniente de estação real nesta etapa. Em produção e mercado, a IA consulta os candidatos FAOSTAT e mostra o último preço histórico disponível, identificando o produto, o país, o ano e a correspondência não revisada. O histórico usa dados informados no Discovery e o acesso ao mapa reutiliza a edição da propriedade; notícias e medições continuam indisponíveis até haver fontes conectadas.

O desenvolvimento da cultura destaca a cultura atual e organiza fase, justificativa e colheita em linhas com ícones. Indicadores percentuais reais, como umidade prevista do ar, recebem barras acessíveis; não é criado percentual de avanço da safra sem dados que o sustentem.

O resumo da propriedade usa mapa de satélite com o perímetro cadastrado e sobreposição legível de cultura, fase declarada, plantio, colheita estimada e objetivo. Quando o mapa não estiver disponível, as informações permanecem sobre fundo verde. Produção e mercado apresenta um insight curto; fontes e dados consultados permanecem no resultado interno.
