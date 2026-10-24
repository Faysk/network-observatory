# Public source repository

Never commit production data, credentials, private files or derived indexes. Use synthetic fixtures only. Keep unavailable values null, preserve provenance, and respect reduced-motion preferences. Do not probe or deploy to a real device without explicit operator authorization.

For S7 deployments, keep persistent files on microSD, reserve at least 2 GiB available internally, and use internal cache only for demonstrated performance needs with bounded disposable files. Network disks are for large media and backups, not active SQLite databases.
