# PO Delivery Scheduler

> Schedule, track and reconcile **multiple partial deliveries against a single Purchase Order** — natively inside ERPNext v15.

[![ERPNext](https://img.shields.io/badge/ERPNext-v15-blue)](https://erpnext.com)
[![Frappe](https://img.shields.io/badge/Frappe-v15-0089ff)](https://frappeframework.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](license.txt)

---

## The problem this app solves

Out of the box, ERPNext only understands **one delivery per Purchase Order item**:

- A PO line has a single `qty`, a single `schedule_date`, and a single `delivery_date`.
- If a supplier ships a purchase in **several consignments** (e.g. 100 units now, 60 next week, 40 the week after), there is **nowhere to record that plan**.
- You cannot see *how much is expected, when, and how much is still outstanding* per delivery.
- There is no way to warn a buyer that a promised delivery is **overdue** or **due soon**.
- Receiving staff have no structured way to say *"this goods-receipt line is fulfilling the 2nd scheduled delivery"*.

Teams end up tracking this in spreadsheets, losing visibility between planning and receiving.

**PO Delivery Scheduler** adds a first-class scheduling layer on top of a Purchase Order:

- A **PO Delivery Plan** splits a Purchase Order into as many dated deliveries as you need.
- A **PO Delivery Schedule** is one such delivery (date + quantity + UOM + status).
- Receiving lines can be **linked to the schedule they fulfil**, so received / outstanding quantities and status are computed automatically.

Nothing in ERPNext core is modified — the app only adds documents, a custom field, a hook, a report and dashboards.

---

## Features

| Area | What you get |
| --- | --- |
| **Delivery planning** | Create a plan per Purchase Order and split the ordered quantity into multiple dated deliveries. |
| **Over-scheduling guard** | Total scheduled quantity can never exceed the ordered quantity (row-locked to prevent race conditions). |
| **Receipt linking** | A `Delivery Schedule` field on every Purchase Receipt Item links a receipt line to the delivery it fulfils. |
| **Automatic tracking** | `received_qty`, `outstanding_qty` and `status` are recomputed from submitted receipts (returns are subtracted). |
| **Supplier confirmation** | Track confirmation status and the supplier-confirmed date per delivery. |
| **Calendar view** | A colour-coded calendar of all scheduled deliveries (by status). |
| **Dashboard** | Number cards (scheduled / received / outstanding / overdue) and trend + status charts on the "PO Delivery Scheduler" workspace. |
| **Report** | **PO Delivery Overview** script report across all schedules with filters. |
| **Reminders** | A daily scheduler job emails the responsible user about upcoming and overdue deliveries (once per day). |
| **Permissions** | Ships a `PO Delivery Manager` role plus sensible access for Purchase / Stock roles. |

---

## Requirements

- **Frappe Framework v15**
- **ERPNext v15** (declared as a required app)
- Tested against Frappe `15.74` and ERPNext `15.71`.

---

## Installation

```bash
cd frappe-bench

# 1. Fetch the app
bench get-app https://github.com/hisham733/po_delivery_scheduler

# 2. Install it on your site
bench --site your.site.com install-app po_delivery_scheduler

# 3. Sync doctypes, fixtures, dashboards and rebuild assets
bench --site your.site.com migrate
bench build --app po_delivery_scheduler

# 4. Restart
bench restart
```

`bench migrate` takes care of everything else automatically:

- creates the **PO Delivery Plan** and **PO Delivery Schedule** doctypes,
- installs the **`Delivery Schedule`** custom field on Purchase Receipt Item (via fixtures),
- creates the **`PO Delivery Manager`** role,
- syncs the **PO Delivery Overview** report,
- syncs the number cards, dashboard charts, the **PO Delivery** dashboard and the **PO Delivery Scheduler** workspace,
- registers the daily reminder job.

> The app must be installed on a site that already has **ERPNext** installed.

---

## Usage

### 1. Plan deliveries for a Purchase Order

Open a **submitted** Purchase Order and click **Manage Delivery Schedule** (top-right).

- This creates (or opens) the linked **PO Delivery Plan** for that PO.
- The plan shows a grid of all schedules for the order, with planned vs. received quantities.
- Use **Add Schedule Entry** to add a dated delivery. The item picker is scoped to the PO's items.
- **Recalculate** refreshes received/outstanding quantities; **Cancel Plan** cancels the plan and its open schedules.

### 2. Add and confirm schedules

Each **PO Delivery Schedule** records:

| Field | Meaning |
| --- | --- |
| Scheduled Delivery Date | When the quantity is expected |
| Scheduled Quantity / UOM | How much is expected (UOM must match the PO item) |
| Status | `Planned → Confirmed → Partially Received → Received`, or `Overdue` / `Cancelled` |
| Confirmation Status | Supplier confirmation state + confirmed date |
| Received / Outstanding Qty | **Read-only**, recomputed from submitted receipts |

### 3. Receive against a schedule

When creating a **Purchase Receipt** for the PO, on each item row set the **Delivery Schedule** link
(shown only after the PO custom field is installed). The link is filtered to schedules that:

- belong to the same Purchase Order and item code,
- are not cancelled,
- are in a receivable state (`Planned`, `Confirmed`, `Partially Received`, `Overdue`).

On submit, the schedule's `received_qty`, `outstanding_qty` and `status` update automatically.
Cancelling or deleting the receipt rolls the quantities back. **Return receipts** are attributed to the
original schedule and subtracted.

### 4. Watch progress

- **Calendar** — open *PO Delivery Schedule → Calendar* (or the **Delivery Calendar** shortcut) for a colour-coded view of every scheduled delivery.
- **Dashboard** — open the **PO Delivery Scheduler** workspace in the sidebar for the number cards and charts.
- **Report** — run **PO Delivery Overview** for a filterable, flat table of all schedules.

### 5. Reminders

A daily scheduler job (`send_delivery_reminders`) emails the plan's **responsible user**
(`PO Delivery Plan.owner_user`) about deliveries that are **due soon**, **due today**, **overdue**, or whose
supplier-confirmed date has passed. Each schedule is reminded at most **once per calendar day**.
Suppliers are never emailed by this app. If email is not configured the job does not fail — the issue is
recorded in the schedule's `reminder_note` and written to the error log.

---

## Status reference

**PO Delivery Schedule**

| Status | Meaning |
| --- | --- |
| `Planned` | Scheduled, not yet confirmed by the supplier |
| `Confirmed` | Supplier confirmed the delivery |
| `Partially Received` | Some, but not all, of the scheduled quantity has been receipted |
| `Received` | Fully receipted |
| `Overdue` | Past the scheduled date and not fully received |
| `Cancelled` | The schedule was cancelled |

**PO Delivery Plan**: `Draft`, `Active`, `Completed` (all schedules closed), `Cancelled`.

Status precedence when deriving a schedule's state:
`Cancelled > Received > Partially Received > Overdue > Confirmed > Planned`.

---

## Permissions

The app creates a **`PO Delivery Manager`** role with full access to plans and schedules.
Purchase Manager, Stock Manager and System Manager also have full access; Purchase User and Stock User
get read access. Assign the `PO Delivery Manager` role to buyers/schedulers who should edit plans.

---

## Architecture

```
po_delivery_scheduler/
└── po_delivery_scheduler/
    ├── doctype/
    │   ├── po_delivery_plan/        # PODP-.#####  (the plan, holds the schedule grid UI)
    │   └── po_delivery_schedule/    # PODS-.#####  (one dated delivery; calendar view)
    ├── report/po_delivery_overview/ # Script Report
    ├── api.py                       # whitelisted UI methods + calendar events
    ├── receipt_integration.py       # Purchase Receipt validate / on_submit / on_cancel / on_trash
    ├── purchase_order_events.py     # Purchase Order validate / on_cancel
    ├── reminders.py                 # daily reminder job
    ├── utils.py                     # status & quantity computation
    ├── workspace/ number_card/ dashboard_chart/ ..._dashboard/  # Desk workspace + dashboard
    ├── fixtures/                    # custom field + role
    └── tests/                       # unit tests (22)
```

**Hooks** (`hooks.py`)

- `doc_events` — Purchase Receipt (`validate`, `on_submit`, `on_cancel`, `on_trash`) and Purchase Order (`validate`, `on_cancel`).
- `scheduler_events.daily` — `reminders.send_delivery_reminders`.
- `doctype_js` — adds the **Manage Delivery Schedule** button to Purchase Order and the schedule-link filter to Purchase Receipt.
- `fixtures` — Custom Field + Role.
- `required_apps = ["erpnext"]`.

---

## Development

```bash
# Run the test suite
bench --site your.site.com run-tests --app po_delivery_scheduler

# If your site lacks the ERPNext test company/fiscal-year fixtures, add:
bench --site your.site.com run-tests --app po_delivery_scheduler --skip-test-records
```

The test suite covers quantity/status derivation, over-scheduling, duplicate guards, receipt progression,
returns, plan lifecycle, PO-cancel cascade, reminders (idempotency and email-failure tolerance) and the report.

### Contributing

This app uses `pre-commit` for formatting and linting. Enable it with:

```bash
cd apps/po_delivery_scheduler
pre-commit install
```

Configured tools: ruff, eslint, prettier, pyupgrade.

---

## License

[MIT](license.txt)
