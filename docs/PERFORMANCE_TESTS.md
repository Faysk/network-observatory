# Testes individuais de funcionalidade e desempenho

A suíte `tools/performance_matrix.py` dá uma identidade estável a cada consulta. Cada resultado informa contrato funcional, tempo de consulta/resposta, serialização, validação, CPU da thread, bytes e dispersão. HTTP ainda separa TTFB, transferência e parse. Os relatórios JSON permitem comparar versões; o Markdown ordena os casos mais lentos primeiro.

## Controles de capacidade HTTP (auditoria 27/10/2026)

As chamadas `GET/HEAD` a `/api/*` e `/metrics` compartilham no máximo
**24 slots ativos** em todo o processo. Sob saturação recebem HTTP 503
imediatamente, sem abrir novas consultas de banco e sem iniciar esperas
ilimitadas. Assets estáticos não usam esses slots; os caches e semáforos
próprios dos históricos continuam iguais.

Exportações completas de dispositivos usam adicionalmente **4 slots**;
quando os quatro estiverem ocupados, novos pedidos recebem 503. Uma
exportação iniciada continua sem limite artificial de linhas e o semáforo
é sempre libertado (inclusive em erro). O cliente deve aguardar e tentar
novamente; HTTP 503 **não** significa ausência de dados.

Esse limite não substitui testes de 24h em microSD, p95 sob vários clientes,
verificação de navegador Android 8 nem quotas do sistema operativo. É uma
proteção básica contra concorrência acidental na LAN permitida, não uma
solução completa de DDoS nem de autenticação.

## CSV de eventos — exportação em fluxo

A rota `/api/export/events.csv` mantém o contrato de **até 100.000 eventos
mais recentes**, ordenados por `id DESC`, mas deixa de criar uma lista
Python e um CSV gigante em RAM. O servidor fixa um limite superior de ID,
obtém a contagem inicial e processa blocos de até 1.000 eventos por transação
SQLite curta. O socket envia as linhas progressivamente, sem manter uma
transação WAL aberta durante a espera pelo consumidor.

A resposta inclui `X-FNO-Export-Expected-Rows` (registros que devem constar
no CSV) e `X-FNO-Export-Truncated` (se o arquivo ultrapassa 100.000 no
início da exportação). O cliente pode verificar a contagem antes de confiar
num CSV transferido por HTTP/1.0 sem Content-Length. Ingestões concorrentes
posteriores ao limite superior não são adicionadas à exportação; remoções
concorrentes podem resultar num arquivo com menos linhas que o cabeçalho
esperava. Não chamar esse arquivo de snapshot transacional perfeito sob
mutações simultâneas.

Conexão fechada é o delimitador da resposta. A rota compartilha os quatro
slots de exportação existentes e devolve HTTP 503 quando ocupados. HEAD
devolve metadados sem transferir CSV. A formatação protege texto não
confiável contra interpretação como fórmulas em planilhas; o banco e JSON
originais não sofrem alterações.

## Consultas de estado e lock SQLite

O `/api/status` recolhe a parte SQLite e copia o estado do coletor sob a
proteção normal. Em seguida **liberta o lock e fecha a conexão** antes de
enumerar os arquivos da fila (`outbox`) e da quarentena no microSD.
A enumeração pode ser demorada num cartão ocupado, mas não deve manter
um lock de escrita global nem impedir que outras transações SQLite avancem.

As duas contagens da fila são informativas, recolhidas fora da transação;
podem variar durante uma entrega concorrente e **não representam um snapshot
atómico** com as métricas do router. Um teste de regressão simula uma
enumeração lenta e exige a conclusão de uma escrita simultânea.

## Cobertura

- Router: status, inventário, overview resumo/completo e dossiê em 1h/6h/12h/24h/7d/1m/1y.
- S7: snapshot, catálogo, página de arquivo bruto e cada uma das oito métricas (CPU, RAM, RX, TX, bateria, temperatura, latência e armazenamento) em todos os sete períodos suportados.
- Exportações CSV/JSON de cada período são opt-in `--include-exports`, por HTTP. O contrato exige observações originais, não pontos agregados do gráfico.
- Sintético: três cenários por caso — cache da aplicação limpo, cache aquecido e quatro consumidores simultâneos compartilhando um miss. **Limpar o cache da aplicação não limpa cache do Linux, SQLite ou SD.**
- Live: primeiro observado, repetições e concorrência; a ferramenta não limpa caches nem reinicia o servidor real.

