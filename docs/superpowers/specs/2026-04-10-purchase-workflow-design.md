# Purchase Workflow Enhancement — Design Spec

**Date:** 2026-04-10
**Module:** `co_warehouse_extended` (extension)
**Odoo Version:** 19.0

---

## 1. Overview

Extend the existing `co_warehouse_extended` module to cover a complete procurement workflow: product requests from users, stock availability checks with configurable auto-split, N-level purchase approval, multi-criteria supplier evaluation, quotation comparison, partial receipt tracking, and automatic journal entry generation.

---

## 2. Models

### 2.1 `co.product.request` (New)

User-facing product request — the workflow entry point.

**Fields:**

| Field | Type | Description |
|---|---|---|
| name | Char | Auto-generated sequence (PR/YYYY/NNNNN) |
| requester_id | Many2one(res.users) | Requesting user (default: current) |
| department_id | Many2one(hr.department) | Requester's department |
| company_id | Many2one(res.company) | Company |
| warehouse_id | Many2one(stock.warehouse) | Source warehouse |
| date_request | Date | Request date (default: today) |
| line_ids | One2many(co.product.request.line) | Requested products |
| state | Selection | draft / stock_check / splitting / processed / done / cancel |
| picking_ids | Many2many(stock.picking) | Generated internal transfers |
| purchase_request_id | Many2one(co.purchase.request) | Generated purchase request |
| notes | Text | Free-text notes |

**States:**

1. `draft` — user adds product lines
2. `stock_check` — system checks availability per line
3. `splitting` — partial stock + "user decides" config → waits for user to adjust split
4. `processed` — transfer and/or purchase request generated
5. `done` — all transfers received and/or PO fulfilled
6. `cancel` — cancelled by user

**Actions:**

- `action_check_availability()` — queries `product.product.qty_available` for the selected warehouse, classifies each line, transitions to `stock_check` or `splitting`
- `action_confirm_split()` — if in `splitting`, user confirms qty_to_transfer/qty_to_purchase per line
- `action_process()` — generates stock.picking for transfer lines and co.purchase.request for purchase lines, transitions to `processed`

### 2.2 `co.product.request.line` (New)

**Fields:**

| Field | Type | Description |
|---|---|---|
| request_id | Many2one(co.product.request) | Parent request |
| product_id | Many2one(product.product) | Product |
| qty_requested | Float | Quantity requested |
| uom_id | Many2one(uom.uom) | Unit of measure |
| qty_available | Float | Computed: current stock in warehouse |
| qty_to_transfer | Float | Qty to fulfill from stock |
| qty_to_purchase | Float | Qty to purchase externally |
| line_state | Selection | available / partial / unavailable (computed) |

### 2.3 `co.purchase.approval.level` (New)

Configurable N-level approval tiers.

**Fields:**

| Field | Type | Description |
|---|---|---|
| company_id | Many2one(res.company) | Company |
| department_id | Many2one(hr.department) | Department (blank = company-wide fallback) |
| sequence | Integer | Order of approval |
| name | Char | Level name (e.g., "Manager", "Director") |
| min_amount | Float | Minimum amount for this level |
| max_amount | Float | Maximum amount (0 = unlimited) |
| currency_id | Many2one(res.currency) | Currency |
| approver_ids | Many2many(res.users) | Users who can approve at this level |

**Lookup logic:**

1. Find levels matching company + department + amount range, ordered by sequence
2. If no department-specific levels found, fall back to company-wide levels (department_id = False)
3. If no levels found at all, request is auto-approved

### 2.4 `co.purchase.approval.line` (New)

Tracks each approval step on a purchase request.

**Fields:**

| Field | Type | Description |
|---|---|---|
| purchase_request_id | Many2one(co.purchase.request) | Parent purchase request |
| approval_level_id | Many2one(co.purchase.approval.level) | Approval level |
| sequence | Integer | Related to level sequence |
| approver_id | Many2one(res.users) | User who actually approved/rejected |
| date | Datetime | Approval/rejection timestamp |
| state | Selection | pending / approved / rejected |
| notes | Text | Approver comments |

### 2.5 `co.supplier.score` (New)

Multi-criteria supplier scoring.

**Fields:**

| Field | Type | Description |
|---|---|---|
| partner_id | Many2one(res.partner) | Supplier |
| product_category_id | Many2one(product.category) | Product category |
| company_id | Many2one(res.company) | Company |
| score_price | Float | Price competitiveness (0–100) |
| score_delivery | Float | On-time delivery rate (0–100) |
| score_quality | Float | Quality pass rate (0–100) |
| score_compliance | Float | Order fulfillment rate (0–100) |
| weight_price | Float | Weight for price (default 40) |
| weight_delivery | Float | Weight for delivery (default 25) |
| weight_quality | Float | Weight for quality (default 20) |
| weight_compliance | Float | Weight for compliance (default 15) |
| total_score | Float | Computed weighted average |
| last_updated | Datetime | Last recalculation |

**Score computation sources:**

- **Price:** historical PO line unit prices vs. average across suppliers for same product category
- **Delivery:** `(on-time pickings / total pickings)` — compare scheduled_date vs. date_done on receipt pickings
- **Quality:** `(passed quality checks / total checks)` from stock.picking quality fields
- **Compliance:** `(sum qty_received / sum qty_ordered)` across POs

**Default weights** configurable per company in `res.config.settings`.

