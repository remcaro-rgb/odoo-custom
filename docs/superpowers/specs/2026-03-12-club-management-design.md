# Social Country Club Management — Design Spec

**Date:** 2026-03-12
**Author:** Manuel Caro
**Status:** Draft

---

## Goal

Build a suite of Odoo 18.0 modules for managing a social country club, covering affiliate memberships, billing, golf, equestrian, tennis, and events. All modules available in English and Spanish.

---

## Module Architecture

```
club_core            ← foundation (affiliates, memberships, billing)
├── club_golf        ← depends on club_core
├── club_equestrian  ← depends on club_core
├── club_tennis      ← depends on club_core
└── club_events      ← depends on club_core
```

All modules live in `custom-addons/` in the `remcaro-rgb/odoo-custom` repo. Each follows standard Odoo 18.0 addon structure.

**Odoo dependencies leveraged:**
- `account` — invoicing and billing
- `portal` — member self-service portal
- `event` — base for club_events
- `mail` — chatter, notifications, automated emails

---

## Prototype Build Phases

| Phase | Modules | Key Deliverables |
|---|---|---|
| 1 | `club_core` | Affiliate registration, membership plans, billing, portal |
| 2 | `club_golf` | Tee times, handicap, scorecards, caddies, carts, bags |
| 3 | `club_equestrian` + `club_tennis` | Stable/horse mgmt, arena/court bookings, rankings |
| 4 | `club_events` | Internal/external events, registration, payments |

Each phase delivers installable module(s) with security groups, demo data, tests, and Spanish translations.

---

## Standard Module Structure (all modules)

```
club_<name>/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── <model>.py (one file per model)
├── views/
│   └── <model>_views.xml
├── security/
│   ├── ir.model.access.csv
│   └── club_security.xml
├── data/
│   └── demo_data.xml
├── i18n/
│   └── es.po
└── tests/
    └── test_<feature>.py
```

---

## Phase 1: `club_core`

### Models

#### `club.affiliate` (extends `res.partner`)
| Field | Type | Description |
|---|---|---|
| `membership_type` | Selection | individual / family_primary / family_dependent / corporate_admin / corporate_employee |
| `membership_ids` | One2many | → `club.membership` |
| `family_group_id` | Many2one | → `club.family.group` (if dependent) |
| `corporate_group_id` | Many2one | → `club.corporate.group` (if employee) |
| `affiliate_number` | Char | Auto-generated unique club ID |
| `membership_status` | Computed | active / suspended / expired (from active membership) |
| `photo` | Binary | Member photo |

#### `club.membership.plan`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Plan name (e.g. "Individual Anual") |
| `fee` | Float | Fee amount |
| `billing_period` | Selection | monthly / annual |
| `grace_period_days` | Integer | Days after expiry before suspension |
| `late_fee_amount` | Float | Late fee charged after grace period |
| `golf_access` | Boolean | Includes golf access |
| `equestrian_access` | Boolean | Includes equestrian access |
| `tennis_access` | Boolean | Includes tennis access |
| `product_id` | Many2one | → `product.product` (for invoicing) |

#### `club.membership`
| Field | Type | Description |
|---|---|---|
| `affiliate_id` | Many2one | → `club.affiliate` |
| `plan_id` | Many2one | → `club.membership.plan` |
| `start_date` | Date | Membership start |
| `end_date` | Date | Membership end (computed from period) |
| `status` | Selection | draft / active / suspended / expired / cancelled |
| `invoice_ids` | One2many | → `account.move` |
| `notes` | Text | Staff notes |

#### `club.family.group`
| Field | Type | Description |
|---|---|---|
| `primary_member_id` | Many2one | → `club.affiliate` |
| `dependent_ids` | One2many | → `club.affiliate` |
| `billing_affiliate_id` | Many2one | → `club.affiliate` (who receives invoices) |

#### `club.corporate.group`
| Field | Type | Description |
|---|---|---|
| `company_partner_id` | Many2one | → `res.partner` (company) |
| `admin_id` | Many2one | → `club.affiliate` (corporate admin) |
| `employee_ids` | One2many | → `club.affiliate` |
| `max_employees` | Integer | Maximum authorized members |

