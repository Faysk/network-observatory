# Configuração e diagnóstico — visualização guiada pelos dados

## Problema resolvido
A página do Observatory apresentava 28 fontes Huawei como uma coluna de
`<details>` com tabelas de dezenas de colunas. Era difícil entender a leitura
antes de abrir cada fonte. A nova interface distingue **estado**, **registo**,
**distribuição** e **medição**; nunca substitui o valor bruto por um score
fabricado.

## Navegação

A vista mantém o seletor de grupo e o período de alterações, e acrescenta
pesquisa local por nome, grupo/tipo de fonte e descrição. As fontes aparecem
em cinco grupos temáticos:

1. Rádios e Wi-Fi — configuração, rádios, estações, WPS, MLO, limitações,
   agendamento e rede convidada.
2. Dispositivos e endereçamento — DHCP, identidades, IPs e modos Wi-Fi.
3. Regras e acesso — UPnP, firewall v4/v6, acesso WAN, MAC e NAT.
4. Rede, interfaces e IPv6 — estados IPv6, anúncios, DHCP/DNS e topologia.
5. Serviços e hardware — USB, FTP/SFTP, DLNA, voz e hardware Wi-Fi.

## Camadas visuais

- **4 KPIs gerais:** fontes com leitura atual / total, leituras antigas,
  linhas reportadas nas fontes mais recentes (não clientes únicos) e alterações
  observadas no período (prévia até 500).
- **Fonte fechada:** título, propósito, contagem e qualidade (atual/antiga/
  indisponível), com número de mudanças quando houver.
- **Fonte aberta:** indicadores curados para cada esquema, com unidade e
  interpretação; distribuição categórica proporcional a **contagem de
  registos**, sem misturar métricas diferentes; até 6 registos em cartões
  legíveis; tabela técnica completa opcional.
- **Estações Wi-Fi:** RSSI e SNR em dBm/dB quando reportados; escala de
  localização -100 a -30 dBm com valor numérico. A posição não constitui
  pontuação de saúde. PHY não é throughput.
- **Histórico:** histograma da densidade das *diferenças observadas* no
  período selecionado e lista comparativa antes/depois. O momento da mudança
  real pertence a um intervalo entre leituras, não à hora em que foi observada.
  Se a lista de alterações estiver truncada, o histograma é explicitamente
  rotulado como prévia incompleta.
- **Arquivo:** botão de acesso às observações guardadas por fonte, com
  paginação sob demanda. Os dados originais continuam disponíveis.

## Campos de baixa certeza
- Códigos de firewall, ACL e filtragem MAC **não** são automaticamente
  interpretados como seguros/inseguros; exibidos como campos reportados.
- WPS, MLO, NAT, partilha de ficheiros e acesso WAN representam configuração,
  não confirmação de exposição ou exploração a partir da Internet.
- Limites convidados, largura Wi-Fi configurada e durações/contadores de
  semântica incerta mantêm os avisos de procedência e escala.
- Concessões DHCP não garantem que um cliente esteja online.
- "Não observado" e `null` não viram zero; **0 e falso** são valores válidos.
- Os pequenos gráficos de distribuição mostram proporção de **contagens**,
  não tráfego, tempo online, percentagem de sucesso ou saúde Wi-Fi.
- O histograma de alterações não insere amostras que não existem; não
  representa coleta do aparelho em tempo real.

## Segurança e desempenho
- Apenas altera HTML/CSS/JavaScript e documentação da vista, sem novos
  endpoints, novas leituras do router, mutações, credenciais ou alteração do
  intervalo de 5 minutos.
- Textos reportados do Huawei entram como `textContent`, não HTML
  executável. A pesquisa é local à resposta já recebida.
- Tabelas com mais de três linhas são construídas apenas ao abrir a área
  técnica. Nenhum `canvas` pesado, dependência externa, animação contínua ou
  biblioteca gráfica extra.
- Layout responsivo para 320–1300 px, foco visível, regiões com rótulos
  semânticos e suporte a `prefers-reduced-motion`.

## Verificações
```sh
node tests/test_observability_view.cjs
node --check app/static/observability.js
node tests/browser_smoke.cjs
python -m unittest discover -s tests -v
```

