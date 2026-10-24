# Security and privacy

Only source code and synthetic examples belong in this public repository. Never add credentials, captured responses, real identities, MAC addresses, personal documents, database files, screenshots from production, or derived full-text indexes.

The read API is not an authentication boundary. Keep local servers on loopback unless access is restricted to a trusted network. Do not expose router administration or ADB ports to the Internet.

Runtime credentials belong on the operator device. If a CI job ever needs credentials, use scoped GitHub Actions secrets; do not put them in commits, Actions logs, or browser bundles. Current checks require no secrets and make no connection to a production router.

To report a vulnerability, use GitHub private vulnerability reporting if enabled. Do not post secrets or personal samples in issues.
