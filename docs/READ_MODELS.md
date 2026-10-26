# Consultas compactas, sem perder o arquivo original

## Problema e estratégia

O histórico S7 extraía oito métricas de JSONs completos a cada consulta; dossiês de clientes liam muitas páginas intercaladas do microSD. Uma consulta CPU7d observada em15,58s ultrapassou o timeout15s do frontend; o diagnóstico registrou dossiês6–9s. Cache RAM acelera repetição, mas não resolve a primeira leitura nem o reinício.

`app/read_models.py` mantém projeções exatas por observação no mesmo SQLite e microSD do original:

- `host_chart_points`: timestamp e oito valores de gráficos, sem JSON de sensores brutos.
- `client_chart_points`: chave primária(mac,ts,id), WITHOUT ROWID, com o subconjunto exato usado por gráfico/sessões/identidade; páginas próximas para o mesmo MAC.
- `router_chart_points`: chave(ts,id), métricas usadas pelo histórico completo do Router, sem todos os detalhes do snapshot.

Não são médias pré-calculadas nem amostragem destrutiva. A janela, os buckets, médias/extremos, zero/null, estados, gaps e sessões continuam calculados com as mesmas observações. O payload completo, arquivo de sensores e exportações não são substituídos. Novos dados e projeções são gravados na mesma transação, com savepoint para a parte reconstruível. Uma falha da projeção reverte somente essa parte e preserva a observação bruta; a consulta usa o original ausente da projeção. Se SQLite reverteu a transação inteira por falta de espaço, o erro é reportado e não se anuncia gravação bem-sucedida. O diagnóstico do host expõe chartProjectionError e o serviço registra aviso sem dados privados.

## Migração e reconstrução

```sh
python tools/build_read_models.py --router-db /volume/sd/observatory.db --host-db /volume/sd/host-telemetry.db --batch 128
```

A ferramenta aceita somente arquivos existentes (`mode=rw`), não cria pastas, não inicia coletor nem consulta aparelhos. Lê1–128registros de cada fonte por lote em RAM. Agrupa commits até aproximadamente2048registros ou2s por transação (um lote lento pode exceder esse orçamento temporal), cedendo entre transações para o coletor. Repetição é idempotente e pode retomar uma migração interrompida, incluindo registros históricos inseridos fora de ordem.

Enquanto há dados não projetados, a consulta mescla projeções e originais ainda ausentes, sem duplicar nem omitir linhas. Triggers invalidam a projeção quando o original é atualizado/apagado; os valores corretos reaparecem pelo fallback e podem ser reconstruídos. Leituras não criam ou migram schema. Migração deve ocorrer com backup consistente e espaço para projeção+WAL/intermediários no microSD. O banco do host passa a WAL com synchronous=FULL, permitindo que leitores usem um snapshot consistente durante a escrita sem reduzir a durabilidade. Nenhum spill para interno ou disco de rede.

## Verificação e rollback

Testes sintéticos comparam os resultados completos durante migração parcial/total, zero/null, divisão por zero, alterações/remoções, gaps, identidade, idempotência, falta de SD e rollback de falha de escrita. Na homologação, comparar o código anterior e o novo sobre cópias consistentes reais, mesma janela, SHA-256 dos registros brutos antes/depois e cache RAM novo por rodada. Não usar `drop_caches`/root nem afirmar cache físico frio sem evidência.

Rollback de código ignora as tabelas extras, preservando novas coletas. Não restaurar banco antigo sobre produção. As projeções podem ser reconstruídas; removê-las deve incluir seus triggers e seguir procedimento explícito com serviço parado/backup. Não apagar dados pessoais, amostras originais ou tabelas desconhecidas para liberar espaço.

## Espelho do S7 e boot

A cópia S7 integrada agora corresponde à versão pública independente113c69d. `docs/INTEGRATED_S7.json` registra origem e hashes LF dos três arquivos; teste de regressão detecta divergência. Não copiar índices privados ou sobrescrever arquivos locais automaticamente.

