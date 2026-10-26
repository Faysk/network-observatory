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
