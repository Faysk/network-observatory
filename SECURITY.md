# Security and privacy

Only source code and synthetic examples belong in this public repository. Never add credentials, captured responses, real identities, MAC addresses, personal documents, database files, screenshots from production, or derived full-text indexes.

The read API is not an authentication boundary. Keep local servers on loopback unless access is restricted to a trusted network. Do not expose router administration or ADB ports to the Internet.

Runtime credentials belong on the operator device. If a CI job ever needs credentials, use scoped GitHub Actions secrets; do not put them in commits, Actions logs, or browser bundles. Current checks require no secrets and make no connection to a production router.

To report a vulnerability, use GitHub private vulnerability reporting if enabled. Do not post secrets or personal samples in issues.

## Controlos de acesso de leitura e credenciais do Huawei

Por padrão, a aplicação aceita chamadas HTTP **somente de conexões originadas
em loopback**, independentemente de `--bind` ou `FNO_BIND`. Para permitir
um PC/telemóvel na LAN, configure explicitamente `FNO_READ_ALLOW_CIDRS`
com uma ou mais sub-redes **RFC1918** de confiança, separadas por vírgula,
por exemplo `192.168.1.0/24` se esta for efetivamente a rede doméstica.
A função verifica o endereço da ligação TCP e não confia em cabeçalhos
`X-Forwarded-For`. CIDRs públicos, genéricos e IPv6 são rejeitados. Uma
ACL de endereço IP **não é autenticação de usuário**: qualquer aparelho da
faixa autorizada pode ler MACs, eventos, amostras e exportações. O acesso
remoto deve usar VPN ou proxy com autenticação e TLS, preferivelmente com
origem em loopback. Não abra a porta do serviço no router ou na Internet.

O adaptador validado para o Huawei usa **HTTP/80**, inclusive na sessão de
login; não há comprovação de HTTPS nessa interface específica. O canal de
administração não deve passar por redes de hóspedes, intermediários não
confiáveis nem portas públicas. Não afirmar proteção criptográfica de
credenciais ou autorização de gestão além daquela efetivamente oferecida
pelo firmware. A API do Network Observatory nunca deve receber a senha do
router pelo navegador: ela permanece no processo coletor autorizado.

Antes de atualizar o serviço real: configurar a ACL para os clientes de LAN
que precisam aceder ao painel, verificar alcance a partir de um peer dentro
e outro fora da faixa, e manter rollback do código. Sem a variável,
o painel continuará disponível no S7 via `127.0.0.1`, mas não no PC pela LAN.