Com o perfil completo são 82 consultas e 246 cenários de backend; HTTP com exportações tem 96 consultas e 288 cenários. Cada cenário é validado funcionalmente mesmo durante a medição. Séries limitadas a 361 pontos, zeros/null e valores de fixture são conferidos individualmente. Não concluir que os sensores físicos estão corretos só porque o JSON é válido.

Não mede paint, INP, LCP, FPS, animações, leitor de tela ou tempo de cada leitura sysfs/coletor. O frontend tem suas fixtures browser e testes Node existentes; seus números não substituem medições no navegador cliente físico. CPU da thread HTTP é do cliente de teste; não é CPU do servidor.

## Execução sintética segura

Somente fixtures inventadas; não inicia adaptador, login, sondas, coleta de hardware ou tráfego para a LAN. O HTTP sintético sobe um servidor de teste somente em loopback. A aplicação e os bancos reais não são abertos.

```sh
python tools/performance_matrix.py --output /pasta/existente/backend-v1.json
python tools/performance_matrix.py --transport http --include-exports --output /pasta/existente/http-v1.json
```

Perfil padrão: 30 dias, 24 amostras/dia, 19 identidades e padding de 4 KiB. A densidade é horária, não uma simulação de 30 dias completos a cada 60 segundos. Dimensões, ambiente e tamanho dos bancos são registrados. Para volumes maiores, ajuste `--days`, `--samples-per-day`, `--devices` e `--payload-kib`; a estimativa conservadora de fixture, índices e WAL precisa caber no orçamento (`--fixture-budget-mib`, padrão 256, máximo 1024 MiB) e na margem livre do volume. Evitar carga grande só para produzir números.

No próprio S7/Termux, o runner exige `--work-dir` e saída no microSD e reserva interna >=2 GiB. Não usa fallback interno. A limpeza alcança apenas a pasta temporária que ele mesmo criou. Relatórios existentes nunca são sobrescritos.

```sh
python tools/performance_matrix.py --days 7 --samples-per-day 24 --payload-kib 64 --work-dir /storage/SEU_SD/pasta-existente --output /storage/SEU_SD/pasta-existente/s7-sintetico-v1.json --environment-label s7-microsd-synthetic
```

## Investigar um gargalo

```sh
python tools/performance_matrix.py --case 's7/history/cpu/7d' --case 'router/device/7d' --trials 20 --output /pasta/existente/foco-v1.json
```

A seleção aceita globs e pode ser repetida. `median_ms` compara a experiência típica, máximo/dispersão mostram variação, `query_or_http_ms_median` separa o backend de serialização, e HTTP separa cabeçalhos/transferência/parse. `p95_ms` só é publicado com pelo menos 20 observações; concorrência de um único lote com quatro consumidores fica sem p95. O contrato funcional sempre prevalece sobre uma boa latência.

## Comparar uma execução de referência

```sh
python tools/performance_matrix.py --baseline /pasta/existente/backend-v1.json --output /pasta/existente/backend-v2.json --fail-regressions
```

Parâmetros e ambiente precisam ser os mesmos (inclusive rótulo, transporte, densidade, tamanho, períodos e amostras). O build pode diferir. Por padrão marca regressão se a mediana ultrapassa a anterior em 25% **mais** 5 ms de margem de ruído. Casos removidos são relatados; com `--fail-regressions`, uma regressão, baseline incompatível ou caso removido devolve exit code 1. Casos novos são identificados.

Não há baseline universal versionado com números de outro hardware. CI compartilhado varia e não recebe um limite absoluto arbitrário de milissegundos. Falhas funcionais/limites estruturais falham o CI; tempos são preservados como artefatos. Para um gate de desempenho, fornecer baseline do mesmo ambiente controlado ou orçamento explícito. Live tem carga/arquivo/cache não controlados e não recebe veredito automático de regressão, mesmo quando o rótulo do cliente é igual.

