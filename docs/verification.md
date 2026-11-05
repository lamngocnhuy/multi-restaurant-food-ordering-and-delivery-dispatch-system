# Verification record

Recorded on **3 November 2026** during implementation. The normal application uses PostgreSQL; the test suite also has a disposable SQLite fallback for quick checks. Results describe this local development environment, not a hosted production SLA.

## Catalog load test — NFR01

The read-only load test completed at **16:19:26 Asia/Ho_Chi_Minh** (`2026-11-03T09:19:26Z`) against the locally running application and real PostgreSQL database. The raw output is `artifacts/load-test.json` in this workspace.

```sh
python scripts/load_test.py --base-url http://127.0.0.1:8000 --users 200 --requests 2000 --output artifacts/load-test.json
```

| Measure | Recorded value |
| --- | --- |
| Concurrent clients / peak requests in flight | 200 / 200 |
| Measured requests | 2,000 |
| Failures | 0 |
| Duration | 7.24 seconds |
| Throughput | 276.13 requests/second |
| Overall p50 / p95 | 515.09 ms / **859.16 ms** |
| Responses completed successfully within 2 seconds | **99.00%** |
| Slowest response | 2,579.51 ms |
| Test verdict | Passed: every endpoint p95 below 2,000 ms, no HTTP/network errors |

| Endpoint | Requests | p95 | Successfully within 2s |
| --- | --- | --- | --- |
| Restaurant discovery | 667 | 915.46 ms | 98.95% |
| Menu search | 667 | 808.14 ms | 98.80% |
| Restaurant menu/detail | 666 | 802.98 ms | 99.25% |

The report requires at least 95% of catalog/menu lookups within 2 seconds under up to 200 concurrent users; this measured run met that criterion. Some individual requests exceeded 2 seconds, as shown by the maximum. Client and server ran locally with seeded catalog data; a deployment with larger data, public traffic, remote networking or different hardware must repeat the test.

## Automated acceptance results

| Runtime / database | Result | Duration |
| --- | --- | --- |
| Local Python, real PostgreSQL | **25 passed** | 4.52 seconds |
| Local Python, isolated SQLite fallback | **24 passed, 1 skipped** | 2.27 seconds |
| Built Docker image, Python 3.12, real PostgreSQL | **25 passed** | 3.29 seconds |

The skipped SQLite check is PostgreSQL transaction/concurrency acceptance. On PostgreSQL, **16 simultaneous checkout submissions produced one invoice and one payment**. The suite also validates signed callback replay, role/owner boundaries, incident resolution, FREESHIP accounting, exact Sunday cutoff behavior, expiry/reassignment of unanswered driver offers, persisted refund records, and withholding unpaid online orders from restaurant partners.

## Environment and repeatable checks

The local runtime used **Python 3.14.5, FastAPI 0.121.0, SQLAlchemy 2.0.44, and PostgreSQL 17 Alpine**. The supplied Dockerfile uses Python 3.12 and Compose specifies PostgreSQL 17 Alpine, and the built image also passed the full PostgreSQL suite. The primary dependencies are pinned to the tested versions.

The automated suite covers catalog/search, authentication and roles, field/customization validation, multi-restaurant quotes and exact promotion allocation, fresh checkout pricing/availability, distance/closed-restaurant rejection, duplicate checkout, online failure/retry/replay, partial refunds, ordered pickups/COD completion, driver reassignment/offer expiry, ownership/reviews, reconciliation idempotency, menu constraints, GPS/accounts, signed callbacks, account provisioning, incidents, FREESHIP accounting and the Sunday cutoff.

```sh
# Quick isolated checks; concurrency is skipped on SQLite.
pytest -q

# Full database acceptance: use a dedicated disposable PostgreSQL database.
TEST_DATABASE_URL='postgresql+psycopg://gather:your-local-password@localhost:5432/gather_test' pytest -q
```

The PostgreSQL database name must end in `_test`; the suite rejects other names before dropping/creating test tables. Do not run the suite against development or production business data.

The following deployment/tooling checks passed: Compose configuration validation; Python syntax for environment/load tools; shell syntax for backup/restore/cron tools; and an isolated environment-generator smoke check verifying mode-0600 permissions, generated secrets, and preservation of an existing `.env` on rerun.

## Isolated PostgreSQL backup/restore drill

At **16:34:09 Asia/Ho_Chi_Minh** on 3 November 2026, a custom-format dump of the running development database `gather` was created at `/tmp/gather-verification.dump`, its archive contents verified, and restored transactionally using `pg_restore --no-owner --single-transaction --exit-on-error` into a **new empty database `gather_restore_test`**. The source database was never overwritten, dropped or stopped. Results are saved in `artifacts/restore-drill.json`.

| Measure | Result |
| --- | --- |
| Compressed archive | 46,912 bytes |
| Backup time | 0.097 seconds |
| Database import time | 0.080 seconds |
| Entire isolated drill and data validation | 0.400 seconds |
| Restaurants / dishes | **8 / 32** |
| Orders / restaurant suborders / order lines | **2 / 2 / 3** |
| Payments | 1 |
| Sum of order totals / refunds | **314,400₫ / 0₫** |
| Source/restored summaries | Identical |

Checks found **zero** invalid parent/suborder/line totals, parent-to-suborder allocation mismatches, or suborder-to-item subtotal mismatches. Each parent total matched food plus delivery minus discount; each item matched unit price times quantity. The archive and restored test database were retained for inspection.

This verifies recoverability of the small development dataset. The 0.400-second local drill is not a measured production service-recovery RTO: it excludes provisioning, off-host download, TLS/DNS recovery, incident handling and user-facing validation. Daily backup success and remote retention still need ongoing monitoring.

## Deployment targets requiring ongoing evidence

The optional TLS proxy and secure production-cookie guards are provided; a real-domain certificate deployment must be verified on its actual host. The payment provider is explicitly sandboxed and performs no real capture/refund/bank transfer.

Daily backup and restore scripts plus recovery procedures are provided, and one isolated local restore passed as recorded above. Demonstrating production RPO≤24h/RTO≤4h requires monitored off-host backups and appropriately sized timed recovery drills. Monthly 99.5% availability requires a monitored long-lived deployment and redundancy. GPS timing requires a permissioned active browser and stable network; background mobile suspension can violate timing. These targets are not established by a one-time local functionality or load test.


## Browser verification

The customer journey passed in the browser: sign-in, restaurant menu, size and topping selection, quantity changes, persisted basket, promotion, checkout, sandbox success, and order tracking. Large phở plus extra egg at quantity 2 cost 188,000₫; WELCOME10 plus delivery produced a consistent 201,200₫ invoice. The restaurant accepted, prepared and marked it ready; a driver came online, received and accepted the trip, then confirmed pickup. Admin operations and account lists rendered with persisted data.

The layout was inspected at 360, 1440 and 1920 pixels; DOM measurements at 360 and 1920 showed no horizontal overflow. Staff workspaces hide customer basket/navigation. The administration screenshot is retained at `docs/screenshots/gather-admin.jpg`.

Final browser checks of the revenue-report tab and newly added driver route-map display could not finish: the browser automatic approval service reported capacity/timeouts before granting action authority. This was an automation-service failure, not a reported application error. API/business behavior is covered by automated tests; route-map JavaScript passed syntax checks. Browser GPS permission was not enabled during testing, so real device GPS cadence requires an active permissioned device check.

The Docker build initially encountered a package-download timeout. Retrying with longer download timeouts and pinned tested dependencies completed successfully; all 25 tests then passed inside the resulting image. Public TLS, a live payment provider, and month-long availability measurement were not performed.