Termux:Boot0.8.1 oficial foi instalado no aparelho após conferir checksum de release e certificado igual ao Termux existente. O operador abriu o app. O bootstrap mínimo no armazenamento privado Android é necessário ao receptor de boot; aplicação, bancos e logs ficam no SD. A presença do script significa configuração, não homologação após reinício; `boot-validation.json` somente é registrado após teste físico e reconexão sem abrir Termux manualmente. O agente ADB de CPU continua sujeito à reativação após reboot, conforme seu atalho; não contornar permissões.

## OUI

A base pública IEEE permanece dependência separada. Downloads oficiais retornaram418 e o navegador reportou ERR_BLOCKED_BY_CLIENT nesta sessão; nenhuma proteção foi alterada. O lookup offline funciona com arquivo fornecido pelo operador, mas fornecedor indisponível permanece desconhecido. Não usar base de procedência/licença incerta para preencher categorias.


## Evitar trabalho repetido no Router

Dossiês compartilham a mesma consulta em voo e um cache RAM de20s, até8entradas e2MiB de JSON contabilizado (overhead dos objetos Python é maior; medir RSS real). No máximo2cálculos diferentes leem o SD simultaneamente. Erros não ficam em cache; resultados maiores não são retidos; cópias isolam consumidores. Triggers de versão invalidam também UPDATE/DELETE e backfills, sem depender só do maiorID. A leitura de cada bundle usa uma transação consistente. O cache não muda o arquivo nem a cadência do coletor.

## Ensaio no aparelho sobre cópias consistentes

No S7/microSD, com mesmas janelas e resultados completos exatamente iguais: CPU7d de3589ms para25,7ms; overview24h1153→305ms e7d3346→840ms; dossiê24h148→132ms e7d432→375ms. Rodada única, com cache físico não controlado; não confundir com SLA ou cold boot. A igualdade SHA-256 dos registros brutos dos cinco conjuntos foi conferida. Projeções acrescentaram~25MiB ao banco Router e280KiB ao host nesse volume. O ganho do dossiê frio foi menor que o dos gráficos S7; a camada de chamadas compartilhadas e cache limitado trata repetição/concorrência, cuja medição HTTP será feita após deploy.


## Publicação LAN e chamadas simultâneas — 26/10/2026

Versão19d9211 publicada após backup consistente do banco Router/host e código. Migração online:78192observações Router em102,61s,3244host em10,22s, mais um pequeno delta na troca; coletor manteve sua cadência e o intervalo de autenticação foi respeitado no restart. Os hashes SHA-256 de todos os registros anteriores das cinco tabelas foram comparados com os backups e permaneceram idênticos.24arquivos do manifesto conferidos;171arquivos privados de configuração/Vault e o servidor privado preservados.

Medição HTTP real emLAN, primeiroGET antes e cincoGETs depois:

|Consulta|Antes (primeiro observado)|Depois (primeiro observado)|Depois (repetições)|
|---|---:|---:|---:|
|Dossiê24h|2478ms|516ms|178–224ms|
|Dossiê7d|7681ms|586ms|91–127ms|
|CPU S7 7d|19883ms|93ms|26–45ms|
|Overview completo7d|15185ms|1064ms|109–151ms|

4GETs simultâneos: dossiê7d378–559ms eCPU7d25–53ms. Todos200. Rodadas não têm cache físico/concorrência idênticos; antes houve outras leituras de homologação no SD e o arquivo continua recebendo dados. Os números mostram a experiência observada, não garantem fator de ganho universal; o ensaio sobre cópias fixas acima separa o ganho do plano de consulta. Não foram calculados p95/INP/FPS com estas amostras.

111testes Python locais/CI aprovados e24específicos no S7. Navegação real após publicar: resumo/inventárioRouter prontos, dossiê com gráfico/exportação após loading, dois gráficos7dS7 prontos sem retry ou busy. RSS de amostra~37,8MiB, gravação anterior do host306ms, semerro de histórico/projeção. Boot configurado e app aberto; teste físico ainda pendente à hora deste registro.