### Billing Logic
- On membership activation (`status` → `active`): auto-create `account.move` (invoice) using `plan.product_id`
- Daily cron (`ir.cron`): checks memberships expiring within 7 days → generates renewal invoice
- Late fee cron: after `end_date + grace_period_days` if invoice unpaid → add late fee line to invoice, set membership `status = suspended`
- On invoice payment confirmation → renew `end_date`, restore `status = active` if suspended

### Security Groups
| Group | Access |
|---|---|
| `club_core.group_club_admin` | Full access to all club models |
| `club_core.group_club_staff` | Read/write memberships, affiliates; no billing config |
| `club_core.group_club_member` | Portal: read own membership, invoices |

### Views
- Affiliate kanban + list + form (with membership history)
- Membership plan list + form
- Membership list + form with inline invoice list
- Family group form
- Corporate group form
- Dashboard: active members count, expiring this month, suspended

---

## Phase 2: `club_golf`

### Models

#### `club.golf.course`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Course name |
| `holes` | Integer | 9 or 18 |
| `par` | Integer | Course par |
| `slope_rating` | Float | WHS slope rating |
| `course_rating` | Float | WHS course rating |

#### `club.golf.tee.time`
| Field | Type | Description |
|---|---|---|
| `date` | Date | Round date |
| `time_slot` | Float | Time (e.g. 7.5 = 07:30) |
| `course_id` | Many2one | → `club.golf.course` |
| `affiliate_ids` | Many2many | → `club.affiliate` (max 4) |
| `guest_count` | Integer | Non-member guests |
| `caddie_id` | Many2one | → `club.golf.caddie` (optional) |
| `cart_id` | Many2one | → `club.golf.cart` (optional) |
| `bag_ids` | Many2many | → `club.golf.bag` |
| `status` | Selection | available / booked / completed / cancelled |

#### `club.golf.caddie`
| Field | Type | Description |
|---|---|---|
| `partner_id` | Many2one | → `res.partner` |
| `employee_number` | Char | Club employee ID |
| `availability_ids` | One2many | → `club.golf.caddie.availability` |
| `tee_time_ids` | One2many | → `club.golf.tee.time` |

#### `club.golf.caddie.availability`
| Field | Type | Description |
|---|---|---|
| `caddie_id` | Many2one | → `club.golf.caddie` |
| `day_of_week` | Selection | Monday–Sunday |
| `time_from` | Float | Available from |
| `time_to` | Float | Available until |

#### `club.golf.cart`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Cart identifier/number |
| `cart_type` | Selection | rental / owned |
| `owner_id` | Many2one | → `club.affiliate` (if owned) |
| `status` | Selection | available / in_use / maintenance |
| `battery_level` | Integer | % charge (electric carts) |
| `maintenance_log` | Text | Maintenance notes |
| `tee_time_ids` | One2many | → `club.golf.tee.time` |

#### `club.golf.bag`
| Field | Type | Description |
|---|---|---|
| `tag_number` | Char | Bag tag/ID |
| `owner_id` | Many2one | → `club.affiliate` |
| `locker_number` | Char | Storage locker assignment |
| `status` | Selection | stored / with_member |
| `notes` | Text | Description / special instructions |

#### `club.golf.scorecard`
| Field | Type | Description |
|---|---|---|
| `tee_time_id` | Many2one | → `club.golf.tee.time` |
| `affiliate_id` | Many2one | → `club.affiliate` |
| `course_id` | Many2one | → `club.golf.course` |
| `date` | Date | Round date |
| `hole_1` … `hole_18` | Integer | Score per hole |
| `gross_score` | Integer | Computed: sum of holes |
| `course_handicap` | Integer | Computed from handicap index + course slope |
| `net_score` | Integer | Computed: gross − course_handicap |
| `score_differential` | Float | Computed: WHS formula |

#### `club.golf.handicap`
| Field | Type | Description |
|---|---|---|
| `affiliate_id` | Many2one | → `club.affiliate` |
| `handicap_index` | Float | Current WHS index (best 8 of last 20 differentials) |
| `revision_date` | Date | Last revision date |
| `history_ids` | One2many | → `club.golf.handicap.history` |

#### `club.golf.handicap.history`
| Field | Type | Description |
|---|---|---|
| `handicap_id` | Many2one | → `club.golf.handicap` |
| `date` | Date | Revision date |
| `handicap_index` | Float | Index at this revision |
| `scorecard_ids` | Many2many | Scorecards used in this calculation |

