# Network Observatory

Dashboard local de rede com API Python, histórico SQLite, inventário e integração opcional de leitura com router Huawei. Inclui o backend de telemetria do host e uma cópia integrada do painel S7.

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

## Identificação MAC/OUI (opcional)\n\nO inventário pode acrescentar `identity` com tipo MAC e fabricante OUI registrado, quando conhecido. Não garante aparelho, OS ou dono. Sem arquivo local OUI, fabricante permanece desconhecido. Veja [instruções offline e privacidade](docs/MAC_OUI.md).\n\n## Validação

```sh
python -m unittest discover -s tests -v
node tests/test_s7_ui.cjs
node --check app/static/app.js
```

## Limites e privacidade

GET não tem autenticação; o padrão é loopback. Não exponha este servidor na Internet sem uma camada adequada de autenticação e TLS. Escritas exigem `FNO_INGEST_TOKEN`; configure um valor aleatório longo somente no ambiente de execução. Consultas autenticadas ao router devem respeitar intervalo mínimo de 60 segundos.

O repositório contém código e fixtures sintéticas. Bancos, inventário real, registros, credenciais, capturas e backups foram excluídos. Null representa dado desconhecido; bytes acumulados não equivalem a velocidade nem consumo de uma janela. Sensores brutos não recebem unidades presumidas. Para Android/S7, preserve pelo menos 2 GiB disponíveis no interno; dados persistentes devem ficar no SD. A política não é uma quota automática.

Licença MIT conforme `LICENSE`.
