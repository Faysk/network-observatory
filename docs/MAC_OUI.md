# MAC/OUI offline — issue #7

Os dados da IEEE identificam **titular do bloco de endereço de interface**, não necessariamente fabricante do aparelho, modelo, sistema operativo ou proprietário. O bit U/L ligado significa **MAC administrado localmente**, que pode mas não precisa ser um MAC aleatório. Não fazer lookup OUI quando esse bit está ligado.

A API existente `GET /api/router/clients` inclui a propriedade adicional `identity` em cada cliente, sem mudar campos originais, bancos, observações brutas ou exportações: `mac_type` (`global`, `locally_administered`, `multicast`, `invalid`), `oui_vendor` (string ou null), `oui_prefix_bits` (24/28/36 ou null), `oui_dataset_version` e `sources`. `mac_type=locally_administered` **não afirma** randomização nem fabricante. MAC inválido ou sem atribuição resulta em `null` sem inventar marca.

## Atualização do dataset de modo offline

A versão pública carrega por padrão uma base *vazia* (`app/data/oui.json`) propositalmente: não republicar material IEEE sem validar licença/atribuição. Para preencher na implantação privada, obtenha manualmente o(s) CSV MA-L, MA-M ou MA-S na [IEEE Registration Authority](https://standards.ieee.org/products-programs/regauth/mac/) e execute no computador do operador:

```sh
python tools/import_ieee_oui.py --ma-l /caminho/ma-l.csv --ma-m /caminho/ma-m.csv --ma-s /caminho/ma-s.csv --output /caminho/no/microsd/oui-local.json
FNO_OUI_FILE=/caminho/no/microsd/oui-local.json python -m app.server --host 127.0.0.1 --port 8767
```

O importador aceita um ou mais CSVs, **sem** download de rede. O caminho deve apontar para o microSD, com arquivo de leitura local e fora do Git. A tabela é carregada uma vez em memória por processo (`lru_cache(maxsize=1)`) e não reprocessa CSVs nem faz requests por dispositivo. Para atualizar a tabela, substituir o JSON local e reiniciar o serviço de modo autorizado. Se indisponível, vendor fica null; nenhuma identidade inventada. Qualquer redistribuição requer revisão jurídica da licença da fonte.

## QA / privacidade
- `python -m unittest tests.test_device_identity -v` ou `python -m unittest discover -s tests -v`.
- Testar 1/19/1000 MACs **inventados**, incluindo global, local, multicast, zero, inválido, prefixos aninhados e desconhecidos.
- No S7, medir RAM/CPU e tempo de import em volume real **somente com autorização**, sem varredura nem mudança no polling; manter >=2 GiB internos livres.
- Não usar dados, hostname, IP ou capturas reais como fixture pública.