### Business Logic
- Tee time conflict detection: same time slot + course → validation error
- Caddie availability check on booking
- Cart availability check: rental carts from available pool; owned carts reserved for owner
- Bag check-out on tee time confirmation; check-in on completion
- WHS handicap: on scorecard save → compute `score_differential` = `(113 / slope_rating) × (gross_score − course_rating)`; recalculate `handicap_index` = average of best 8 from last 20 differentials × 0.96
- Views: calendar for tee times, graph for handicap trend, list for scorecards

---

## Phase 3a: `club_equestrian`

### Models

#### `club.horse`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Horse name |
| `breed` | Char | Breed |
| `color` | Char | Coat color |
| `birth_date` | Date | Date of birth |
| `owner_id` | Many2one | → `club.affiliate` |
| `registration_number` | Char | Club registration number (auto) |
| `stall_id` | Many2one | → `club.stall` (current assignment) |
| `photo` | Binary | Horse photo |

#### `club.stall`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Stall number/name |
| `barn_section` | Char | Barn/section label |
| `horse_id` | Many2one | → `club.horse` (current occupant) |
| `status` | Selection | vacant / occupied / maintenance |
| `notes` | Text | Special instructions |

#### `club.horse.feeding`
| Field | Type | Description |
|---|---|---|
| `horse_id` | Many2one | → `club.horse` |
| `feed_type` | Char | Feed name/type |
| `quantity` | Float | Amount |
| `unit` | Selection | kg / lbs / flakes |
| `schedule` | Selection | morning / afternoon / evening |
| `responsible_id` | Many2one | → `res.users` (staff) |
| `notes` | Text | Additional instructions |

#### `club.vet.record`
| Field | Type | Description |
|---|---|---|
| `horse_id` | Many2one | → `club.horse` |
| `date` | Date | Visit date |
| `vet_name` | Char | Veterinarian name |
| `procedure` | Text | Procedure / diagnosis |
| `next_visit_date` | Date | Next scheduled visit |
| `attachment_ids` | Many2many | → `ir.attachment` (documents) |

#### `club.arena`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Arena name |
| `arena_type` | Selection | dressage / jumping / outdoor / multipurpose |
| `capacity` | Integer | Max riders simultaneously |
| `status` | Selection | available / maintenance |

#### `club.equestrian.booking`
| Field | Type | Description |
|---|---|---|
| `arena_id` | Many2one | → `club.arena` |
| `affiliate_id` | Many2one | → `club.affiliate` |
| `horse_id` | Many2one | → `club.horse` |
| `date` | Date | Booking date |
| `time_slot` | Float | Start time |
| `duration` | Float | Hours (max 2) |
| `status` | Selection | booked / completed / cancelled |

### Business Logic
- Horse owner must be active affiliate
- Stall assignment: mutual update (horse.stall_id ↔ stall.horse_id); stall auto-freed on horse departure
- Arena conflict detection: same arena + overlapping time → validation error
- Vet next visit alert: daily cron checks `next_visit_date` within 7 days → post chatter message + email owner
- Daily feeding sheet: printable PDF report grouped by schedule (morning/afternoon/evening)

---

## Phase 3b: `club_tennis`

### Models

#### `club.tennis.court`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Court name/number |
| `surface` | Selection | clay / hard / grass / artificial |
| `indoor` | Boolean | Indoor or outdoor |
| `status` | Selection | available / maintenance |

#### `club.tennis.booking`
| Field | Type | Description |
|---|---|---|
| `court_id` | Many2one | → `club.tennis.court` |
| `affiliate_ids` | Many2many | → `club.affiliate` (max 4) |
| `date` | Date | Booking date |
| `time_slot` | Float | Start time |
| `duration` | Float | 1 or 2 hours |
| `caddie_id` | Many2one | → `club.tennis.caddie` (optional) |
| `status` | Selection | booked / completed / cancelled |

#### `club.tennis.caddie`
| Field | Type | Description |
|---|---|---|
| `partner_id` | Many2one | → `res.partner` |
| `employee_number` | Char | Club employee ID |
| `availability_ids` | One2many | → `club.tennis.caddie.availability` |
| `booking_ids` | One2many | → `club.tennis.booking` |

#### `club.tennis.caddie.availability`
| Field | Type | Description |
|---|---|---|
| `caddie_id` | Many2one | → `club.tennis.caddie` |
| `day_of_week` | Selection | Monday–Sunday |
| `time_from` | Float | Available from |
| `time_to` | Float | Available until |

