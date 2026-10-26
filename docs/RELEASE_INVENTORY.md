# Integração de inventário — 26/10/2026

Esta branch concilia a entrega de desempenho #5 com o inventário #15–#17 e o explorer. Aproveita a administração local de #22, adaptada à taxonomia completa de 13 categorias. As implementações concorrentes #18–#20 não devem ser aplicadas por cima: seus contratos/categorias diferem. Nenhum dado real faz parte do repositório.

## Entrega

- MAC EUI-48 estrito, flags local/global/multicast; OUI offline por prefixo mais específico, origem e versão. Base ausente/corrupta/permissão negada retorna desconhecido. Nenhum MAC é enviado à Internet.
- Classificador determinístico prudente, conflitos e evidências; OUI, interface ou DHCP genérico não comprovam categoria/OS.
- Sprite SVG local original MIT; fallback neutro e categoria textual na lista, explorer e dossiê.
- Explorer com filtros combinados, grupos de estado, busca, ordenação e 40 cards por página. Desatualizado não vira offline; contagens pendentes ficam desconhecidas. Foco, filtros, paginação e scroll preservados no polling.
- Metadados separados no SQLite configurado: apelido, categoria/ícone, nota privada, revisão; precedência manual sem sobrescrever inferência ou registros. Edição/reset via CLI local autenticada; nenhuma mutação HTTP administrativa ou token no browser.
- Sugestões de possíveis relações são fracas, limitadas e não confirmadas; associação/desassociação somente por CLI explícita. Históricos e contagens permanecem por MAC.
- Dossiê cancela chamadas obsoletas, troca o período imediatamente, bloqueia exportação até resposta válida e oferece retry.

## Validação da candidata

99 testes Python aprovados em Windows; testes Node de seletores (19/1000 identidades), histórico/S7 e reentrada de requisição abortada aprovados. Fixture de browser integrada com 1000 identidades: 40/80 cards, busca, atualização com foco, override e rótulo HTML escapado, 320/768/1300 sem overflow e fechamento restaurando foco. A fixture anterior de desempenho é reexecutada para evitar regressões. CI inclui ambas as fixtures Chromium.

Não confundir estes testes com INP/FPS/LCP no navegador Android físico. Essa medição de cliente continua fora da evidência disponível; não há garantia universal de 200 ms. Estado de publicação, hashes, disco, backup e medições LAN serão registrados após homologação.

## Dados OUI e licença

Fonte prevista: [IEEE Registration Authority, public listings](https://standards.ieee.org/products-programs/regauth/). Download dos três CSVs oficiais foi recusado (HTTP 418) nesta sessão. Não instalar base de procedência desconhecida nem inventar fabricante: operação continua com `oui_vendor=null` até importação oficial explícita. O dataset não é redistribuído no Git. SVG e regras são originais MIT; não copiar logomarcas ou bases de terceiros sem licença.

## Publicação e reversão

Persistentes permanecem no microSD. Antes de migrar: parar apenas o serviço da aplicação, gerar backup SQLite consistente, testar restauração em cópia isolada, guardar hashes e código anterior. Migração idempotente adiciona duas tabelas de metadados; nenhum ALTER/UPDATE/DELETE nas observações. Rollback de código preserva tabelas extras e dados recentes; não restaurar banco antigo sobre a coleta atual. Não habilitar cache interno; exigir >=2 GiB disponíveis no interno. Aguardar intervalo de autenticação de 60 s antes de retomar o coletor Huawei.
