# WBSps.ca local deployment

> **The archive online: https://wardbecksystems.github.io/WBSps.ca/** (repository: https://github.com/WardBeckSystems/WBSps.ca)

The whole archive site served from this machine, with every image, scan, PDF and drawing included. The public GitHub Pages site (`../site`, built by `2026/timelines/make_site.py`) has only the pages and their meta links.

```
cd docker
docker compose up -d          # start the container "WBSps.ca"
open http://localhost:8067    # the binder index
docker compose down           # stop it
```

- `2026/` is the web root. `WBSps.env/` (the originals) is served at `/WBSps.env/`, so the "open original" links work.
- Both are mounted read-only, so the container can never change the archive.
- It is bound to 127.0.0.1. To share it on your local network, change the port line in `docker-compose.yml` to `"8067:80"`.
- Nothing needs rebuilding in the container: re-run `2026/timelines/run_all.sh` and refresh the browser.
- The timeline database, scripts and `.git` are never served.

## Local FTP Service

The stack includes a local Pure-FTPd service (`WBSps.ca-ftp`) bound to `127.0.0.1:21` with access to the whole `WBSps.ca` project tree.

- Credentials and configuration are maintained in `docker/.env` (gitignored).
- Account: `wbsps@wbsps.ca`
- Pre-configured in FileZilla Site Manager as `WBSps.ca (Local)`.