#### `club.tennis.match`
| Field | Type | Description |
|---|---|---|
| `booking_id` | Many2one | → `club.tennis.booking` |
| `player_ids` | Many2many | → `club.affiliate` |
| `set_1_score` | Char | e.g. "6-4" |
| `set_2_score` | Char | |
| `set_3_score` | Char | (optional tiebreak) |
| `winner_id` | Many2one | → `club.affiliate` |
| `ranking_points` | Integer | Points awarded to winner |

#### `club.tennis.ranking`
| Field | Type | Description |
|---|---|---|
| `affiliate_id` | Many2one | → `club.affiliate` |
| `category` | Selection | men / women / junior / senior / mixed |
| `points` | Integer | Total ranking points |
| `rank` | Integer | Computed position in category |
| `matches_played` | Integer | Total matches recorded |
| `matches_won` | Integer | Total wins |

### Business Logic
- Court booking conflict detection: same court + overlapping time → validation error
- Caddie availability check on booking
- Match result recording: on save → update winner/loser ranking points (ELO-style delta)
- Rank recomputation: triggered after each match result; ranks all affiliates in category by points descending
- Leaderboard view: affiliates grouped by category, sorted by rank

---

## Phase 4: `club_events`

### Models

#### `club.event` (extends `event.event`)
| Field | Type | Description |
|---|---|---|
| `event_scope` | Selection | internal / external |
| `sport_category` | Selection | golf / equestrian / tennis / social / general |
| `member_only` | Boolean | Visible only to active affiliates |
| `member_price` | Float | Ticket price for affiliates |
| `public_price` | Float | Ticket price for external attendees |

#### `club.event.registration` (extends `event.registration`)
| Field | Type | Description |
|---|---|---|
| `affiliate_id` | Many2one | → `club.affiliate` (if member) |
| `attendee_type` | Selection | member / guest / public |
| `payment_status` | Selection | pending / paid / refunded |
| `payment_move_id` | Many2one | → `account.move` (invoice if paid) |

### Business Logic
- Internal events: restricted to active affiliates; registration free
- External events: public portal page; payment via Odoo payment acquirer
- Member discount: affiliates automatically assigned `member_price`; non-members get `public_price`
- Capacity enforcement: registration blocked when `seats_available = 0`
- On registration + payment confirmed → send confirmation email with event details and receipt
- On registration for internal event → send confirmation email

---

## Internationalization (all modules)

- All Python model fields use Odoo's `_()` translation wrapper for labels and error messages
- All XML views use standard Odoo translatable string patterns
- Each module ships `i18n/es.po` covering:
  - Field labels and help text
  - Menu item names
  - Button text and action names
  - Validation error messages
  - Email template bodies
- English (`en`) is the default; Spanish (`es`) available as selectable language per user

---

## Security Model (all modules)

| Group | Defined in | Access |
|---|---|---|
| Club Admin | `club_core` | Full CRUD on all club models |
| Club Staff | `club_core` | Read/write operations; no configuration |
| Club Member (portal) | `club_core` | Read own data; create bookings/registrations |
| Golf Staff | `club_golf` | CRUD on golf models |
| Equestrian Staff | `club_equestrian` | CRUD on equestrian models |
| Tennis Staff | `club_tennis` | CRUD on tennis models |
| Events Staff | `club_events` | CRUD on event models |

---

## Demo Data (all modules)

Each module ships `data/demo_data.xml` with:
- `club_core`: 10 individual affiliates, 2 family groups, 1 corporate group, 3 membership plans
- `club_golf`: 1 course, 5 tee times, 2 caddies, 4 carts, 5 bags, 3 scorecards, handicap records
- `club_equestrian`: 3 horses, 6 stalls, 1 arena, 3 bookings, 2 vet records
- `club_tennis`: 3 courts, 2 caddies, 5 bookings, 3 matches, ranking data
- `club_events`: 2 internal events, 1 external event with registrations

---

## Testing Strategy (all modules)

- Unit tests in `tests/test_<feature>.py` using `odoo.tests.common.TransactionCase`
- Each module tests:
  - Model constraints (e.g. tee time conflicts, stall double-assignment)
  - Business logic (billing cron, handicap calculation, ranking update)
  - Access rights (admin vs staff vs member)
- Tests run with: `docker compose exec odoo /odoo/odoo-bin test -d odoo --test-tags club`
