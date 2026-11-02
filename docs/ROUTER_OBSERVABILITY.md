# Configuração, diagnóstico e histórico do router

O painel **Configuração e diagnóstico**, no fim de `/router/`, acrescenta 28 fontes lógicas ao coletor Huawei HG8247B7-8N, firmware `V5R024C00S114`. Compartilha conexão e cookie existentes. Não cria segundo login, executa JavaScript recebido ou altera o equipamento.

## Dados disponíveis

| Grupo | Dados preservados |
|---|---|
| Wi-Fi | Canal, potência, política de largura, padrão/modos, PMF/cifras configuradas, WMM, beamforming, MCS/limiar RSSI configurados, DTIM/beacon/RTS/fragmentação, MU-MIMO, airtime fairness e backhaul |
| Convidados | Limites reportados e pool privado |
| UPnP | Estado reportado, protocolo, portas, cliente LAN, restrição de origem e duração |
| Políticas | Firewall IPv4/IPv6, ACL de gestão WAN, filtro MAC, exclusões de band steering e agenda Wi-Fi |
| Clientes | Flags IPv4/IPv6, endereços LAN, nomes/tipos/alias/modos reportados; fontes separadas para comparação |
| DHCP/LAN | Concessões, tempo restante/decorrido reportado, reservas, servidor, pool, duração e encaminhamento DNS |
| IPv6 | Estado WAN, tipo/encapsulamento, presença de DNS/AFTR/gateway, origem/validade de endereços e prefixos, Router Advertisement e DNS LAN |
| Estações | Fonte alternativa de 29 campos: sinal, taxas PHY e capacidades; separada da fonte existente de 30 campos |
| Hardware/serviços | Rádios/bandas, MLO configurado, componente Wi-Fi, estado USB, registo/estado de chamada, política de toque, FTP/SFTP/DLNA e NAT configurado por serviço WAN |

`FIELDS`, em `app/router_observability.py`, define a allowlist aplicada também na ingestão. O inventário consolida os ramos de 16/17 argumentos por MAC: campos discrepantes ficam nulos, com `conflicting_fields` e contagem de linhas reportadas, sem escolher um ramo por suposição. Valores numéricos de estação fora do intervalo válido ficam nulos sem descartar as outras medições. Na fonte alternativa de endereços, interpreta somente os nove argumentos consumidos pela GUI; descarta os três extras sem contrato.

## Cadência e falhas

Métricas existentes continuam com intervalo mínimo de 60 segundos; novas fontes usam 300 segundos. Páginas compartilhadas são lidas uma vez por rodada. Há orçamento de 30 segundos para iniciar leituras adicionais; uma requisição já iniciada continua sujeita ao timeout/repetição existentes. Fontes restantes recebem razão `budget`. Não são iniciadas ações de diagnóstico.

Cache conserva horários originais. Após 900 segundos, a última leitura válida fica antiga. Falhas preservam o último dado válido com indicação de qualidade; não produzem zero nem remoção de regras. Razões são códigos fixos, sem páginas, cookies ou mensagens privadas. Formatos divergentes ficam indisponíveis.

Em `--serve --watch`, falhas de autenticação mantêm HTTP, histórico e telemetria do host ativos. Falhas de sessão entram em `auth_backoff`, com motivo sanitizado, etapa e próxima tentativa na API e no painel. A recuperação espera 5, 15 e 30 minutos, respeita uma janela móvel de uma hora (no máximo três falhas antes de aguardar a janela) e o piso de 60 segundos entre logins. Sucessos breves não apagam o histórico móvel de falhas. Não há replay automático de POST de login.

Uma resposta de desafio incompatível ou três rejeições consecutivas de login deixam `auth_blocked`, com `intervention_required=true`; isso precisa de verificação do operador e não prova senha incorreta. O motivo específico fica em `collector.reason`, a etapa em `auth_stage` e o horário real agendado em `next_retry_at`. Limitação local de cadência não conta como rejeição do router. Execução sem servidor continua encerrando com erro, sem repetir logins automaticamente.

O arquivo privado `collector-recovery.json`, junto de `FNO_DB` no microSD, guarda apenas horários/orçamento de recuperação, sem credenciais ou cookies. Reiniciar não zera os limites. Arquivo inválido/inacessível bloqueia novos logins; não apagar automaticamente para contornar a proteção. Após confirmar acesso e resolver a causa de um bloqueio permanente, parar o serviço, arquivar esse arquivo no próprio microSD e iniciar uma vez; esse reset é uma ação administrativa explícita. Backoff normal retoma sozinho e não exige reset.