## Orçamentos por caso

Arquivo JSON privado ou sintético, escolhido pelo operador:

```json
{"rules":[{"pattern":"s7/history/*/repeat","median_ms":250,"bytes_max":100000},{"pattern":"router/device/*/first_observed","median_ms":1500}]}
```

```sh
python tools/performance_matrix.py --budgets /pasta/existente/metas.json --fail-budgets --output /pasta/existente/resultado.json
```

Os valores acima são exemplos, não metas homologadas. Regras sem caso correspondente são indicadas para detectar erros de digitação; alvo p95 sem amostras suficientes não passa silenciosamente. Sem `--fail-budgets`, o relatório sinaliza violações sem transformar ruído em falha de pipeline.

## Medição real, somente autorizada

```sh
python tools/performance_matrix.py --transport http --allow-live --live-url http://SERVIDOR:PORTA --environment-label s7-lan-clientpc --periods 24h 7d --trials 3 --output /pasta/privada/lan-data.json
```

A origem deve ser a aplicação de observabilidade, **não o painel do Huawei**. São apenas GETs, sem autenticações/sondas adicionais, sem mudanças de configuração e sem aumentar polling do coletor. Dossiês/exports reais precisam de `--device-id` explícito (12 hex); não há seleção ou descoberta de dispositivos automática. O ID, a origem e os corpos não aparecem no relatório. Rotas/casos têm aliases estáveis; falhas guardam código/tipo sem mensagens do servidor. Respostas têm timeout e limite de bytes. Exports completos podem ser grandes e devem ser habilitados deliberadamente.

Mesmo sanitizados, relatórios reais são privados: não enviar ao GitHub por padrão. Datas, tempos e volumes não demonstram igualdade de contexto entre rodadas. CI publica apenas relatórios sintéticos, com retenção de 14 dias e caminhos de artefatos explícitos, sem bancos/fixtures/payloads.

## Diagnóstico de picos e fluxo misto

`--transport http --include-flows --gzip` adiciona duas consultas compostas em 24h: abertura do Router (status, resumo, inventário) e rede do S7 (snapshot, RX, TX, latência). Cada membro valida seu contrato. O lote usa até quatro endpoints; o cenário concorrente simula quatro consumidores desses lotes (até 16 requisições). Use `--case '*/page/*'` para medir só os lotes e iniciar com `--concurrent 1` no aparelho real. Não representa renderização no navegador.

O servidor inclui `Server-Timing` nas respostas API não transmitidas em streaming: `db` mede chamadas SQL execute/fetch (inclui espera SQLite), `wait` mede aquisição dos locks/semaforos instrumentados e espera por resultado compartilhado; `serialize` e `compress` medem essas operações. `app` é o restante do tempo, incluindo construção Python e trabalho não instrumentado, não CPU pura. `total` termina antes de enviar headers e corpo. Abertura de conexão SQLite não é separada: está em `app`. Não contém SQL, parâmetros, identificadores ou payloads; não cria logs em disco. Exportações em streaming não têm essas fases nos headers.

A matriz guarda medianas `server_*_ms_median` quando disponíveis. Compare o mesmo teste com `--live-url http://127.0.0.1:8767` no S7 e pela LAN no PC. TTFB muito maior que `server_total` aponta para tempo fora da janela instrumentada, incluindo rede, conexão e despacho; não prova isoladamente qual deles é a causa. Medianas de fases independentes não devem ser subtraídas como se fossem uma mesma amostra.

`--gzip` negocia compressão nível 1 para respostas >=16 KiB com ganho >=10%; bytes do relatório são transferidos comprimidos, parse inclui descompressão. Há limite tanto de bytes recebidos quanto descomprimidos. A compressão não armazena cache e mantém `no-store`. Comparar identity/gzip com perfis explicitamente separados; não usar baseline automático entre transportes diferentes.

Para triagem sustentada, selecione os casos lentos com `--case`, use `--trials 20` e repita em momentos diferentes. O p95 passa a existir nas repetições, mas os quatro consumidores simultâneos continuam insuficientes para p95. Não chamar uma amostra inicial de cache frio.
