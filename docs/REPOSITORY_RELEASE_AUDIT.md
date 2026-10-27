# Repository and deployment reconciliation — 2026-10-26

Runtime source is compared to each repository main, normalizing CRLF for source review and retaining byte hashes for deployment. The integrated S7 manifest identifies the standalone main revision. No private documents, telemetry or identifiers belong in this repository.

## Runtime reconciliation

- Publish the generic Tuya OUI classification from PR #39. Operator overrides stay independent and take precedence.
- Upstream the existing private deployment guard rejecting absolute-form HTTP requests. This is an origin application, not a forward proxy. A local HTTP regression test rejects an example.invalid target without contacting it.
- Keep the S7 example fixture synthetic, and never load it in the real UI.
- Vault shares the public application logic with deployment-specific owner labels/routes and private HTML/data modules. These deliberate private substitutions are not stale application code; do not replace the private corpus with public examples.
- Application, databases, logs and backups stay on microSD; check the internal 2 GiB reserve before deployment. No new internal cache.

## What is complete and what remains open

Functional Router inventory, data math, WAN views, loading states, source privacy and the three published applications have automated and live endpoint checks. Existing measurement reports distinguish LAN/backend timings from browser timings.

Status atualizado em 27/10/2026: as issues #6 (closed/completed) e #13 (closed/not_planned) constam encerradas no GitHub. **Esses estados não comprovam** os critérios físicos de INP/LCP/long tasks/FPS, interação por toque/leitor de ecrã e medidas sustentadas antes/depois. Nenhum resultado de CI desktop ou ligação ADB certifica essas medições; mantêm-se pendentes de homologação no Android 8 real.

The offline manufacturer registry is now installed from the official Wireshark manufacturer dataset. Earlier statements that no real OUI dataset was installed are superseded; IEEE CSV retrieval was blocked, and no counterparty protection was bypassed. The deployment records the actual provider instead of claiming direct IEEE retrieval.

Branches are archived in private operator Git bundles before deletion; only main remains after cleanup. Closed/superseded implementation branches are not separate releases to deploy over the integrated main.
