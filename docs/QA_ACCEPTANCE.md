# QA e aceite — Network Observatory (#1–#4)

**Data:** 24/10/2026 · **escopo:** checkout público sanitizado, sem deploy, sondas, interrupção do router ou acesso ao Samsung S7 real.

## Implementação

| Issue | Alteração implementada | Evidência automatizada | Pendência externa |
|---|---|---|---|
| #1 Históricos | Home usa `/api/v1/overview?period=24h&view=summary`; leitura compacta de observações reais por bucket, contagem/cobertura exatas, até 3 eventos. Histórico completo e exportação permanecem nas rotas antigas. Cache por revisão (MAX IDs em SQLite), TTL 20s/até 12 bundles, chamadas simultâneas coalescidas por chave, até 2 consultas distintas no SQLite. S7: cache invalidado no sucesso de gravação, até 56 séries, 2 leitores máximos | `test_optimizations.py`, `test_historian.py`, `test_host.py`, `bench_histories.py` | Desempenho LAN e concorrência real em microSD, EXPLAIN QUERY PLAN com volume de produção sob autorização |
| #2 Home progressiva | Status, resumo e inventário carregados em paralelo, publicados individualmente; falha de uma fonte não esconde as demais. Estado loading/ready/empty/error/stale por recurso com aria-busy, aviso persistente e retry local | `browser_smoke.cjs` (atraso, HTTP 500, retry, inventário []); testes Python | Fluxo via toque/teclado, latência em Android 8 |
| #3 HTTP | ETag SHA-256, Last-Modified, Vary e 304 para código CSS/JS/SVG/woff2 não privado até 512 KiB; gzip seletivo em memória (nível 5, apenas quando economiza >=10%, arquivo >=1KiB). Cache-Control privado com revalidação, **nunca public/immutable** | `test_optimizations.py`: 200, 304, HEAD, gzip, q=0, troca real de conteúdo, CSS/JS/S7 estáticos, HTML/JSON/imagem/Vault e API sem cache | CPU/RAM/latência com 1/4 clientes; testar versões e proxy de produção |
| #4 Painel histórico | Período, legenda, título e estado aria-busy mudam antes da resposta; cancela período fechado/obsoleto e compartilha bundle idêntico, reutiliza cache de 20s, erro/vazio/retry, bloqueia exportação até payload válido, Escape restaura foco | `browser_smoke.cjs`: legenda correta, 24h→7d→1y, erro e retry, cache e foco | Toque, screen reader e reduced-motion no aparelho físico |

## Medições *sintéticas* reproduzíveis

Comando:

```bash
python tools/bench_histories.py --samples-per-day 30
```

GitHub Actions (Linux/Python 3.12), 900 amostras Huawei fictícias + 900 sondas, 1/7/30 dias disponíveis na fixture, quatro clientes concorrentes e amostras frias e quentes:

| Período | JSON resumo (bytes) | JSON completo (bytes) | Redução no JSON | Resumo cold / completo cold |
|---|---:|---:|---:|---:|
| 24h | 18.273 | 66.716 | 72,61% | 2,616 / 3,618 ms |
| 7d | 57.860 | 452.650 | 87,22% | 3,795 / 11,514 ms |
| 30d | 57.900 | 777.850 | 92,56% | 4,785 / 35,650 ms |

**Não extrapolar esses tempos para a LAN/S7.** O mesmo benchmark imprime ambiente, medianas de warm cache, amostras com 4 consumidores e tamanho de payload. Não se mediram uso real do cartão, pico de RAM do S7, carga dos serviços, p95 de rede, INP, LCP ou FPS. Metas de produção (resumo cache <=250ms, miss >=50% mais barato, código repetido >=90% menor, compressão >=50%, INP <=200ms) continuam **pendentes** de verificação física.

## Garantias e limites

- Os dados completos continuam em SQLite no microSD; o cache novo é volátil em RAM e limitado. Não existe service worker, cache persistente no interno ou mudança da coleta/auth do router.
- Resposta `view=summary` inclui `summary.sampled: true` e `series_semantics`: cada minigráfico contém observações **originais reais** escolhidas por janela, não valores interpolados nem extremos garantidos. Para min/max, médias e exportação, use `view=full` (padrão) ou exportações.
- A data da coleta e a janela são as que vieram dos registros; TTL não transforma observação antiga em leitura atual.
- Revalidação e gzip HTTP são **somente** para código confiável nos namespaces públicos Router/S7; HTML, endpoints JSON, imagens não classificadas, documentos privados e **todos** os conteúdos `/valt/` permanecem `no-store`. O código do Vault poderá ganhar estratégia específica depois de separar artefactos genuinamente públicos de índices personalizados.
- A versão S7 embutida em `app/static/s7/` é uma cópia independente. Integrar alterações da PR do repositório `s7-edge-observatory` exige sincronização/revisão posterior; **não copiar manualmente dados privados nem fazer deploy implícito**.

## Homologação real — somente com autorização

- [ ] Confirmar diferenças entre o commit implantado e o checkout público antes de qualquer atualização, inclusive JS do S7 integrado.
- [ ] Backup e restauro comprovados no microSD; checar >=2 GiB livres no interno; medir tamanho dos bancos/WAL e espaço disponível.
- [ ] Comparar 1d, 7d, 30d em cache frio/quente, com 1/4 clientes LAN, mantendo distribuição de sensores equivalente; recolher p50, p95, dispersão, bytes, CPU/RAM do processo, SQLite EXPLAIN, busy/lock, leitura no cartão, eventual jitter da coleta.
- [ ] Comparar versão anterior e proposta com os mesmos parâmetros; validar metas de payload/custo do miss/latência de snapshot, sem afirmar números do benchmark sintético como se fossem do aparelho.
- [ ] Validar Router/S7/Vault via navegador desktop e Android 8: versão correta após 304, gzip, leitura privada não cacheada, dados frescos e sem segurança enfraquecida.
- [ ] Provocar delays, falhas 500 e desconexões apenas em fixture de homologação, não desligar nem modificar router/serviço real; repetir período rápido e inspeção/teclado/aba oculta.
- [ ] Auditar acessibilidade, redução de movimento, foco, INP, LCP, long tasks >50ms e eventuais quedas de FPS em dispositivo físico.
- [ ] Rever permissões/rede antes de abrir o servidor fora de loopback: APIs GET não têm autenticação nativa, manter autenticação/TLS na borda.
