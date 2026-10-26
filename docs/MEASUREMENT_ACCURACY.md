# Auditoria de exibição, unidades e cálculos

## Cobertura temporal e cadência

`coverage_percent` agora mede a união dos intervalos `[coleta, coleta+180s]`, recortados à janela solicitada. Usa a mesma tolerância de leitura recente da interface; não é disponibilidade de Internet, ping nem percentual de registros recuperados. Duplicatas não aumentam tempo coberto, lacunas continuam descobertas e há contexto de até 180 s anterior ao início. A média dos intervalos positivos entre coletas na janela é apresentada separadamente, incluindo pausas longas. Uma coleta a cada 67 s pode cobrir toda a janela sem atingir a meta nominal de 60 s.

`sample_count`, `expected_count` (meta nominal a cada 60 s), `nominal_sample_percent` e segundos cobertos continuam explícitos. Não ajustamos o denominador pela mediana observada: isso poderia esconder uma coleta que ficou muito lenta. A cadência do coletor não foi acelerada, e os registros antigos não foram alterados.

## Matriz auditada

| Família | Cálculo / significado | Verificação e limites |
|---|---|---|
| Router CPU e RAM | Percentuais reportados, 0–100 | Parser validado; leitura atual exige fonte recente. Não recalcula RAM sem fonte total/disponível. |
| Router uptime / óptica | Segundos; dBm, °C do transceiver, mV e mA conforme campos do parser | Não confunde temperatura óptica com CPU. Estado PON não equivale a Internet. |
| WAN RX/TX | Inteiros acumulados originais, convertidos para GiB somente para exibição | Quedas quebram a curva. Largura, resets e múltiplas voltas não permitem validar Mbps nem consumo; não soma 4 GiB presumidos. |
| TCP gateway / exterior | Tempo de conexão TCP em ms | Não chama de ping, perda ICMP, DNS ou velocidade. Leituras ausentes não viram zero. |
| Wi-Fi / PHY / RSSI | PHY em Mbit/s, RSSI em dBm reportados pelo AP | Não são tráfego por cliente. SNR só quando reportado. |
| Presença / sessões | Percentual de amostras conhecidas; segmentos observados com limite de lacuna | Não infere sessões exatas, banda por aparelho ou desconexão só por ausência da tabela. |
| Estatísticas Router | Média aritmética das observações, min/max, contagem por métrica | Não é média ponderada no tempo. Prévia usa uma observação original por intervalo; histórico detalhado agrega com envelope e lacunas. |
| CPU S7 / núcleos | Delta de contadores; ocioso inclui idle+iowait; guest não contado novamente | Primeira leitura, reset ou janela inválida: null. Agente tem janela/idade próprias; não é uso contínuo de todo o período. Offline só quando confirmado. |
| CPU do processo | Delta de tempo CPU / tempo monotônico ×100 | 100% = um núcleo; pode superar 100% com vários núcleos. |
| RAM S7 | MemTotal − MemAvailable; KiB→MiB | API legada `totalMB/usedMB` representa MiB. Disponível, usado e total podem ser conferidos na mesma amostra. |
| Cache / swap / zram | Cache e swap usados a partir dos campos do kernel | Cached/Slab/Available podem se sobrepor, não são fatias somáveis. `swapMB` legado é capacidade; `swapUsedMB` é uso. Zram preserva unidades nativas. |
| Armazenamento | Usado=blocks−bfree; disponível=bavail×frsize; GiB binários | Percentual disponível usa bavail, sem contar espaço reservado ao sistema. Volume interno selecionado por id, não posição. Alerta interno em 2 GiB, sem prometer limpeza automática. |
| Rede S7 | Delta de bytes ×8 / segundos reais /10^6 | Cada direção valida reset separadamente; janela >180 s ou mudança de interface não gera taxa. Contadores Linux são do host, não da rede inteira. |
| Bateria | Capacidade %, temp/10 °C, voltage_now/1000 mV | Corrente Samsung mantém valor/unidade brutos sem inferir sinal/escala. Sensores não disponíveis não são simulados. |
| Load / GPU / devfreq / térmicos | Load 1/5/15 min é número de tarefas; drivers ficam brutos | Não converte load em %, GPU em MHz ou zona térmica desconhecida em temperatura CPU. |
| Disco / processo / PSI | Índices de diskstats e contadores de I/O; status em KiB/contagens | Não atribui I/O do kernel ao SQLite. PSI e campos não interpretados mantêm metadados de unidade/fonte. |
| API / coleta / commit | p95 pelo nearest-rank `ceil(.95*n)-1` | Tempos de API Router são do servidor e excluem /api/host; não incluem rede. Gravação do hardware é transação anterior, identificada como tal. |
| Precisão de inteiros | JSON bruto preservado no banco; inteiros além de 2^53−1 chegam ao JS como strings decimais exatas | Strings JSON e números fracionários permanecem intactos. Valores escalados/arredondados não devem ser tratados como contadores exatos. |

## Projeção do hardware v2

A expressão de armazenamento encontra `id=internal`; ausência desse volume resulta em null. A coluna `projection_version` distingue projeções antigas. Consultas leem a origem bruta para linhas antigas até a reconstrução em lotes no próprio microSD. Nenhuma amostra bruta é apagada ou reescrita. Limite superior da consulta impede exibir pontos do arquivo com timestamp futuro após correção do relógio. O cursor do arquivo permanece monotônico e os originais continuam acessíveis.

## Repetir a auditoria

`python -m unittest discover -s tests -v` cobre fórmulas e casos de borda com fixtures inventadas. `node tests/test_sheet_requests.cjs` cobre continuidade e precisão JSON; `node tests/test_s7_ui.cjs` cobre apresentação/zero/null e espaço disponível. A matriz de desempenho continua a validar cada métrica/período.

Para uma aplicação real explicitamente autorizada, sem acessar painel do router nem iniciar sensores:

```sh
python tools/audit_measurements.py --allow-live --live-url http://ENDERECO:PORTA --output /pasta/existente/auditoria-nova.json
```

O relatório guarda somente nomes estáticos das verificações e estados pass/fail/unknown, sem payloads, URLs, IPs, MACs ou nomes dos clientes. No Termux exige microSD e reserva interna >=2 GiB. `unknown` é falta de fonte, não aprovação. Esta auditoria confirma contratos, conversões e consistência matemática; não calibra sensores nem certifica unidades proprietárias não documentadas.
