# Observabilidade P2 — visuais específicos, alertas locais, saúde do S7

Esta entrega é **passiva**: lê somente as amostras já recolhidas. Não usa root,
não abre portas novas, não altera Huawei, não configura firewall/WPS/NAT e não
executa processos externos para alertas. Sem Push, Telegram, email, SMS ou
reenvio de dados pessoais.

## 1. Onde ver no Router

Na página **Configuração e diagnóstico**, antes das fontes aparecem:
- **Saúde e alertas do Observatory**: RAM RSS do processo, capacidade livre no
  volume configurado, SQLite e WAL, latência p95 da API, idade da última
  recolha e estimativa de crescimento do SQLite. Quando indisponível mostra
  **Sem medição**, nunca 0.
- Alertas passivos derivados de limiares de um arquivo JSON local e mudanças
  observadas por duas leituras válidas, sem lacuna conhecida.
- Histórico de saúde em SVG, por métrica, desenhado apenas quando aberto.
  No máximo 480 amostras recentes de até 24 h, portanto pode representar
  uma **fração menor da janela**; nunca apresenta interpolação.
- As 28 fontes continuam agrupadas e auditáveis. Novas vistas apropriadas ao
  tipo de fonte exibem rádio/canal/potência configurada, bools como
  ativado/desativado, encaminhamentos UPnP, tempos de concessão DHCP e
  sinais de estações. Cada valor vem da fonte existente; sem extrapolação de
  throughput, segurança, antenas físicas ou tempo online de aparelhos.

### O que **não** representa

- RSS de **processo** não é RAM total do Android.
- Tamanho de SQLite e WAL não indica espaço efetivamente recuperável.
- O p95 vem das últimas 128 requisições à API, não de monitorização externa.
- O uso de espaço é medido para o volume configurado do arquivo. Se o volume
  desaparecer, a UI não diz que ele está vazio; a condição vira crítica.
- Crescimento MB/dia exige pelo menos **6 horas** de amostras de telemetria
  realmente disponíveis. É taxa observada, não previsão de esgotamento.
- Mudança de política não prova violação nem alteração maliciosa. O evento
  mantém o carimbo de quando a diferença foi observada, não a causa real.
- "Sem alertas ativos" significa apenas que **nenhuma regra habilitada**
  encontrou condição reconhecida nas amostras disponíveis; não é garantia
  de que a rede está saudável.

## 2. Configuração local (sem endpoint de escrita)

Modelo versionado: `config/alert_rules.example.json`.

Para personalizar, criar **uma cópia em armazenamento controlado pelo
operador**, por exemplo fora da árvore servida pela aplicação (nunca em
`app/static`, `sites/valt` ou noutro diretório HTTP):

```sh
cp config/alert_rules.example.json /CAMINHO-PRIVADO/alert_rules.json
python tools/check_alert_rules.py /CAMINHO-PRIVADO/alert_rules.json
export FNO_ALERT_RULES_FILE=/CAMINHO-PRIVADO/alert_rules.json
```

Reiniciar **apenas o serviço da aplicação** para aplicar a nova variável de
ambiente. Quando o ficheiro já está configurado, alterações do seu conteúdo
são lidas nas consultas seguintes; validar antes. Não editar por HTTP.

Campos e padrões:

| Campo | Padrão | Significado |
|---|---:|---|
| enabled | true | Liga a avaliação passiva |
| collector_stale_minutes | 15 | Última recolha bem-sucedida atrasada |
| host_stale_minutes | 5 | Telemetria do S7 antiga |
| database_free_gib_warning | 2 | Alerta de reserva em GiB no volume |
| database_free_gib_critical | 1 | Reserva crítica (menor que aviso) |
| process_rss_mb_warning | 250 | RSS da aplicação com leitura recente |
| sqlite_growth_mb_day_warning | 250 | Taxa extrapolada só após >=6h |
| change_window_minutes | 90 | Janela de mudanças observadas |
| change_sources | 6 fontes | Quais políticas geram aviso informativo |

