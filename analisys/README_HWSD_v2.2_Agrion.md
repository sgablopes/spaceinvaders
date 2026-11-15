# HWSD v2.2 — Base de solos do Agrion

**Fonte:** FAO / IIASA — *Harmonized World Soil Database*, versão 2.2  
**Finalidade:** fornecer propriedades do solo para preparar as entradas do simulador agrícola AquaCrop 7.3.  
**Resolução:** 30 segundos de arco (aproximadamente 1 km no equador).  
**Cobertura:** global; sete faixas de profundidade, de 0 a 200 cm.  
**Licença:** CC BY 4.0 (atribuir a fonte).

## Por que guardamos esta base?

O Agrion precisa conhecer o solo além do clima e da cultura escolhida. Um mesmo volume de chuva pode resultar em disponibilidades de água diferentes para as plantas, conforme textura, profundidade e outras propriedades do solo. A HWSD oferece essas informações em um banco geográfico padronizado, sem depender de preenchimento manual para cada localização.

## Qual a diferença para o GAEZ v5?

- **GAEZ v5:** apresenta avaliações agroecológicas, como aptidão e produtividade potencial das culturas.
- **HWSD v2.2:** disponibiliza atributos físicos e químicos do solo por unidade de mapeamento e profundidade, úteis para parametrizar o AquaCrop.

**Não é um ganho de resolução espacial:** as duas fontes são relacionadas e podem usar informações de solo da mesma família de dados. O ganho é o **acesso aos atributos de origem**, em vez de somente aos indicadores derivados do GAEZ.

## Arquivos baixados

| Arquivo | Conteúdo | Uso |
|---|---|---|
| `hwsd2.2_raster.zip` | Raster de unidades de mapeamento (`HWSD2.bil` e arquivos auxiliares) | Encontrar a unidade de solo correspondente às coordenadas |
| `hwsd2.2_db.zip` | Banco de atributos Microsoft Access (`HWSD2.2.mdb`) | Consultar os componentes do solo e suas propriedades nas sete camadas |

**Guarde os dois ZIPs.** O raster e o banco se complementam; a camada visual WMTS do portal não substitui esses arquivos.

## Como utilizar no Agrion (fluxo simples)

1. **Receber latitude e longitude** da propriedade ou do talhão.
2. **Ler o raster** na posição correspondente e obter o identificador da unidade de mapeamento do solo (SMU).
3. **Consultar o banco `.mdb`** usando esse identificador; recuperar componentes e propriedades por profundidade (por exemplo, areia, silte, argila, carbono orgânico e fragmentos grosseiros).
4. **Converter os atributos em parâmetros hidráulicos** para o AquaCrop: capacidade de campo (**FC**), ponto de murcha (**PWP**), umidade de saturação (**SAT**) e condutividade hidráulica saturada (**Ksat**), por métodos documentados e com conferência das unidades.
5. **Gerar o perfil de solo** no formato de entrada do AquaCrop e registrar procedência, métodos, hipóteses e limitações.

**Atenção:** FC, PWP, SAT e Ksat não devem ser considerados automaticamente disponíveis ou medidos; parte deles exige estimativas por funções de pedotransferência. A ligação raster → banco e a transformação hidráulica precisam ser validadas antes de utilização operacional.

## Limitações importantes

- Um pixel representa uma **unidade de mapeamento**, que pode incluir mais de um tipo/componente de solo. Não representa uma análise exata do talhão.
- Resolução de aproximadamente 1 km **não significa precisão de 1 km** nem garante homogeneidade dentro da célula.
- Resultados derivados são **estimativas regionais**. Quando disponíveis, medições de campo e análises laboratoriais devem prevalecer para decisões específicas da propriedade.
- O **SoilGrids (250 m)** pode ser avaliado futuramente para maior detalhamento espacial; não é necessário incorporá-lo antes de testar a HWSD.

## Referências oficiais

- Catálogo HWSD v2.2: https://data.apps.fao.org/catalog/iso/ff5c613c-75bb-46a9-a162-bc728059b465
- Portal GAEZ v5: https://data.apps.fao.org/gaez/?lang=en
- Referência de metodologia de solo para AquaCrop: https://www.fao.org/in-action/drought-portal/tools/d-iap/methodology/soil-data/en

**Citação da base:** FAO & IIASA. *Harmonized World Soil Database version 2.2*. Licença CC BY 4.0. Consultado em 15/11/2026.

**Status no Agrion:** arquivos obtidos; consulta geográfica inicial realizada; leitura do banco de atributos e geração validada do perfil hidráulico ainda pendentes.
