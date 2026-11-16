(function () {
  'use strict';
  const english = {
    'Ir para o conteúdo': 'Skip to content',
    'Voltar para o site': 'Back to the site',
    'O projeto': 'The project',
    'Nosso pitch': 'Our pitch',
    'Repositório GitHub': 'GitHub repository',
    'DA INFORMAÇÃO À DECISÃO NO CAMPO': 'FROM INFORMATION TO DECISIONS IN THE FIELD',
    'Inteligência para': 'Insights to',
    'cultivar o futuro.': 'grow the future.',
    'O AGRION busca conectar dados ambientais, conhecimento agronômico e inteligência artificial para ajudar agricultores a conhecer sua propriedade e explorar cenários de cultivo.': 'AGRION aims to connect environmental data, agricultural knowledge and artificial intelligence to help farmers understand their property and explore crop scenarios.',
    'Do clima ao planejamento, traduzimos informações complexas em uma conversa mais simples sobre o campo.': 'From weather to planning, we turn complex information into a clearer conversation about farming.',
    'Conheça nossa proposta': 'Explore our idea',
    'Uma iniciativa da equipe': 'An initiative by the',
    'Dados que aproximam.': 'Data that connects.',
    'Decisões que cultivam.': 'Decisions that help us grow.',
    'Tecnologia com os pés no campo': 'Technology grounded in the field',
    'Dados ambientais': 'Environmental data',
    'Conhecimento agronômico': 'Agricultural knowledge',
    'Inteligência artificial': 'Artificial intelligence',
    'CONHEÇA A IDEIA': 'EXPLORE THE IDEA',
    'O desafio, a proposta e o que queremos': 'The challenge, our idea and what we hope',
    'construir para o futuro da agricultura.': 'to build for the future of farming.',
    'APRESENTAÇÃO DO PROJETO': 'PROJECT PRESENTATION',
    'Nosso vídeo pitch estará disponível aqui em breve.': 'Our pitch video will be available here soon.',
    'Inteligência para cultivar o futuro.': 'Insights to grow the future.',
    'Uma ideia que nasce do campo e olha para o futuro.': 'An idea rooted in the field and looking to the future.',
    'Abrir vídeo em outra aba': 'Open video in a new tab',
    'Ative o JavaScript para exibir o vídeo incorporado. O repositório abaixo continua disponível.': 'Enable JavaScript to play the embedded video. The repository below remains available.',
    'DA PROPOSTA À IMPLEMENTAÇÃO': 'FROM IDEA TO IMPLEMENTATION',
    'Código do projeto': 'Project code',
    'Código-fonte e arquitetura do AGRION': 'AGRION source code and architecture',
    'para avaliação técnica da proposta.': 'for technical review of the project.',
    'REPOSITÓRIO PRINCIPAL': 'MAIN REPOSITORY',
    'Código-fonte da aplicação e documentação da experiência do agricultor.': 'Application source code and documentation of the farmer experience.',
    'Ver código no GitHub': 'View code on GitHub',
    'Desenvolvido pela equipe': 'Developed by the',
    'AGRION, início': 'AGRION, home',
    'Navegação da apresentação': 'Presentation navigation',
    'Paisagem agrícola ilustrativa, com uma lavoura iluminada pelo nascer do sol': 'Illustrative farm landscape with a field lit by the sunrise',
    'Pilares do projeto': 'Project pillars',
    'Assistir ao vídeo pitch do AGRION': 'Watch the AGRION pitch video'
  };
  const textNodes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement?.closest('script,style,option')) continue;
    const original = node.nodeValue;
    if (original.trim()) textNodes.push([node, original]);
  }
  const attributes = [];
  document.querySelectorAll('[aria-label],[alt]').forEach(element => {
    for (const name of ['aria-label', 'alt']) if (element.hasAttribute(name)) attributes.push([element, name, element.getAttribute(name)]);
  });
  function render() {
    const translated = window.AgrionLocale.get() === 'en-US';
    for (const [node, original] of textNodes) {
      const value = original.trim();
      node.nodeValue = translated && english[value] ? original.replace(value, english[value]) : original;
    }
    for (const [element, name, original] of attributes) element.setAttribute(name, translated && english[original] ? english[original] : original);
  }
  window.addEventListener('agrion:language', render);
  render();
})();
