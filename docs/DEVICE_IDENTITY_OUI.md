# Identidade MAC e fabricante de bloco IEEE — issue #7

> **Escopo:** enriquecimento **leitura-apenas** no inventário local. Não identifica o proprietário, o produto exato, o sistema operacional nem garante que duas interfaces sejam o mesmo aparelho.

## O que a API devolve

O endpoint `GET /api/router/clients` continua a devolver os dados originais do Huawei, a `quality` e os timestamps por MAC. Agora cada item recebe **apenas na resposta** uma estrutura nova:

```json
{
  "identity": {
    "normalized_mac": "00:11:22:33:44:55",
    "mac_type": "global",
    "oui_vendor": "Fixture assignee — EXEMPLO, não um vendor real",
    "oui_prefix_bits": 36,
    "oui_dataset_version": "synthetic-testing-only",
    "sources": ["mac_bit_flags", "ieee_public_assignment"],
    "vendor_semantics": "registered_mac_block_assignee_not_device_model"
  }
}
```

O exemplo é **fictício**: nunca usar o OUI `00:11:22` como atribuição real. `oui_vendor` e `oui_prefix_bits` são `null` quando não há base, match, ou quando MAC não é unicast global.

`mac_type`: `global`, `locally_administered`, `multicast`, `invalid`, `unknown`. O bit U/L ligado indica endereço administrado localmente, **não prova sozinho randomização nem que seja Apple/Android**. Para endereços globalmente administrados, um assignee IEEE representa o bloco da **interface de rede**, que pode pertencer a uma placa/acessório de outra marca. Classificação de categoria/modelo/plataforma é trabalho da issue #8.

A rota `GET /api/router/clients?mac=...` mantém **as observações históricas originais** (sem enriquecimento persistido). Exportações de histórico continuam intactas, sem reconstrução ou fusão de MACs. O enriquecimento de uma identidade **não faz varreduras nem consultas de rede**.

## Instalar base offline — processo explícito

O checkout público **não inclui lista IEEE completa nem qualquer dataset importado de produção**. Sem importar o arquivo, `oui_vendor` permanece `null` e isso é comportamento correto. O repositório contém código para produzir uma base compacta *sem* baixar nada durante a execução da API.

1. Num computador do operador, obtenha os CSVs da **listagem pública da IEEE Registration Authority**:
   - MA-L / oui.csv: https://standards-oui.ieee.org/oui/oui.csv
   - MA-M / mam.csv: https://standards-oui.ieee.org/oui28/mam.csv
   - MA-S / oui36.csv: https://standards-oui.ieee.org/oui36/oui36.csv
   - Índice oficial: https://standards.ieee.org/products-programs/regauth/
2. Confirme que são arquivos oficiais IEEE, registre localmente a **data de obtenção**, e verifique as permissões de reutilização/distribuição aplicáveis. Não usar export proprietário de vendor lookup sem licença.
3. Compile **fora do coletor** usando Python 3.11+; MA-M/MA-S opcionais, mas trazem o prefixo mais específico se incluídos:

```bash
python tools/import_ieee_oui.py \
  --ma-l /CAMINHO/DO/OPERADOR/oui.csv \
  --ma-m /CAMINHO/DO/OPERADOR/mam.csv \
  --ma-s /CAMINHO/DO/OPERADOR/oui36.csv \
  --output /MICROSD/CONFIGURADO/oui-assignments.tsv
```

> **Atenção:** `/CAMINHO/DO/OPERADOR` e `/MICROSD/CONFIGURADO` são placeholders; não criar esses caminhos literalmente. O output deve ficar **no mesmo diretório de `FNO_DB`** (`core.DB_PATH.parent`). Em Android/S7, configurar esse diretório no **microSD**, nunca no armazenamento interno. O diretório deve existir previamente; não há fallback nem instalação silenciosa.

O arquivo `oui-assignments.tsv` tem colunas `bits\tprefixo\tnome` e `# version=ieee-public-<hash>`. Ele armazena **somente** prefixo e nome do assignee público, sem endereços de fabricante e sem dados de dispositivos locais. O hash de versão é derivado do conteúdo e não deve ser confundido com data de publicação do IEEE.

Para atualizar, passe `--replace`; o import é validado antes da escrita e substitui o destino atomicamente com um arquivo temporário **no mesmo diretório**. O servidor verifica alteração por caminho, mtime em nanossegundos e tamanho; atualiza sua referência sem reiniciar, e faz lookup com memória limitada. Sem modificação de SQLite, sem reprocessar histórico.

## Segurança e desempenho

- O arquivo é limitado a **8 MiB** e **100 mil entradas**; parsing malformado, arquivo ausente/ilegível ou arquivo maior que o limite resulta em vendor desconhecido, jamais em chute.
- Dataset em memória **única instância compartilhada**; lookup por 36, 28 e 24 bits em hash, com prioridade pelo prefixo mais específico; sem chamadas a sites de OUI por MAC.
- Nomes de fabricantes vindos do dataset nunca são usados como HTML confiável; consumir o campo com renderização escapada.
- Nenhuma escrita de MAC, IP, nome ou identidade ao dataset, nem publicações de inventário real em GitHub, logs ou CI.
- Configuração atual do servidor mantém GET local sem autenticação de aplicação; não expor na Internet sem autenticação/TLS na borda (README/SECURITY.md).
- A implementação **não** recolhe fingerprints adicionais, não consulta router e não altera o intervalo mínimo do coletor.
- O orçamento >=2 GiB livres internos do S7 é verificado apenas na homologação real autorizada, não inferido de testes sintéticos.

## Testes

```bash
python -m unittest tests.test_device_identity -v
python -m unittest discover -s tests -v
```

Cobrem formatos EUI-48, endereço global/local/multicast/inválido, OUI 24/28/36 bits e regra longest-prefix, falhas de dataset, importação e atualização atômica, dados originais e HTTP sem alteração de persistência, e 1.000 lookups **de MACs de teste**.

## Pendências de homologação

- [ ] Importar uma base IEEE real devidamente verificada para o diretório no microSD já configurado, fora do repositório público.
- [ ] Medir RAM/CPU do processo com base completa sob 1/4 clientes e tempo de resposta em Android 8/S7.
- [ ] Conferir ausência de regressão nas PRs de performance do backend e na cópia integrada do frontend S7.
- [ ] Confirmar nome de origem, tipo MAC e campo vendor em browser, sem confundí-los com categoria/modelo.
- [ ] Testar backup/rollback da base no cartão SD e confirmar reserva >=2 GiB no interno.

**Não houve acesso ou deploy no aparelho real para esta issue.**
