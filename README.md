# Gather — Multi-Restaurant Food Ordering & Delivery Dispatch

A runnable implementation of the supplied **Báo cáo thực hành lab 03** report: one customer cart and checkout, separate restaurant orders, preparation, driver dispatch, ordered pickups, tracking, reviews, reports, and weekly reconciliation.

Built with **Python, FastAPI, PostgreSQL, SQLAlchemy, HTML/Jinja2, Bootstrap 5, and JavaScript**. Bootstrap assets are included locally. Money is stored as integer Vietnamese đồng and business data persists in PostgreSQL.

## Run with Docker

Install Docker with Compose, then run from this directory:

```sh
python3 scripts/configure.py
docker compose up --build -d
docker compose ps
```

Open [Gather](http://localhost:8000), [interactive API documentation](http://localhost:8000/docs), or [database-aware health check](http://localhost:8000/health). First start creates the tables and demonstration data. The configuration script generates private random secrets in `.env` and preserves an existing `.env`. PostgreSQL stays on a private network and persists in a named volume.

```sh
docker compose logs -f app
docker compose stop
docker compose start
```

`docker compose down` preserves the database. **`docker compose down -v` erases the database** and is only for an intentional reset.

## Run Python locally

Use Python 3.12+ and PostgreSQL 17 or a compatible server. Create a dedicated development database and login with your PostgreSQL administration tool, then:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/configure.py
```

Edit `DATABASE_URL` in `.env` to your actual PostgreSQL login, password, host, port, and database. For example: `postgresql+psycopg://gather:your-local-password@localhost:5432/gather`. URL-encode special characters in passwords. `.env` is loaded automatically.

```sh
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The standard Compose database deliberately has no published host port. A local Python process can use your locally installed PostgreSQL, or a private Compose override that publishes the database on a loopback port.

## Demo accounts

With `SEED_DEMO=true`, the seeded password is **`Demo123!`**. Set `DEMO_PASSWORD` before first initialization to use another password; changing it later does not rewrite passwords.

| Role | Email | Workspace |
| --- | --- | --- |
| Customer | `customer@localtable.vn` | `/order` — restaurants, basket, checkout, tracking |
| Restaurant | `restaurant@localtable.vn` | `/restaurant` — menu and preparation |
| Driver | `driver@localtable.vn` | `/driver` — offers, pickups, delivery |
| Administrator | `admin@localtable.vn` | `/admin` — users, dispatch, reports, settlements |

All four roles sign in on the same page (`/` or `/sign-in`). The account determines where you land: customers go to **Order food** (`/order`), and staff go to their own workspace. Signed-out visitors do not see orders, reviews, delivery details, or the basket. Public registration creates customers only.

Other seeded restaurant owners are `restaurant2@localtable.vn` through `restaurant8@localtable.vn` (Pizza & Co., The Green Bowl, Seoul Table, Burger Theory, Mori Sushi, Cloud Nine Tea, Butter & Crumb). A second driver is `driver2@localtable.vn`; all use the same configured demonstration password.

## Delivery address lookup

Customers start without a delivery address. Their confirmed address is saved per account in the current browser. Signed-out visitors see sign-in and registration, and staff go directly to their workspaces.

To fill the street address from **Use my current location**, enable the [Google Geocoding API](https://developers.google.com/maps/documentation/geocoding/cloud-setup) with billing in your Google Cloud project. Add your restricted server key as `GOOGLE_MAPS_API_KEY` in the local `.env`, then restart Gather (`docker compose up -d --force-recreate --no-deps app` for Docker). Keep the key on the server.

Allow browser location access on localhost or HTTPS. Gather sends the device coordinates to Google Maps for the lookup, then lets you review the street address and add unit details before saving. Without the key or a matching result, use the captured coordinates and enter the street address manually. You can also enter both the address and coordinates by hand.

## Complete order walkthrough

1. Sign in as a customer. On **Order food**, search or filter restaurants, open a menu, customize a dish, and add it to your basket. Add dishes from two nearby restaurants to see how the basket groups them.
2. Review quantities, fees and totals. Enter a delivery address and coordinates near central Ho Chi Minh City (the seed locations are around District 1). Try `WELCOME10` or `FREESHIP`. Server quoting and checkout revalidate prices, availability, acceptance, distance and totals.
3. Choose COD or online. Online checkout opens a clearly labelled **sandbox** page to simulate success or failure. Failed payment can be retried; idempotency keys prevent duplicate orders.
4. In independent browser profiles, sign into the restaurant workspaces. Accept, prepare and mark each portion ready using its owning account. Separate profiles keep roles signed in independently.
5. Open the driver workspace, go online, grant location access, accept an offer, and confirm each pickup in order after the restaurant is ready. Complete after all pickups, confirming collected cash for COD. Declined offers are reassigned when another eligible driver is available.
6. Watch the customer timeline/map update. After delivery, review each restaurant and the driver. Check restaurant/admin reports, run reconciliation and mark a settlement paid.

Dispatch uses geographic distance for nearby-driver selection and pickup sequencing, rather than live road/traffic routing. Configurable defaults: **5 km between grouped restaurants**, **15 km dispatch radius**, **12,000₫ base + 4,000₫/km delivery per restaurant**, **10% restaurant commission**. The report does not supply those numeric values. Admins can change them.

Unanswered driver offers expire after 60 seconds and are reconsidered on the 30-second dispatch sweep. A driver cannot accept an expired/reassigned offer.

One restaurant's rejection removes/refunds only that portion; remaining portions can continue. Incident reporting exposes admin cancellation/refund/retry decisions. Refund and settlement records do not move real money in this sandbox.

## API and verification

[API contract](docs/api-contract.md) describes routes and JSON. The OpenAPI explorer is `/docs` and its schema `/openapi.json`; sign in through the same-origin website first. Signed callbacks use `PAYMENT_CALLBACK_SECRET` (alias `PAYMENT_WEBHOOK_SECRET`). Sandbox actions are restricted to the owning customer. Full card numbers/CVV are never collected or stored.

[Requirements coverage](docs/requirements.md) maps every FR01–FR15, NFR01–NFR10, QĐ1–QĐ7 and use case. [Operations](docs/operations.md) covers deployment/recovery.

```sh
pytest -q
python scripts/load_test.py --demo --base-url http://127.0.0.1:8000 --users 200 --requests 2000 --output artifacts/load-test-authenticated.json
```

`pytest -q` uses a disposable SQLite database and skips PostgreSQL concurrency checks. For PostgreSQL acceptance, create a separate database whose name ends in `_test` and run, adjusting the connection details:

```sh
TEST_DATABASE_URL='postgresql+psycopg://gather:your-local-password@localhost:5432/gather_test' pytest -q
```

The suite creates/drops its test schema. Its guard rejects a PostgreSQL database name without the `_test` suffix. Never point it at an application database. Recorded validation and measured catalog latency are in [verification](docs/verification.md).

The load test signs in once as a customer, then exercises restaurant discovery, menu listing and a restaurant menu with up to 200 concurrent clients sharing that session. Login and warm-up are excluded from timing. `--demo` uses the seeded customer and default demo password. For a dedicated customer, pass `--email` or set `GATHER_LOAD_TEST_EMAIL`; the script prompts for the password. Set `GATHER_LOAD_TEST_PASSWORD` for non-interactive runs or if the demo account uses a customized password. Use HTTPS when testing a non-local server. The test reports failures and per-endpoint p95, failing if any exceeds 2 seconds. Retain the JSON with server specifications.

## Operations

```sh
scripts/backup.sh
scripts/install_backup_cron.sh
scripts/restore.sh /absolute/path/gather-backup.dump --yes-erases-current-data
```

The opt-in cron installer schedules backup at **02:00 host-time**; run it on the permanent Docker host. Copy dumps to encrypted off-host storage and rehearse recovery. The procedures target **RPO 24h / RTO 4h**, contingent on monitored successful backups and measured restore drills.

`ENABLE_SCHEDULER=true` checks due reconciliation every 30 seconds using **Sunday 23:59 Asia/Ho_Chi_Minh**. Unique settlement/source records prevent repeated accounting; admin can rerun due periods after downtime. Marking paid records an accounting action, not a bank transfer.

For public HTTPS, configure a real domain and production settings, then enable optional Caddy using [the deployment instructions](docs/operations.md#https-deployment). Local HTTP is for development. GPS on public hosts needs HTTPS. A single Compose host does **not** establish 99.5% availability; production needs monitoring, redundancy, off-host backups and a real payment provider.

## Layout

| Location | Purpose |
| --- | --- |
| `main.py`, `api/` | Startup, HTML routes, API and access checks |
| `models/`, `database/` | PostgreSQL schema, constraints, initialization |
| `services/` | Pricing, states, dispatch, payments, reports, settlements |
| `forms/`, `properties/`, `utilities/` | Validation, settings, security |
| `controls/`, `asset/` | Responsive HTML, JS, CSS, local Bootstrap |
| `scripts/`, `ops/` | Setup, backup, recovery, load testing, TLS |
| `tests/`, `docs/` | Automated checks, contract and runbooks |

Jira/Scrum assignments and UML figures in the report are project context, reflected in the actor boundaries and parent/suborder data model. They do not authorize accessing Jira or messaging the authors. Ingredient inventory, detailed kitchen production, payroll and fleet management remain outside scope.
