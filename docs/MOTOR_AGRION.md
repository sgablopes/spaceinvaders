# Motor Agrion — núcleo textual

O núcleo em `app/services/engine.py` é uma interface Python reutilizável. Ele recebe uma tarefa textual, um objeto JSON de contexto, histórico opcional e idioma (`pt-BR`, `en-US` ou `es-US`) e devolve texto, modelo e a lista de ferramentas chamadas. O chamador é responsável por montar o contexto e persistir qualquer histórico.

```python
from app.services.engine import AgrionEngine

result = AgrionEngine().run(
    task='Resuma as informações disponíveis.',
    context={'property_name': 'Sítio Exemplo'},
    history=[],
    language='pt-BR',
)
print(result.text)
```

O motor usa Vertex AI, Application Default Credentials da service account da VM e o SDK Google Gen AI. Configure `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_ENGINE_LOCATION` (padrão `us`) e `GEMINI_ENGINE_MODEL` (padrão `gemini-3.8-flash`). Para `us` e `eu` o endpoint é o multirregional `aiplatform.<região>.rep.googleapis.com`. Cada chamada ao modelo tem timeout de 30 segundos; mensagens e contexto têm limites de tamanho. Não registre contexto ou conversas em logs.

## Contexto da propriedade

No navegador, `AgrionContext.load()` lê o cadastro atual e o perfil agrícola correspondente e produz o objeto JSON enviado ao motor pelo chat. `AgrionContext.build(property, profile)` também aceita os registros diretamente e rejeita perfis de outra propriedade. O contexto contém nome, propriedade, localidade, geometria, ponto central, área, dados agrícolas e estados, origem e confiança. Campos ausentes permanecem `pending`; as transcrições e trechos de evidência não são copiados para o contexto. O cadastro geográfico é a fonte atual de nomes e geometria.

## Chat textual

O botão Assistente Agrion abre a conversa textual. `POST /api/assistant/message` recebe `message`, `context`, `history` e `language` e encaminha ao motor; não há credenciais no navegador. O histórico fica no `localStorage`, separado por identificador de propriedade e limitado a 40 mensagens. O endpoint valida origem, tamanho e formato e aplica limite em memória por processo (`AGRION_ASSISTANT_MESSAGES_PER_HOUR`, padrão 60); não há conta nem sincronização entre dispositivos. Validação real com Vertex AI e a API de análises na VM continua necessária.

O cadastro salva `centerPoint` como GeoJSON Point, em `[longitude, latitude]`, com `method` e `inside_polygon`. O método é o centroide planar por área do anel exterior em coordenadas WGS84, com longitudes ajustadas na mudança de antimeridiano; é uma aproximação e não considera anéis interiores. A geometria atual do cadastro é um único perímetro sem furos. O centroide de um polígono côncavo pode ficar fora da área, indicado por `inside_polygon: false`; não substituí-lo silenciosamente. Registros anteriores sem ponto recebem o cálculo ao serem lidos e a edição da geometria o recalcula. Um resultado de consulta nesse ponto não representa necessariamente toda a propriedade.

Dados do contexto e do histórico são enviados ao modelo como conteúdo, não como instruções de sistema. Essa separação não garante que o modelo ignore instruções maliciosas inseridas nos dados; ferramentas futuras precisarão validar e limitar cada execução no servidor. A configuração e a chamada real na VM dependem de teste posterior com credenciais e acesso ao modelo.

## Ferramentas de análises

O registro em `app/services/tools.py` disponibiliza busca de nomes e requisitos ECOCROP, parâmetros e alertas FAO-56, evidências, fontes e rotações da biblioteca, dicionário AquaCrop, camadas e consulta pontual GAEZ. Cada ferramenta usa um caminho fixo, valida parâmetros e preserva o conteúdo e as fontes retornadas. Consultas locais usam páginas de até 30 registros, com `offset` e filtros exatos; uma página não representa automaticamente toda a base. A API GAEZ pode precisar de paginação própria. Unidades e classes ausentes não devem ser presumidas. O AquaCrop disponibilizado é apenas dicionário, sem simulação. Dados e evidências exigem interpretação de seus avisos e status de validação.

O motor mantém o conteúdo completo retornado pelo modelo para preservar assinaturas do Gemini e executa no máximo cinco chamadas por tarefa. Cada chamada à API tem timeout de 20 segundos e limites de resposta. Falhas retornam ao modelo como erro explícito, sem dados fictícios. Novas ferramentas exigem revisão e registro explícitos.

Na VM, inicie primeiro `docker compose -f analisys/compose.yaml up -d --build` para criar a rede externa `agrion-analisys-data`; em seguida inicie ou recrie o Compose principal. O container do Agrion participa das redes padrão e de análises e usa `AGRION_ANALYSIS_URL=http://agrion-data:8000`. A rede é obrigatória para subir o Compose principal; não expõe a API de análises publicamente. O acesso ao Vertex AI e à API real ainda precisa ser validado no ambiente da VM.

Teste isolado: `python -B -m unittest discover -s tests -p test_engine.py -v`.