Regra padrão de mudanças: firewall IPv4/IPv6, acesso WAN, filtragem MAC,
WPS e partilha de ficheiros. UPnP e DHCP não geram alarme de mudança por
padrão devido à variabilidade normal. É possível optar por outras fontes
permitidas no validador, sem afetar polling.

Validação estrita: tipos numéricos, limites, fontes permitidas, lista sem
duplicados e reserva crítica inferior ao aviso. Erro no JSON ou ficheiro
inacessível gera **`invalid_file_disabled`** e desativa os alertas locais.
Não substituir por regras padrão silenciosamente. Dados brutos nunca entram
no alerta; só código da fonte e timestamp observado.

## 3. Contrato da API

`GET /api/router/operations` devolve:

```json
{
  "health": {
    "processRssMB": null,
    "apiP95Ms": null,
    "collectorSuccessAgeMinutes": null,
    "collectorState": "not_started",
    "databaseMB": null,
    "walMB": null,
    "volumeFreeGiB": null,
    "growthMBPerDay": null
  },
  "alerts": [],
  "rulesSource": "defaults",
  "rules": {},
  "history": {"points": [], "truncated": false, "metrics": []}
}
```

Exemplo de estrutura, **não** uma amostra real. O endpoint só faz consultas
de leitura, inclusive usa conexão SQLite `mode=ro` para dados opcionais.
Não publica caminhos de ficheiros, IP/MAC, nomes, configuração Huawei,
tokens, logs completos ou credenciais. Sem persistência de estados de
acknowledgement, disparos e notificações. Se não estiver isolado em LAN/VPN,
rever `SECURITY.md` antes de expor o painel: as **outras APIs existentes**
ainda podem conter dados identificadores da LAN.

### Tratamento conservador de lacunas e regras desligadas

A configuração `"enabled": false` desativa **somente os alertas**, não a
recolha passiva de métricas nem os cálculos de crescimento baseados no histórico.
A taxa `growthMBPerDay` continua visível quando existirem pelo menos seis horas
de amostras válidas, acompanhada por `growthSampleAgeMinutes` (idade da última
medição arquivada). Um alerta **novo** de crescimento só é emitido se a leitura
atual do host **e** a amostra mais recente do arquivo estiverem frescas.

Se uma linha do arquivo histórico tiver JSON inválido, o ponto continua
representado na linha temporal com `status: "unavailable"` e valores `null`.
Isso impede tanto o desaparecimento completo do gráfico quanto uma linha
enganadora atravessando a amostra corrompida. Não há reparação, eliminação nem
reescrita automática do arquivo.

A consulta de alterações aplica a seleção de fontes configuradas e o filtro
de observações sem lacunas **antes** de limitar a janela a 40 alterações; eventos
frequentes de fontes não monitorizadas (como UPnP) não ocultam uma alteração
recente de uma fonte explicitamente monitorizada.

No painel, regras desativadas ou telemetria incompleta recebem estado visual
de atenção, nunca o indicador verde de saúde. Em falhas consecutivas da API,
apenas um aviso de leitura desatualizada permanece visível.

## 4. QA, desempenho e publicação

```sh
python -m unittest discover -s tests -v
node tests/test_observability_view.cjs
node tests/browser_smoke.cjs
INVENTORY_SMOKE=1 node tests/browser_smoke.cjs
```

Os testes usam dados sintéticos e validam limiares, config inválida, dados
stale, ausência de microSD, diferenças de configuração com lacuna, histórico
completo, não mutação de SQLite via consulta, endpoint e interface desktop/
móvel. Também verificam que conteúdo malicioso de nomes da LAN é tratado
como texto.

**Para produção no Galaxy S7**: confirmar CI; backup do banco e código;
validar restauração em cópia e espaço livre; implantar apenas depois de
autorização; observar RSS/CPU e latência com 1 e 4 clientes, comparar antes/
depois; testar queda de recolha e ausência de uma fonte com fixtures sem
desmontar o microSD de produção; manter rollback do código anterior. Esta
entrega não executa essas etapas. Os dados históricos brutos continuam no
lugar; não há migração SQLite.
