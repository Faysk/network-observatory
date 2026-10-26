# Network Observatory

Dashboard local de rede com API Python, histórico SQLite, inventário e integração opcional de leitura com router Huawei. Inclui o backend de telemetria do host e uma cópia integrada do painel S7.

## Configuração e diagnóstico do router

O painel integra 28 fontes adicionais: Wi-Fi, clientes/DHCP, IPv6, UPnP, políticas, NAT e serviços USB/voz, com qualidade por fonte, histórico de diferenças, comparação antes/depois e arquivo paginado. Falha de autenticação deixa o coletor bloqueado e mantém o painel disponível. [Dados, APIs, cadência, privacidade e limites](docs/ROUTER_OBSERVABILITY.md).

## Executar

Python 3.11 ou superior, sem dependências Python externas:

```sh
python -m app.server --host 127.0.0.1 --port 8767
```

Abra http://127.0.0.1:8767/router/ . O host fica em `/s7/`. Sem uma fonte autenticada, métricas do router permanecem sem dados; o servidor pode executar sondas TCP configuradas. A integração não deve ser usada sem autorização do administrador da rede.

O adaptador opcional `python -m app.adapters.huawei_b7 --help` foi desenvolvido para HG8247B7-8N / V5R024C00S114. Compatibilidade com outros equipamentos não é presumida. Credenciais devem ficar somente no dispositivo operador, em arquivo local ignorado pelo Git. Não existe credencial pronta no projeto.

## Organização

- `app/server.py`: rotas e API; `app/core.py`: coleta e histórico.
- `app/host_telemetry.py` e `app/host_sources.py`: telemetria local do host/Android com fontes opcionais.
- `app/static/`: interfaces, Workspace e acabamento compartilhado.
- `tests/fixtures/`: exemplos sintéticos, sem respostas privadas capturadas.
- O Vault é separado: https://github.com/Faysk/docs-vault . Para a integração `/valt/`, disponibilize seu frontend em `sites/valt/` local, ignorado pelo Git; mantenha dados reais privados.
- O painel S7 independente: https://github.com/Faysk/s7-edge-observatory .

## Otimizações de histórico e HTTP — issues #1 a #4

- `GET /api/v1/overview?period=24h&view=summary`: **resumo da home**. Cobertura e contagem de amostras exatas, minigráficos com observações reais limitadas por janela, até três eventos. Não substitui médias/extremos; consulte `view=full` (o padrão original) para históricos detalhados.
- `GET /api/v1/overview?period=24h`: formato completo compatível; cache em RAM, TTL de 20 s, 12 entradas e invalidação por nova coleta (IDs máximos em SQLite).
- Históricos S7 por métrica/período: solicitações simultâneas idênticas calculadas uma vez e leituras simultâneas do SQLite limitadas a duas, com invalidação após gravar no microSD.
- HTTP: JS/CSS/SVG/woff2 de código público (até 512 KiB) usam ETag, Last-Modified e revalidação 304; gzip seletivo para JS/CSS/SVG suficientemente compressíveis. **Sem cache público, immutable ou service worker**. HTML, API, JSON, conteúdo privado e `/valt/` continuam `no-store`.
- Home carrega status, resumo e inventário em paralelo com erros/retry por secção. O painel atualiza imediatamente período/legenda, cancela consultas obsoletas e só habilita exportação para bundle válido.

As otimizações foram publicadas e verificadas em LAN em 25/10/2026; o inventário integrado segue a homologação descrita em `docs/RELEASE_INVENTORY.md`. Consulte [o relatório de aceite](docs/QA_ACCEPTANCE.md): benchmarks sintéticos e testes automatizados **não** substituem medições de LAN, carga do microSD, validação no Android 8 ou sincronização futura com o frontend S7 independente.
## Identificação MAC / OUI (issue #7)

O inventário em `GET /api/router/clients` agora expõe um campo de **evidências `identity`** separado dos dados reportados pelo Huawei: endereço normalizado, tipo de MAC (global/local/multicast/etc.), fornecedor do **bloco de endereço** IEEE quando disponível, versão/fonte. O MAC local **não é prova** de randomização; OUI global **não identifica modelo nem aparelho físico**. Nenhuma amostra histórica ou exportação é modificada.

**Importante:** a base IEEE não vem incluída no checkout. Para resolver fornecedores offline, o operador deve importar os CSVs oficiais **fora do dispositivo**, gerar `oui-assignments.tsv` e colocar no **mesmo diretório de `FNO_DB`**, no microSD para S7. Sem arquivo: `oui_vendor=null`, sem adivinhação, e sem consulta de MAC a serviço externo.