Na execução integrada, a outbox entrega diretamente à transação SQLite do mesmo processo. Só remove o arquivo após a função de gravação retornar, já fora da transação. Isso elimina o timeout HTTP de loopback que podia deixar amostra gravada aguardando confirmação. A execução separada conserva HTTP e reenvio idempotente por timestamp/conteúdo; conteúdo diferente para o mesmo timestamp é rejeitado. A fila continua sendo entregue durante espera ou bloqueio da autenticação. `last_collected_at` e `last_persisted_at` distinguem leitura e commit; `last_success` indica um ciclo completo confirmado nesta execução. O histórico persistido continua visível após reinício, mesmo sem sucesso novo em memória.

Para diagnosticar: verificar `/api/status`, a idade de `huawei.collected_at`, `collector.state/reason/auth_stage/next_retry_at` e `recording.pending_samples`. Sondas online e HTTP 200 não certificam coleta atual. O botão Atualizar relê a API, sem autenticar no router. Após ação administrativa, conferir supervisor, HTTP e pelo menos uma coleta posterior com fila vazia; enviar um comando de restart não comprova retomada. Não repetir logins em sequência nem alterar configuração de rede para investigar uma falha de sessão.

## Histórico e APIs

Snapshots ficam em `router_observations`; diferenças ficam em `router_changes`, na mesma transação da amostra principal. Migração aditiva, sem apagar dados antigos. A primeira leitura estabelece referência. Contagem regressiva do lease UPnP não é alteração. Diferenças após falhas/intervalos superiores a 900 segundos indicam lacuna. Backfill preserva snapshots sem fabricar eventos em tempo real.

| Rota GET | Contrato |
|---|---|
| `/api/router/observability?hours=24` | Última tentativa/dado válido por fonte e até 500 diferenças; máximo 366 dias; indica truncamento |
| `/api/router/observability/archive?source=upnp&after=0&limit=100` | Snapshots integrais, ordem de inserção, `next_after` e `has_more`; limite máximo 500; repetir páginas até terminar |
| `/api/router/observability/change?id=1` | Antes/depois sob demanda, sem carregar centenas de tabelas na consulta inicial |
| `/api/status` | Acrescenta `collector.state`, `reason`, `last_attempt` e `last_success` |

O painel permite escolher período, comparar leituras, carregar páginas e exportar resumo JSON. O resumo contém a prévia de alterações; não substitui backup SQLite ou arquivo paginado. `/api/archive?kind=huawei` conserva as extensões das amostras. Retenção padrão ilimitada; `FNO_RETENTION_DAYS` aplica-se também às novas tabelas. Monitorizar crescimento e espaço do SD continua necessário.

## Semântica e privacidade

- Mudanças são intervalos entre observações, não horário exato, causa ou atribuição a utilizadores.
- Largura é política configurada; MCS configurado não é MCS efetivo. Taxa PHY não é débito Internet. Airtime fairness não mede ocupação RF.
- `ConnectedTime` foi observado avançando em segundos com a redução do lease; é tempo reportado da concessão, não duração contínua online. Outros `Time`, limites de convidados e parâmetros sem unidade comprovada continuam explicitamente reportados.
- Regras configuradas não comprovam serviços acessíveis. Entradas neutras UPnP significam ausência de mapeamentos; página inválida significa indisponibilidade.
- Identidades LAN, nomes e descrições ficam no dispositivo autorizado. Endereços/prefixos WAN, PSKs, PIN WPS, credenciais, nomes/caminhos USB e números de telefone não são persistidos. Referências WAN são hashes de identificação, não uma camada de anonimização do arquivo privado.

## Limites confirmados

Não há exportação Wi-Fi disponível na interface da conta verificada. O projeto não chama geradores FW/SDT escondidos no código da GUI. Não executa rescan de APs, speedtest ou diagnósticos ativos. Não há contador validado de tráfego Internet por cliente nem tabela de fluxos NAT. O fluxo de chamadas não teve contrato suficiente para consulta de contagem; não se apresenta “zero chamadas”. Samba sem estado literal validado não é promovido a serviço medido.

## Validação e implantação

`tests/test_router_observability.py`: exemplos sintéticos para cada contrato, exclusão de dados privados, divergência de ramos, cache/conexão compartilhada, autenticação, persistência, lacunas, cursor e comparação. `tests/test_http.py`: rotas/limites. Smoke Chromium: painel, autenticação bloqueada, escape de HTML, largura, arquivo e viewport 320 px. A referência independente de `app/audit.py` continua limitada à telemetria anterior; não se afirma auditoria independente dos novos parsers contra páginas reais.

No S7: código e backups consistentes em microSD, pelo menos 2 GiB livres no interno, migração aditiva e reinício do único coletor. Nunca abrir uma sessão concorrente no router para validar a extensão. Verificações de produção mostram disponibilidade/contagens/horários; dados privados não entram em Git, CI ou documentação pública.
