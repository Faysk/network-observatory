> Estado atual: houve publicação e homologação funcional LAN em25–26/10/2026. As seções históricas abaixo preservam o escopo original; consulte [a revisão integrada](RELEASE_INVENTORY.md) e [consultas compactas/estado atual](READ_MODELS.md). Metas físicas não medidas continuam pendentes. Preferências são administradas via CLI autenticada; não há editor web.

# Classificação prudente de aparelhos — issue #8

## Contrato

Cada cliente de `GET /api/router/clients` recebe **`classification`** ao lado de `identity` (#7) e dos campos brutos originais. A inferência é uma **sugestão**, não confirmação:

```json
{
  "classification": {
    "category": "game_console",
    "platform_family": "unknown",
    "display_name_suggestion": "PS5-Test",
    "confidence": "medium",
    "evidence": [
      {
        "field": "names",
        "rule": "playstation",
        "source": "huawei_http_report",
        "confidence": "medium"
      }
    ],
    "conflicts": [],
    "classification_version": "router-rules-v1",
    "category_semantics": "heuristic_suggestion_not_verified_identity"
  }
}
```

Dados e nomes deste documento são **fictícios**, não exportações da rede real.

### Categorias

`smartphone`, `tablet`, `laptop`, `desktop`, `game_console`, `smart_tv`, `streaming_box`, `printer`, `camera`, `robot_vacuum`, `network_device`, `iot`, `unknown`.

Plataforma **separada**: `android`, `ios`, `windows`, `linux`, `macos`, `unknown`.

A UI da issue #9 deverá usar ícones exclusivamente da *categoria*, com fallback desconhecido; badges de plataforma apenas se houver evidência. Não inferir tipo de dispositivo pelo meio Wi-Fi/Ethernet.

### Regras e limites

| Pista | Resultado sugerido | Fonte / confiança |
|---|---|---|
| `PS5`, `PlayStation-5`, `Xbox-Series-X`, `Nintendo-Switch` | `game_console` | Nome/tipo reportado, normalmente *média* |
| `iPhone-16`, `iPad-Air` | `smartphone`/`tablet` e família iOS provável | Nome/tipo, normalmente *média* |
| `S23-de-Fixture`, `Galaxy-Tab-...`, `Redmi-A5`, `Pixel-9-Pro` | Smartphone/tablet Android provável | Nome/tipo, normalmente *média* |
| `Roomba-...`, `Roborock-...`, `ESP32-...` | Robô aspirador ou IoT provável | Nome/tipo, normalmente *média* |
| `Chromecast`, `Smart-TV`, `LaserJet`, `IP-Camera` | Categoria compatível | Nome/tipo, normalmente *média* |
| `ThinkPad`, `MacBook`, `Optiplex` | Laptop/desktop provável | Nome/tipo, normalmente *média* |
| Host terminando em `-PC` | Desktop *pouco confiável* | Nome reportado, *baixa* |
| `android-dhcp-16` | **Apenas** indício de Android; categoria pode ser desconhecida | Tipo reportado, *média* |
| `MSFT 5.0` | **Apenas** assinatura DHCP, **não** Windows confirmado | Tipo reportado, *baixa* |
| `wlan0`, `Ethernet`, um OUI de fabricante, IP/MAC cru | Categoria desconhecida | Sem identificação de classe sustentada |

Cada regra possui ID versionado em `app/device_classifier.py` e uma referência ao *campo* de origem, sem replicar nomes, MACs ou IPs na lista de evidências. Fabricante IEEE é assignee do bloco da interface e **não** força categoria/OS. O prefixo privado/local nunca serve para provar marca do equipamento.

**Confiança qualitativa e determinística:**
- `unknown`: nenhuma pista categórica suficiente ou categorias contraditórias;
- `low`: pista fraca, ou contradição de plataforma;
- `medium`: família reconhecível em um único tipo de campo (nome ou tipo);
- `high`: duas fontes de campo (nome **e** tipo) apontam de forma forte e concordante para a mesma categoria. **Ainda não é verificação humana**.

Se houver pistas conflitantes de categorias, a categoria retorna `unknown` + `conflicts`. Se há plataformas conflitantes, a plataforma vira `unknown`, e a confiança de categoria é reduzida. Jamais sobrescrever um nome confiável, fazer junção de MACs ou reescrever histórico bruto. O fluxo de override humano pertence à issue #11.

### Código, desempenho e privacidade

- `classify_client()` é função pura, determinística e sem acesso à rede, disco, hora ou dados externos.
- Somente campos já presentes em `/api/router/clients` (`names`, `device_types`, `identity`); no máximo 16 valores por campo, até 256 caracteres cada para matching e nenhuma regex com backtracking explosivo.
- Não existe coleta adicional, fingerprint de sistema operacional, pesquisa ativa, correlação por IP ou transmissão de dados a fornecedores.
- Ausência de nome e MAC local são tratados honestamente como desconhecidos.
- Campos de evidências são compostos de IDs de regras e referências de origem, não de valores brutos privados.
- A camada de apresentação deve escapar/encodar o campo `display_name_suggestion`, porque ele continua derivado de hostname não confiável.
- A UI e os ícones fazem parte das issues #9/#10. Overrides persistentes e agregações de identidades são issues #11/#12.

## Testes

```bash
python -m unittest tests.test_device_classifier -v
python -m unittest discover -s tests -v
```

Fixtures sintéticas validam as categorias propostas, falsos positivos (`MSFT 5.0`, `android-dhcp`, `wlan0`, fabricante OUI isolado), colisões de categoria/plataforma, confiança, normalização Unicode, saídas determinísticas, limites e **preservação do JSON histórico**.

## Aceitação física

Homologação real S7, carga de 1/4 clientes, testes de browser na interface final e sincronização com a PR #5 continuam pendentes. **Não houve deploy ou consulta à rede do operador nesta issue.**