A homologação automatizada em navegador usa fixtures artificiais;
**não representa teste numa conta Huawei real nem no hardware S7**.
Para instalar no S7, é necessário procedimento de backup e validação
separados. Os dados anteriores no SQLite não precisam de migração.


## Nova camada: navegação e tendências verificáveis (PR de acabamento)

A vista abre com seis atalhos (panorama + cinco domínios), cada um exibindo a
quantidade **atual / total** de fontes desse domínio. O seletor de grupo, a
pesquisa e os chips `Todas`, `Com alterações` e `Sem leitura atual`
**ocultam** cartões em vez de destruí-los, preservando gráficos e arquivos
abertos durante uma pesquisa. O filtro de mudanças baseia-se nas diferenças
recebidas na prévia de até 500 entradas; não deve ser descrito como consulta
exhaustiva quando `changes_truncated=true`.

### Gráfico histórico por fonte

`GET /api/router/observability/trend?source=station_details&hours=24&limit=400`

- Fonte obrigatoriamente conhecida (allowlist de 28). Janela: 0–366 dias.
- Consulta SQLite indexada por fonte/tempo, limitada às **400 observações
  cronologicamente mais recentes** do intervalo. Se existirem mais registos,
  retorna `truncated=true`, datas efetivamente representadas e aviso no gráfico.
- Cada ponto contém somente carimbo de data/hora, estado e resumo numérico.
  **Não** retorna MAC, IP, SSID, nomes de clientes ou o corpo bruto das
  configurações; o arquivo original permanece no banco.
- Qualquer fonte pode representar **quantidade de linhas reportadas**.
  A quantidade não é uma contagem de dispositivos físicos nem de serviços
  acessíveis. Para estações, expõe também a média de RSSI e de SNR das
  estações reportadas; para UPnP/WPS/rádios/serviços, o número de linhas
  explicitamente ativadas; para inventário, o número de identidades
  com estado `Online` reportado.
- O gráfico é gerado **sob demanda** em SVG, sem dependências externas;
  indisponibilidade e valores `null` quebram o traçado. Lacunas com mais
  de 15 minutos entre observações também interrompem a linha. Não há
  interpolação, preenchimento sintético nem previsão.
- Os pontos são guardados no SQLite já existente; a API não gera qualquer
  novo dado de recolha.

### Arquivo recente

`GET /api/router/observability/archive/recent?source=upnp&limit=50&before=0`

- Começa pelo instante mais recente, com paginação keyset
  por `(ts,id)`. Lida corretamente com inserções históricas fora de ordem.
- Não substitui a API de arquivo ascendente original nem altera exportações.
- O frontend só constrói a tabela HTML de cada leitura arquivada **quando
  essa leitura é aberta**; não há 50 tabelas grandes criadas de uma vez.
- Respostas de arquivo continuam contendo informações privadas da rede.
  Mantenha a API protegida por isolamento local ou autenticação e TLS
  de um gateway confiável, como descrito em `SECURITY.md`.

### Economia de recursos no S7

- Nenhum gráfico histórico é carregado na inicialização da página; botão
  dedicado consulta **uma fonte por vez**.
- Detalhes completos das 28 fontes são construídos apenas quando o
  respetivo cartão é aberto. A pesquisa e os filtros evitam reconstruir
  os outros cartões e preservam histórico já carregado.
- Mudanças de período feitas durante uma consulta são reexecutadas após
  a consulta pendente, evitando mostrar indefinidamente uma janela antiga.
- Não há alterações no intervalo do coletor Huawei, credenciais, escrita
  do SQLite, retenção, GPIO, root ou firmware do router.
- Dados brutos previamente arquivados continuam intactos: não é necessária
  migração do banco para esta melhoria de apresentação.

### Testes sintéticos adicionais

```bash
python -m unittest tests.test_router_observability -v
python -m unittest tests.test_http -v
node tests/test_observability_view.cjs
node tests/browser_smoke.cjs
```

O teste do navegador usa somente leituras fabricadas de documentação
(`example`, rede de teste `192.0.2.0/24`) e verifica navegação entre
domínios, gráfico com lacunas, arquivo recente, pesquisa preservando
estado, leitura `0`, escaping e largura de 320 px.

**Nenhuma alteração foi feita diretamente ao S7 nem ao Huawei pela PR.**
