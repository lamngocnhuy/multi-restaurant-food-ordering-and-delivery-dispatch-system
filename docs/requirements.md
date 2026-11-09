# Requirements traceability

Source: all 29 pages of **Báo cáo thực hành lab 03 (2).pdf**, especially requirements (pp. 12–15), use cases (pp. 16–18), business rules (pp. 18–21), constraints (pp. 21–22), and UML descriptions (pp. 22–28). Jira assignments/team reports describe development process, not runtime commands.

The implementation uses Python/FastAPI/HTML/Bootstrap/JavaScript/PostgreSQL. These tables map implementation to acceptance checks. Deployment targets require operational evidence; configuration does not establish an SLA or real gateway integration.

## Functional requirements

| ID | Implementation | Acceptance check |
| --- | --- | --- |
| FR01 | Search/filter restaurant catalog and menus | Search restaurant/dish, filter category, open a menu |
| FR02 | Dish detail: image, description, price and availability | Inspect detail; sold-out items cannot enter cart |
| FR03 | Size/sugar/ice, multiple priced toppings, notes/defaults | Verify options and surcharge; reject undefined options |
| FR04 | Persisted customer cart with per-line customization | Add different customizations; reload and inspect |
| FR05 | One cart grouped by restaurant; parent and separate suborders | Checkout two nearby restaurants; verify two suborders |
| FR06 | Server totals, promotions and per-restaurant delivery | Verify items+fees−discount and invalid promo error |
| FR07 | Delivery details, COD/online, immutable snapshot, idempotency | Repeat submission; verify one order; fail/retry online |
| FR08 | Restaurant menu, acceptance and preparation workspace | Owner accepts/rejects/prepares/marks ready only its portion |
| FR09 | Nearby available-driver selection/radius and pickup sequencing | Skip unavailable drivers; show pending dispatch without candidates |
| FR10 | Driver offer detail, acceptance, decline/reassignment and unanswered-offer expiry | Decline/expire then offer to another eligible driver; reject unrelated driver |
| FR11 | Periodic browser GPS with persisted coordinate timestamp | Grant GPS; inspect successive updates during active work |
| FR12 | Customer timeline/map polling and stale-position feedback | Advance states from another session; interrupt GPS and observe staleness |
| FR13 | Completion requires every ordered pickup and COD confirmation | Reject early completion; collect all stops and deliver |
| FR14 | Delivered restaurant/driver reviews, score/duplicate/owner checks | Reject pending/unowned/repeated/invalid-rating review |
| FR15 | Role-scoped dated revenue reports, history and settlements | Restaurant sees own data; admin sees all; other roles denied/audited |

Dispatch uses geographic pickup distance, not live road/traffic routing. GPS/map features depend on device permission, foreground execution, network and external map tiles, consistent with the report's stated dependencies.

## Non-functional requirements

| ID | Implementation and verification | Operational qualification |
| --- | --- | --- |
| NFR01 | `scripts/load_test.py --demo --users 200 --requests 2000`: signs in as a seeded customer, measures catalog/menu p95≤2s and failures, writes JSON evidence | Use a dedicated customer and representative data on intended hardware; code alone is not performance evidence |
| NFR02 | Driver location cadence 10s; tracking polls within 20s; persisted timestamps/stale feedback | Stable network and active permissioned browser required; background suspension prevents a hard mobile guarantee |
| NFR03 | TLS proxy config, production secure-cookie guard, hashed passwords, signed callbacks; no card/CVV fields | Enable HTTPS for public traffic; local HTTP is development; payments are sandbox |
| NFR04 | Session/role/ownership checks and forbidden-access audit logs | Retain logs; verify customer/driver report/admin/settlement requests return 403 |
| NFR05 | UUIDs, unique emails, restaurant dish codes, order/trip codes, callback references | Preserve PostgreSQL constraints across migrations |
| NFR06 | Server revalidation and recalculation, transactional idempotent checkout, callback replay protection | Exercise stale cart, duplicate requests, payment failure and partial rejection |
| NFR07 | Responsive Bootstrap catalog, navigation, cart and workspaces | Inspect 360/768/1280/1920px; confirm critical buttons and scrolling modals |
| NFR08 | Field validation and actionable business errors surfaced in UI | Test missing address, bad coordinates/options, unavailable dish and illegal state |
| NFR09 | Database-aware health, restart policies and monitoring/failover runbook | 99.5% monthly uptime requires measured hosting reliability; single-host Compose does not guarantee it |
| NFR10 | Daily dump/cron, verification, retention and transactional restore/runbook | RPO24h/RTO4h need monitored off-host backups and measured restore drills |

## Business rules

