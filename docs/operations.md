# Operations

## Configuration

`python3 scripts/configure.py` generates random database, session and callback secrets in a private mode-0600 `.env`, preserving existing configuration. `.env.example` documents fields; its empty secrets are not deployable credentials.

| Setting | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL; Compose overrides its host to `db` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Compose database initialization; changes do not migrate an existing volume |
| `SECRET_KEY` | Random signing key; rotation invalidates sessions |
| `PAYMENT_CALLBACK_SECRET` | Separate callback HMAC secret; alias `PAYMENT_WEBHOOK_SECRET` |
| `APP_ENV` | `production` enables startup safety checks |
| `COOKIE_SECURE` | `true` under HTTPS; alias `SECURE_COOKIES` |
| `TRUSTED_HOSTS` | Allowed hostnames separated by commas, without protocol/port |
| `BASE_URL` | External origin, including protocol |
| `SEED_DEMO`, `DEMO_PASSWORD` | Private development fixtures; disable seeding publicly |
| `ENABLE_SCHEDULER` | Enable due weekly settlement checks |
| `PAYMENT_PROVIDER` | `sandbox` is the implemented provider |
| `PUBLIC_HOST`, `TLS_EMAIL` | Domain/contact for optional Caddy TLS |
| `APP_PORT` | Host's loopback HTTP port, default 8000 |

Use a dedicated database login. Keep secrets out of commits/logs. PostgreSQL has no host-published port. App traffic reaches port 8000 through loopback or Caddy's private network. Do not publish port 8000 publicly while trusting forwarded proxy headers.

## HTTPS deployment

These instructions do not imply that a public deployment was performed.

1. Prepare a patched Docker host and domain with A/AAAA records pointing to it. Allow TCP 80/443, optionally UDP 443 for HTTP/3. Keep app/database ports private.
2. Run `python3 scripts/configure.py`. Edit `.env`: real `PUBLIC_HOST` and `TLS_EMAIL`, `BASE_URL=https://your-domain`, `TRUSTED_HOSTS=your-domain,localhost,127.0.0.1`, `APP_ENV=production`, `COOKIE_SECURE=true`, `SEED_DEMO=false`. Keep random secrets. Use a separate clean production database.
3. Run `docker compose --profile tls up --build -d`. Caddy obtains/renews certificates when DNS and ports are correct; its state persists in named volumes.
4. Privately provision the initial administrator: `docker compose exec app python scripts/create_user.py --email your-address --name 'Administrator' --role admin`. The command prompts twice for a password, avoiding shell history. Sign in and provision partner accounts using admin account creation (`POST /api/admin/users`); restaurant provisioning requires its profile/address/coordinates. Public registration creates customers only. Verify role boundaries before onboarding real users.
5. Check HTTP redirects to HTTPS, certificate validity, `/health`, the Secure/HttpOnly login cookie, and rejection of unexpected Host headers. Keep loopback hosts allowed for container health checks.
6. Configure monitoring, off-host backups, recovery drills and a real payment provider before commercial use. Sandbox payments, refund bookkeeping and marking settlements paid do not execute financial transfers.

Browser GPS requires HTTPS or localhost and the user's permission. Keep the driver page active with a stable connection. Background mobile browsers may suspend location timers; a dedicated mobile service is needed for guaranteed background GPS.

## Daily backups and RPO

`scripts/backup.sh` streams a consistent compressed PostgreSQL custom dump, verifies its table of contents, and atomically renames it under `backups/`. Files are owner-only. Set `BACKUP_DIR=/protected/path` or `KEEP_DAYS=30` to adjust storage/retention. A directory lock prevents overlap; inspect running jobs before removing a stale `.backup.lock` left by a crashed job.

`scripts/install_backup_cron.sh` installs a managed daily **02:00 host-time** schedule while preserving other entries. Verify the host timezone and `crontab -l`. The cron user needs Docker access. A sleeping desktop or stopped Docker engine does not satisfy daily backup requirements. Errors go to `backups/backup.log`.

Replicate each successful dump to encrypted storage outside this host. Back up deployment secrets separately in restricted storage; a database dump cannot recover session keys or proxy configuration. Alert before the latest successful remote archive exceeds 24 hours. Remote copies need their own retention policy.

Daily scheduling targets **RPO≤24h**. Only monitored success, remote copies and proven recoverability establish the actual RPO. Use managed PostgreSQL continuous WAL archiving/PITR for tighter recovery points.

## Recovery and RTO

`scripts/restore.sh` requires `--yes-erases-current-data`. It checks archive readability, stops the application and replaces database objects transactionally. Failure rolls back and leaves the app stopped for inspection. Back up the current database first when possible.

1. Recover the repository and private `.env` from trusted storage on a host with Docker, sufficient disk and correct credentials.
2. Run `docker compose up -d db`, then wait for healthy database status. Existing volumes retain their original credentials.
3. Run `scripts/restore.sh /absolute/path/known-good.dump --yes-erases-current-data`. The script recreates or restarts the app after a successful transaction. On a new host it may first need to build the application image.
4. Run `docker compose up --build -d app`, or `docker compose --profile tls up --build -d` for HTTPS. Check `/health`, login, a known order, item/payment values and latest saved timestamp.
5. Rerun due reconciliation in admin; unique source records avoid duplicates. Reopen traffic after validation and rotate credentials if compromise caused the incident.

Rehearse restoration to a separate non-production database. Record archive size, download/import/validation duration and total outage. Keep tooling and archives ready for the report's **RTO≤4h**. Archive-list verification alone is not a full restore test.

## Reconciliation

The scheduler checks every 30 seconds for accounting periods due at **23:59 Sunday Asia/Ho_Chi_Minh**. Keep `ENABLE_SCHEDULER=true`. Unique period/party and source records protect reruns. The admin can manually run due periods; `include_current=true` intentionally demonstrates current-period data and is not the weekly operating schedule.

Restaurant settlement equals eligible food revenue less commission. Driver settlement equals delivery fees less COD collected: positive is payable to the driver; negative is owed to the platform. Pending/paid are accounting statuses; bank transfers require a real financial integration.

## Monitoring and capacity

Monitor `/health` from outside the host, container restarts, PostgreSQL storage/connections, error and forbidden-access logs, pending dispatch, failed payments, stale GPS, overdue settlement work, archive age and certificate expiry. Do not log passwords, cookies or secrets.

```sh
python scripts/load_test.py --demo --base-url http://127.0.0.1:8000 --users 200 --requests 2000 --output artifacts/load-test-authenticated.json
```

Use `--demo` only with seeded development data. For staging, provision an active customer and pass `--email` or set `GATHER_LOAD_TEST_EMAIL`. The script prompts for a password without echo; non-interactive runs should supply `GATHER_LOAD_TEST_PASSWORD` from the job's secret store. This variable also overrides the default demo password when `--demo` is used. Non-local origins require HTTPS.

The test authenticates once and shares the customer session among all concurrent clients; neither login nor warm-up counts toward latency. Timed requests only read the catalog and include connection waits and failures. The JSON records concurrency, throughput and p50/p95/max for each endpoint without credentials or cookies. Exit 0 requires no errors and each p95≤2s; 1 signals a threshold failure; 2 indicates a setup failure. Retain server specs, data size/topology and load with its JSON. Remote generation better isolates server capacity.

Single-host Compose restart policies cannot prove **99.5% monthly uptime** (roughly 3h36m downtime in a 30-day month, excluding announced maintenance). Meeting it needs measured external uptime, redundant apps, database failover, reviewed migrations and incident response. Tables are initially created at startup; production schema evolution requires versioned reviewed migrations, not a database reset.
