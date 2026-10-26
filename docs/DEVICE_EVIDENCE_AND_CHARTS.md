# Identificação e gráficos: evidência em vez de aproximação visual

## Workspace S7

Arquivos compartilhados são servidos na raiz: `/workspace.css`, `/finish.css`, `/finish.js` e `/loading.css`. Referências relativas dentro de `/s7/` procuravam arquivos inexistentes e deixavam o seletor sem estilo. A versão independente e a integrada mantêm hashes dos assets; o teste HTTP verifica as URLs usadas pelo HTML.

## Identificação

O fabricante do bloco MAC estava indisponível porque não havia uma base carregada. O download IEEE pode recusar acesso (418). A ferramenta `tools/import_manuf.py` compila o arquivo publicado pelo próprio Wireshark para o formato local. Preserva a procedência `wireshark_manuf`, diferente de um download IEEE atual. Nenhum inventário ou MAC individual é enviado para consulta externa. A base fica no microSD e é lida em memória, sem consultas HTTP durante navegação. Atualização é manual; o Wireshark pede no máximo uma atualização semanal.

```sh
python tools/import_manuf.py --input /arquivo/manuf --output /microSD/dados/oui-assignments.tsv
```

A [base pública do Wireshark](https://www.wireshark.org/download/automated/data/manuf) tem prefixos de 24/28/36 bits; [a IEEE descreve essas atribuições](https://standards.ieee.org/products-programs/regauth/). O titular pode ser o fabricante do módulo, não o fabricante do aparelho. MAC local/multicast/inválido continua sem consulta de fabricante.

Regras específicas de família são sugestões: Nintendo é console provável, sem afirmar Switch/modelo; Intel + nome não genérico + assinatura DHCP Microsoft sugere computador, sem provar Windows ou formato notebook/desktop. Nome de família Galaxy legado com contexto DHCP Android pode sugerir smartphone. Fabricante isolado de módulo genérico não determina categoria.

Quando o nome atual some, procuramos até oito observações nomeadas dos últimos sete dias para esse MAC ativo, usando índice existente. Cache reconstruível em RAM: cinco minutos, 32 entradas, 256 KiB, um leitor. Não altera nomes no arquivo original nem cria associações entre MACs. Identificação histórica mostra origem, data e confiança baixa; nomes atuais e personalização prevalecem; conflitos permanecem desconhecidos. Modelos genéricos como MiTV são famílias, não identificação física certificada.

## WAN

A curva não deve calcular médias de contadores que voltam ao início: uma média pode nem corresponder a uma leitura real. A prévia WAN usa a última hora com observações originais. O histórico completo limita a 361 pontos selecionados e mantém gerações de contador por direção: uma queda ou lacuna observada em qualquer amostra intermediária interrompe o traçado, mesmo se o ponto selecionado depois for maior que o anterior. A média/min/max legada continua no objeto estatístico; o traçado de contadores usa `counter_series`.

As barras verticais de mínimo/máximo não são desenhadas para contadores WAN. Não se suavizam nem corrigem voltas presumidas. Largura/reset/múltiplas voltas continuam sem validação; a curva não representa Mbps nem consumo.

O inspetor busca a leitura mais próxima em toda a área do gráfico e informa seu horário e distância do cursor. Não exige acertar um ponto e não interpola valores em lacunas.

## Carregamento

Detalhes de Router/dispositivo exibem estrutura de gráfico, métricas, leituras e eventos enquanto carregam. Cada região informa `aria-busy`, encerra seu estado em sucesso/erro e não mostra valores de outro período como atuais. Preferências de movimento reduzido/pausa são respeitadas.

## Ethernet negotiated speed

The inventory column joins an online device to exactly one explicit LAN port and displays its current negotiated speed from the existing status resource. Both readings must be fresh (180 seconds). Ambiguous, stale, offline, down or unreported links show unavailable. Duplicate representations of the same port are deduplicated. No new polling is added. The value describes the router port, including an upstream switch link; it does not certify the end-device cable or Internet throughput. 10/100 Mb/s can be a normal device limit or a cable/configuration limitation, not a diagnosis.