Veja [manual de instalação, limites e QA](docs/DEVICE_IDENTITY_OUI.md). Há testes sintéticos em `tests/test_device_identity.py`.

## Classificação automática conservadora (issue #8)

`GET /api/router/clients` passa a devolver `classification` (categoria, família de plataforma, sugestão de nome, confiança qualitativa, evidências, conflitos, versão das regras) em paralelo ao `identity` MAC/OUI e aos dados originais. O motor é determinístico, sem IA ou coleta adicional. **Quando `android-dhcp` está explicitamente reportado, mas não há categoria mais específica, a interface pode usar `Equipamento Android` (formato físico desconhecido). `Predator` precisa de contexto adicional da assinatura DHCP Microsoft ou identificação explícita da família Acer para sugerir `Computador`; isso não confirma notebook ou Windows.** `MSFT 5.0`, `android-dhcp`, o tipo Wi-Fi/LAN e a marca do OUI **não** comprovam um modelo ou plataforma; conflitos e desconhecidos são representados honestamente.

[Taxonomia, precedências, evidências e limites](docs/DEVICE_CLASSIFIER.md). A experiência visual está reservada para as issues #9 e #10.

## Ícones locais por categoria (issue #9)

O inventário da home, explorador completo e topo do dossiê usam os mesmos ícones do sprite **local** `app/static/device-icons.svg` para 15 categorias, com fallback `unknown`. As categorias amplas `computer` e `android_device` comunicam evidências sem presumir modelo ou formato físico. Ícones geométricos originais, sem dependências/brands/CDN ou fontes externas. A interface mostra categoria **sem sufixos de incerteza**, plataforma quando sustentada e dados técnicos com proveniência no dossiê. Quando o Huawei só reporta MAC ou nomes técnicos como `wlan0`, o título torna-se legível (`Dispositivo Wi-Fi não identificado`, `Equipamento Android` ou `PlayStation 5` quando houver tipo PS5 reportado), mantendo o endereço MAC original acessível na pesquisa e no dossiê. Os nomes e categorias da lista são curtos, sem o sufixo «provável». A inferência permanece identificada nos campos de confiança, evidências e «Categoria sugerida» do dossiê. Nomes definidos manualmente continuam prioritários. Estado e significado não dependem só da cor. Mantida compatibilidade com categorias desconhecidas e navegadores de viewport estreita.

Testes em `tests/test_device_icons.py` verificam SVG, cobertura do catálogo, fallback, resposta HTTP e acessibilidade básica. A reorganização completa, filtros/paginação/polling estável pertencem à issue #10.

## Validação

```sh
python -m unittest discover -s tests -v
python tools/bench_histories.py --samples-per-day 30
python -m unittest tests.test_device_identity -v
python -m unittest tests.test_device_classifier -v
python -m unittest tests.test_device_icons -v
node --check app/static/devices.js
node tests/test_s7_ui.cjs
node --check app/static/app.js
node tests/browser_smoke.cjs # requer Chrome ou Chromium
```

## Limites e privacidade

GET não tem autenticação; o padrão é loopback. Não exponha este servidor na Internet sem uma camada adequada de autenticação e TLS. Escritas exigem `FNO_INGEST_TOKEN`; configure um valor aleatório longo somente no ambiente de execução. Consultas autenticadas ao router devem respeitar intervalo mínimo de 60 segundos.

O repositório contém código e fixtures sintéticas. Bancos, inventário real, registros, credenciais, capturas e backups foram excluídos. Null representa dado desconhecido; bytes acumulados não equivalem a velocidade nem consumo de uma janela. Sensores brutos não recebem unidades presumidas. Para Android/S7, preserve pelo menos 2 GiB disponíveis no interno; dados persistentes devem ficar no SD. A política não é uma quota automática.

Licença MIT conforme `LICENSE`.

Identificação da banda Wi-Fi por dispositivo, histórico de associação observada, limites da fonte e reprojeção do arquivo: [Wi-Fi por banda](docs/WIFI_BANDS.md).

Personalização e associações explícitas: [CLI administrativa local](docs/DEVICE_PREFERENCES.md).

Consultas de gráficos compactas no microSD, reconstrução segura e espelho S7: [read models](docs/READ_MODELS.md).

Matriz individual de contratos e desempenho, relatórios e comparação por versão: [guia de testes de performance](docs/PERFORMANCE_TESTS.md).
