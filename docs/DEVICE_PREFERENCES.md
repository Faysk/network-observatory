# Personalização local de identidades — issue #11 (implementação parcial)

## Segurança antes de UX de edição

O servidor de leitura não tem sessão de utilizador nem painel administrativo autenticado; a LAN não constitui autorização. **Não existe endpoint HTTP para modificar metadados** e o browser não recebe `FNO_INGEST_TOKEN`. A V1 desta branch disponibiliza configuração de apresentações pelo **terminal local do operador**. A edição na UI requer a definição posterior de autenticação administrativa isolada (sessão com CSRF, política de acesso e TLS confiável), revisão de segurança e homologação; até lá a UI mostra apenas os valores personalizados de forma read-only.

## Campos e persistência

A tabela `device_presentation_overrides` é criada idempotentemente em `core.init_db()`, no mesmo `FNO_DB` SQLite configurado, separado das observações brutas e exportações. Campos: `mac`, `nickname`, `category`, `icon`, `note` (somente local), `revision` e `updated_at`. `note` não é retornado por `GET /api/router/clients`. A API devolve `presentation` com `source:'manual'|'none'` e campos seguros de apresentação. Nome, categoria e ícone manuais têm precedência sobre inferência mas não mudam `classification`.

## Operação CLI privada

Requer o banco já inicializado pelo servidor atualizado. **Não gravar credenciais, nem apontar para a base de produção sem autorização/backup.**

```sh
FNO_DB=/caminho/no/microsd/observatory.db python tools/device_prefs.py set 02:00:00:00:00:01 --nickname "Meu aparelho" --category smartphone --icon smartphone
FNO_DB=/caminho/no/microsd/observatory.db python tools/device_prefs.py show 02:00:00:00:00:01
FNO_DB=/caminho/no/microsd/observatory.db python tools/device_prefs.py reset 02:00:00:00:00:01 --revision 1
```

O MAC acima é **fictício**. O CLI rejeita categorias/ícones fora da lista, texto com control chars, MAC inválido e conflito de revisão. Backup: incluir banco SQLite principal/WAL na cópia consistente existente. Não usar disco interno como fallback. O operador pode apagar um override; o histórico original persiste.

## Checklist pendente antes de encerrar #11
- [x] Tabela separada, validação, versionamento, CLI local, read-only da UI, `note` privada.
- [x] Testes sintéticos de persistência, conflito, reset, enum inválido e ausência de mudança no histórico.
- [ ] Autenticação administrativa web independente e proteção CSRF revisada; escolha segura do mecanismo antes de criar qualquer ação web de escrita.
- [ ] Formulário acessível de edição, confirmação e cancelamento, sem falso botão quando não autorizado.
- [ ] Homologação de migração, backup, volume microSD e orçamento do interno >=2 GiB no S7 físico.
