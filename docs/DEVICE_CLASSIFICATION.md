# Classificação visual de dispositivos — issue #8

Classificação **probabilística qualitativa e determinística** de categoria e família de plataforma, sem ML, sondas, OUI externos ou fontes novas. Não identifica fabricante/modelo ou utilizador de forma garantida.

O payload de cada entrada de `GET /api/router/clients` mantém o formato bruto do Huawei e acrescenta `classification` com:
- `category`: `smartphone|tablet|laptop|desktop|game_console|smart_tv|streaming_box|printer|camera|robot_vacuum|network_device|iot|unknown`;
- `platform_family`: `android|ios|windows|linux|macos|unknown`;
- `display_name_suggestion`: primeiro hostname recebido ou null, **sem substituir os nomes originais**;
- `confidence`: `high|medium|low|unknown` (qualitativa, não probabilidade percentual);
- `evidence`: regras/fontes que contribuíram;
- `conflicts`: categorias incompatíveis que forçam `unknown`;
- `classification_version`, `confirmed:false`.

## Regras V1
- Hostname/tipo que contenha padrão de PlayStation/PS5/PS4/Xbox → `game_console`; Roomba/irobot/Roborock/Deebot → `robot_vacuum`; Galaxy Tab/iPad/tablet → `tablet`.
- Prefixos muito específicos de smartphone (S23, Galaxy S23, Redmi, Pixel, iPhone) → `smartphone` como hipótese; Predator/notebook/laptop → `laptop`; `-PC`, workstation/desktop → `desktop`.
- Chromecast/Fire TV/Apple TV → streaming; 'smart-tv'/'bravia'/'roku-tv' → TV; printer/LaserJet/DeskJet → impressora; câmera IP/webcam → câmera; router/repeater/access-point → equipamento de rede.
- `android-dhcp-...` pode sugerir **família Android**, mas não smartphone. `MSFT 5.0` significa padrão DHCP Microsoft: não prova sistema Windows. OUI e meio Ethernet/Wi-Fi sozinhos não provam categoria.
- Se houver categorias distintas sugeridas para o mesmo registro, `unknown` e `conflicts` listados. Identidade MAC, estado reportado, historização e exportação mantidos.
- Override manual e categoria confirmada são trabalho da issue #11; UI e ícones das issues #9–#10. O esquema permite evoluir regras explicitamente versionadas.

## Testes
`python -m unittest discover -s tests -v` inclui exemplos sintéticos de dez categorias, conflitos, falsas inferências DHCP, MAC privado e desconhecidos. O S7 físico não foi acessado. Para homologação real, medir custos e cobertura com consentimento; nenhuma função pública expõe credenciais do router.
