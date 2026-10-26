# Wi-Fi por banda e interface — evidências verificáveis

## Escopo

O Huawei B7 devolve (a) estações Wi-Fi, com MAC e interface `wlanN`, e (b)
metadados dessa interface no **mesmo snapshot**, com canal e banda. A interface
`wlanN` é uma interface virtual/SSID, **não** identifica por si só 2,4 GHz,
5 GHz ou uma antena física. Não usar `wlan5` como sinónimo de 5 GHz.
Não identificar SSID pelo índice WLAN, nem associar o cliente pelo IP.

Esta entrega **não altera o coletor, a frequência de recolha ou os payloads
brutos do router**. Usa dados já recebidos; não há login adicional,
varreduras ou consultas novas ao Huawei.

## Onde aparece

- Home Router: lista de dispositivos com banda, RSSI e contexto do enlace.
- Explorador completo: mesma identificação, filtro por 2,4/5 GHz na leitura atual.
- Dossiê individual: cabeçalho, ligação e sinal, identidade/fontes e histórico
  de interfaces associadas observado no intervalo selecionado.
- Wi-Fi e sinal: curvas independentes de RSSI médio das estações em 2,4 GHz e
  5 GHz, estatísticas válidas por banda e enumeração de interfaces/clientes
  na última recolha quando houver informações frescas.

A agregação de RSSI é a média **aritmética das estações observadas** em cada
amostra para cada banda (posteriormente médias por intervalo). Não se trata
de potência de transmissão da antena, sinal medido por um telemóvel, velocidade
de Internet, nem qualidade geral da banda. Uma curva só existe se houver
estações com RSSI e correspondência de banda conhecida. Sem estações, null.

## Atual vs histórico

Uma etiqueta de banda **atual** exige simultaneamente:
- dispositivo `Online`, com `quality=ok`;
- snapshot Huawei `quality=ok`, não expirado;
- `last_seen` do dispositivo e `collected_at` do router iguais dentro de 1 s;
- uma estação associada com interface WLAN válida e `wifi[wlanN].band`
  correspondente na **mesma recolha**.

Se essas condições não forem satisfeitas, a banda aparece como **não
identificada**, sem reaproveitar a banda de outro momento. Vários WLANs
simultâneos não são colapsados arbitrariamente numa única frequência.

No arquivo, o histórico `wifi_history` regista mudanças das associações
**observadas**, inclusive banda/canal apenas quando constam na projeção
originada da mesma recolha. Não afirma a hora exata da mudança, da queda
ou do roaming. Fontes antigas sem correspondência mantêm a interface mas
não inventam banda. O JSON bruto original e os exportadores antigos
permanecem preservados.

## Atualização das projeções históricas anteriores

O novo código grava informação de banda nas **projeções compactas** futuras.
Projeções feitas antes da atualização não contêm os campos novos. O operador
pode reconstruir esses metadados *offline, sem modificar a amostra original*.

**Procedimento para S7, apenas após autorização explícita do operador:**
1. Confirmar que está a executar a revisão certa, e se o banco está no microSD.
2. Fazer backup SQLite consistente e validar restauração em **cópia**.
3. Conferir pelo menos 2 GiB livres no interno; escrever apenas no microSD.
4. Preferencialmente parar o processo de serviço antes da reconstrução.
5. Executar, apontando para o **arquivo existente**:

```sh
python tools/build_read_models.py --router-db /CAMINHO/NO/MICROSD/router.db
python tools/build_read_models.py --router-db /CAMINHO/NO/MICROSD/router.db --refresh-wifi --batch 32
```

O primeiro comando cria projeções ausentes; o segundo recalcula *somente*
projeções compactas antigas sem metadados Wi-Fi. A execução é paginada,
reentrante, com transações delimitadas, sem alteração de `huawei_samples`
ou `router_client_samples`. Não restaurar um backup antigo sobre coletas
novas. Este documento **não executa** nenhuma dessas operações.

## Dados deliberadamente indisponíveis

- **SSID textual:** não extraído pelo parser atual. O campo visível informa
  "não reportado", sem tentar reconstruí-lo a partir do número da WLAN.
- **BSSID físico, PHY por antena/cadeia MIMO e potência radiada por antena:**
  não confirmados na fonte. Não inferir.
- **6 GHz:** não adivinhar banda por canal ou pelo nome Wi-Fi 7. O parser
  validado reconhece apenas 2,4 e 5 GHz.
- **Roaming exato, horário exato de associação ou saída e tráfego real por
  cliente:** não estabelecidos por esta fonte.
- **MAC aleatório:** o histórico continua ligado à identidade MAC reportada
  e não tenta juntar identidades diferentes.

## Testes sintéticos

```sh
python -m unittest tests.test_wifi_links -v
python -m unittest discover -s tests -v
node tests/test_inventory.cjs
node tests/browser_smoke.cjs
INVENTORY_SMOKE=1 node tests/browser_smoke.cjs
```

Os testes verificam não atribuir 5 GHz apenas porque `wlan5`, não reutilizar
uma banda após expiração, preservar raw durante reprojeção, respeitar outras
classificações e manter compatibilidade com o histórico existente.

Sem autorização, **não há deploy no S7 nem qualquer alteração no router**.