| Rule | Implementation | Acceptance check |
| --- | --- | --- |
| QĐ1 / QD1 | Unique restaurant dish code, required name/category, positive price, availability, protected deletion and acceptance toggle | Duplicate/zero-price errors; toggle sold out; recheck restaurant at checkout |
| QĐ2 / QD2 | Integer quantity 1–99; defined/default options; multiple surcharged toppings; note≤300 chars; confirmation | Verify `(base+extras)×quantity`; reject invalid quantity/options/length |
| QĐ3 / QD3 | Editable persisted multi-restaurant cart, fresh validation, separate delivery fees/suborders | Change price/availability after add; preserve checkout snapshots |
| QĐ4 / QD4 | Trip links driver/order/pickup suborders; full pickup and recipient details; eligible driver required | No delivery before acceptance; inspect all addresses, values and notes |
| QĐ5 / QD5 | Unique order, guarded states and event timeline; pending/accepted/preparing/ready/picking_up/delivering/delivered/rejected/cancelled | Reject illegal transitions; final completion sets delivered |
| QĐ6 / QD6 | Single invoice, restaurant allocations, per-restaurant fees, promos, online transaction and COD allocations | Parent reconciles to suborders; rejection credits exact portion/COD |
| QĐ7 / QD7 | Sunday23:59 Vietnam reconciliation; restaurant less commission; driver fees−COD; signed values and pending/paid; unique sources | Rerun without duplication; verify online/COD amounts and payment marking |

Numeric distance/fee/commission/promotion values are configurable implementation choices because the report gives no constants. One multi-stop trip can serve the active portions; every suborder remains linked to its restaurant/pickup. Money and selected options become immutable order snapshots.

## Use cases and alternatives

| Use case | Application behavior |
| --- | --- |
| UC01 | Shared sign-in page for four roles, customer registration, and role-specific entry after authentication |
| UC02 | `/restaurant` menu and sold-out/acceptance controls |
| UC03 | Persistent cart drawer with quantity/options/removal |
| UC04 | Checkout, distance/availability rejection, failed payment/retry, partial rejection |
| UC05 | Owner-only sandbox and signed payment callback/replay protection |
| UC06 | Restaurant accepted→preparing→ready, or rejected |
| UC07 | Eligible driver dispatch, admin radius configuration and retry |
| UC08 | `/driver` offers, decline/reassign, sequential pickups, incident/admin resolution |
| UC09 | `/orders/{id}` timeline/map/freshness |
| UC10 | Driver history, fees and COD totals |
| UC11 | Delivered-order restaurant/driver reviews |
| UC12 | Restaurant/admin dated revenue reports and history |

UC08's unreachable customer alternative records an incident and exposes admin cancellation/refund/retry, preventing a driver from silently marking an unsuccessful delivery completed. Refund/settlement records require an external provider for real money movement.

## Architecture and scope

The report's `Customer → Cart → CartItem`, `Order → SubOrder → OrderItem`, `Restaurant → MenuItem`, `Payment → Order`, and `Driver → Trip → Order` relationships are persisted with foreign keys and uniqueness constraints. The cart is represented by the customer's cart items. UI, API, validation, database, business services and environment configuration are separated in repository folders.

Customer, restaurant, driver and admin are implemented; accounting is available to admin. External payment is a signed sandbox adapter. API ownership is checked separately for every restaurant/customer/driver resource. Ingredient stock, detailed cooking operations, payroll and fleet management remain out of scope. Jira/Scrum artifacts are project management context, not required website integrations.

## Repeatable acceptance walkthrough

Use separate browser profiles and a dedicated test database. Never reset a live database for demonstration.

1. Discover/filter and customize dishes from two nearby restaurants. Edit quantities/options/notes; inspect delivery allocations.
2. Try stale prices, sold-out items, restaurant pause, far-apart restaurants, bad coordinates and promotions; verify actionable rejection without duplicate/charged orders.
3. Checkout COD and online; repeat idempotency key; simulate success/failure/retry/replayed callback. Verify invoice and allocations.
4. Accept one portion and reject another; verify its exact refund/COD credit. Attempt cross-owner changes and forbidden reports/admin access; inspect audit logs.
5. Bring two drivers online, decline/reassign and accept. Try early/out-of-order pickups; then collect all, observe GPS, confirm COD and deliver. On another order report an incident and resolve as admin.
6. Check reviews, driver history, restaurant-scoped reports, admin dates/totals, weekly settlement signs, rerun uniqueness and paid marking.
7. Retain 200-user load JSON, inspect responsive layouts, restore a backup into an isolated database and record RTO. Verify HTTPS/external uptime monitoring before claiming production NFR targets.