### 2.6 `co.quotation.comparison` (New)

Side-by-side quotation comparison view.

**Fields:**

| Field | Type | Description |
|---|---|---|
| purchase_request_id | Many2one(co.purchase.request) | Source purchase request |
| rfq_ids | One2many(purchase.order) | Draft POs (RFQs) created for comparison |
| recommended_rfq_id | Many2one(purchase.order) | Computed: highest-scoring RFQ |
| state | Selection | draft / compared / selected |

**Comparison data (computed per RFQ):**

- Supplier name, total quoted price, estimated delivery lead time, supplier total_score, combined ranking

**Actions:**

- `action_accept_recommendation()` — confirms recommended RFQ, cancels others
- `action_select_manual(rfq_id)` — confirms user-chosen RFQ, cancels others

### 2.7 Extensions to Existing Models

#### `co.purchase.request` (Extended)

New fields:

| Field | Type | Description |
|---|---|---|
| product_request_id | Many2one(co.product.request) | Source product request |
| estimated_amount | Float | Computed total of lines × estimated price |
| approval_line_ids | One2many(co.purchase.approval.line) | Approval tracking |
| approval_state | Selection | no_approval / pending / approved / rejected (computed) |
| supplier_count | Integer | Number of top suppliers to request quotes from (default from company settings) |
| comparison_id | Many2one(co.quotation.comparison) | Quotation comparison |

Extended states: draft → submitted → pending_approval → approved → rfq_sent → quotation_compared → po_created → done / rejected / cancel

New actions:

- `action_submit()` — computes estimated amount, creates approval lines, transitions to pending_approval (or approved if auto-approved)
- `action_approve()` — called by approver, advances approval; if all levels approved, triggers supplier evaluation
- `action_reject()` — rejects request
- `action_request_quotations()` — scores suppliers, creates RFQs for top X, creates comparison record
- `action_create_purchase_order()` — from selected RFQ, confirms PO

#### `purchase.order` (Extended)

New fields:

| Field | Type | Description |
|---|---|---|
| fulfillment_pct | Float | Computed: (qty_received_total / qty_total) × 100 |
| fulfillment_state | Selection | pending / partial / complete |
| purchase_request_id | Many2one(co.purchase.request) | Traceability link |

Fulfillment recomputed on every linked picking validation.

#### `stock.picking` (Extended)

New fields:

| Field | Type | Description |
|---|---|---|
| purchase_request_id | Many2one(co.purchase.request) | Traceability link |

Override `button_validate()`:

- After standard validation, if picking is a purchase receipt:
  - Create `account.move` with: debit Inventory account, credit Accounts Payable, tax lines
  - Use product cost price × received qty
  - Auto-post the journal entry
  - Link to picking and PO
- If company setting prefers vendor-bill flow: call `po.action_create_invoice()` instead (existing behavior)
- Update PO fulfillment_pct

#### `res.company` (Extended)

New fields:

| Field | Type | Description |
|---|---|---|
| purchase_split_mode | Selection | auto / manual — how to handle partial stock availability |
| default_supplier_count | Integer | Default number of suppliers for RFQs (default: 3) |
| supplier_weight_price | Float | Default price weight (default: 40) |
| supplier_weight_delivery | Float | Default delivery weight (default: 25) |
| supplier_weight_quality | Float | Default quality weight (default: 20) |
| supplier_weight_compliance | Float | Default compliance weight (default: 15) |
| purchase_journal_mode | Selection | auto_entry / vendor_bill — journal creation mode on receipt |

#### `stock.warehouse` (Extended)

New fields:

| Field | Type | Description |
|---|---|---|
| purchase_split_mode | Selection | auto / manual / company_default — override per warehouse |

#### `res.config.settings` (Extended)

Expose company-level purchase settings in Settings UI: split mode, default supplier count, supplier scoring weights, journal creation mode.

---

## 3. Security & Access

- `co_purchase_request_user` — can create product requests, view own requests
- `co_purchase_request_manager` — can view all requests, configure approval levels
- `co_purchase_approver` — can approve/reject (dynamically checked against approval_level.approver_ids)
- Existing `purchase.group_purchase_manager` used for PO-level operations

---

## 4. Views

- **Product Request:** form (wizard-like with availability results), tree, kanban by state
- **Purchase Request:** extended form with approval timeline widget, supplier evaluation tab
- **Approval Levels:** tree + form (under Settings → Purchase)
- **Supplier Scores:** tree + form, with "Recalculate Scores" button
- **Quotation Comparison:** form with embedded comparison table, recommendation highlight, action buttons
- **Purchase Order:** extended form with fulfillment progress bar
- **Settings:** new "Purchase Workflow" section in res.config.settings

---

## 5. Menu Structure

Under **Purchase** menu:

- Product Requests (new)
- Purchase Requests (existing, enhanced)
- Quotation Comparisons (new)
- Supplier Scores (new)
- Configuration → Approval Levels (new)

---

## 6. Sequences & Data

- `co.product.request` sequence: PR/YYYY/NNNNN
- Default approval levels: none (must be configured per company)
- Default supplier scoring weights: 40/25/20/15

---

## 7. Out of Scope

- Automated supplier score recalculation via cron (manual trigger only for v1)
- Multi-currency quotation comparison (uses PO currency, single currency per comparison)
- Integration with external supplier portals
- Quality management module integration (uses existing stock.picking quality fields only)
