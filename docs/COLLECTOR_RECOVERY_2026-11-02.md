# Recuperação do coletor Huawei — 02/11/2026

## Incidente e limites da evidência

Em 01/11, a coleta parou às 15:24:57 UTC, após uma amostra de 15:23:53.
Um reinício manual recuperou a autenticação com as mesmas credenciais, mas
outra falha às 21:41:19 interrompeu a coleta novamente, após a amostra de
21:40:14. Em 02/11, isso foi observado após mais de 14 horas sem atualização.
As sondas de conectividade e o servidor continuavam disponíveis.

Os registros antigos reduziram diferentes erros a `authentication_failed`.
Não permitem determinar se a rejeição original veio da sessão, do desafio,
do login ou do limite local entre autenticações. O uso das mesmas credenciais
na recuperação não demonstra a causa exata da rejeição anterior.

## Correção integrada

[PR #72](https://github.com/Faysk/network-observatory/pull/72), commit
`97ab8796cca572822cdca3a379eaa445055264c6`, relacionada a #68–#71:

- Substitui espera infinita após falha de sessão por recuperação com atrasos
  de 5/15/30 minutos e histórico móvel de falhas de uma hora. O piso local de
  60 segundos entre logins continua obrigatório. Reinícios não zeram o orçamento.
- Persiste somente horários, contadores e códigos fixos no microSD; nunca
  credenciais, cookies, desafios ou corpos HTTP. Estado inválido impede login.
- Limitação local não consome orçamento de falhas do router. Um login recém
  executado não é repetido no mesmo ciclo quando a leitura seguinte falha.
- Desafio incompatível e três rejeições consecutivas de login exigem ação do
  operador. Rejeição de login não é automaticamente rotulada como senha incorreta.
- Expõe motivo, etapa, status HTTP permitido, duração do ciclo que falhou,
  próxima tentativa, histórico de falha e contador de renovações. A duração
  reportada não é uma medição isolada do endpoint de autenticação.
- Na execução integrada, entrega a outbox diretamente à transação SQLite.
  Confirmação ocorre após o retorno da transação, eliminando a corrida com o
  timeout HTTP de loopback. Entregas pendentes continuam durante bloqueio de login.
- Mantém a idempotência existente por timestamp/conteúdo e rejeita conteúdo
  conflitante. BrokenPipe na resposta de uma mutação não provoca segunda resposta.
- O painel distingue coleta bloqueada, recuperação programada, amostra antiga
  e gravação pendente, com horários e histórico preservado. Atualizar não faz login.

O complemento [PR #73](https://github.com/Faysk/network-observatory/pull/73),
commit `d7f558cd8fa90487a6aa4df8c0c93aa7488e1732`, separa o lock do estado do
coletor das consultas SQLite e publica o prazo de espera entre logins após
reinício. Isso evita que uma confirmação já concluída espere por consultas
longas para atualizar o estado do coletor.

## Validação sintética

- 217 testes Python aprovados em Linux/WSL (Python 3.12).
- 16 testes específicos de recuperação/entrega aprovados no Python do S7,
  importando o código efetivamente instalado e usando bancos sintéticos isolados,
  sem chamadas ao router ou banco de produção durante os testes.
- Testes cobrem persistência dos limites entre reinícios, retrocesso de relógio,
  bloqueio por desafio incompatível, rejeições repetidas, retomada automática,
  entrega durante cooldown e falha ao salvar o orçamento antes de um POST.
- Replay após commit com confirmação perdida preserva amostras, observações
  de clientes, eventos e projeções em fixture com transição real de estado.
- Smoke Chromium integrado aprovado, incluindo aviso persistente em 320 px e
  foco por teclado; contratos Node de inventário, gráficos e requisições aprovados.
- Checks GitHub de Linux e teste SQLite específico de Windows aprovados.
  A execução completa local em Windows apresentou falhas de sockets/limpeza
  de arquivos SQLite e não é reportada como aprovada nesse ambiente.

## Publicação e acompanhamento

A publicação autorizada usa patches por contexto sobre os arquivos implantados,
preservando diferenças privadas e configuração. O rollback restaura código,
sem restaurar banco antigo sobre novas coletas. Backups e artefatos operacionais
ficam privados no microSD. Foram concluídos backups consistentes Router e Host,
ambos com `PRAGMA quick_check=ok`. O backup online encontrou contenção; uma
janela de manutenção permitiu concluir as duas cópias antes da publicação.

A implantação também alinhou a outbox à versão pública já testada e retirou a
enumeração da fila de dentro do lock SQLite na função de status antiga do S7.
Não houve migração nem substituição dos bancos. As alterações de código foram
conferidas por hashes, com cópias dos arquivos anteriores preservadas.

Após o último reinício, o coletor respeitou o prazo de login persistido em
`auth_backoff / login_rate_limited` e retomou automaticamente. A coleta de
12:43:07 UTC terminou com `state=ok`, `quality=ok`, timestamps de coleta e
persistência iguais, fila vazia e sem quarentena. O Chrome real abriu o painel
com “RECOLHA ATIVA”. Isso valida retomada após espera local e coleta normal;
falhas de autenticação do router foram reproduzidas em fixtures, não provocadas
no equipamento de produção.

O acompanhamento final está nas issues #68–#71. Testes sintéticos e algumas
coletas reais não certificam estabilidade física de 24 horas; essa homologação
permanece no escopo de #52/#13. A causa exata das rejeições antigas não foi
reconstruída artificialmente.

O objetivo é eliminar a necessidade de reinício para falhas transitórias de
sessão. Uma credencial realmente inválida ou um protocolo incompatível continuam
exigindo intervenção, em vez de tentativas ilimitadas.
