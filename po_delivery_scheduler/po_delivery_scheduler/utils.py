# Copyright (c) 2026, CAF and Contributors
# See license.txt

"""Shared helpers for the PO Delivery Scheduler app."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

# Tolerance used when comparing float quantities; quantities are stored with
# 6 decimal places, so anything inside this band is considered equal.
EPS = 1e-6

SCHEDULE_STATUSES = [
	"Planned",
	"Confirmed",
	"Partially Received",
	"Received",
	"Overdue",
	"Cancelled",
]

PLAN_STATUSES = ["Draft", "Active", "Completed", "Cancelled"]

# Delivery status precedence (highest wins):
#   1. Cancelled          - the schedule was cancelled
#   2. Received           - received_qty >= scheduled_qty
#   3. Partially Received - 0 < received_qty < scheduled_qty
#   4. Overdue            - nothing received and the scheduled date has passed
#   5. Confirmed          - supplier confirmed but date is still in the future
#   6. Planned            - anything else
STATUS_PRECEDENCE = {
	"Cancelled": 1,
	"Received": 2,
	"Partially Received": 3,
	"Overdue": 4,
	"Confirmed": 5,
	"Planned": 6,
}


def get_plan_for_po(purchase_order: str) -> str | None:
	"""Return the PO Delivery Plan for a Purchase Order, if one exists."""
	return frappe.db.get_value("PO Delivery Plan", {"purchase_order": purchase_order})


def compute_schedule_status(
	cancelled: bool,
	received_qty: float,
	scheduled_qty: float,
	scheduled_date,
	confirmation_status: str,
	today=None,
) -> str:
	"""Derive the delivery status from authoritative snapshot values.

	This function never trusts a client-submitted status value; it recomputes
	from the supplied authoritative values (which callers load from the DB).
	"""
	if cancelled:
		return "Cancelled"

	received = flt(received_qty)
	scheduled = flt(scheduled_qty)

	if scheduled > 0 and received >= scheduled - EPS:
		return "Received"

	if received > EPS:
		return "Partially Received"

	today = today or nowdate()
	if scheduled_date and getdate(scheduled_date) < getdate(today):
		return "Overdue"

	if confirmation_status == "Confirmed":
		return "Confirmed"

	return "Planned"


def compute_plan_status(plan, today=None) -> str:
	"""Derive the PO Delivery Plan status from its schedules.

	Used for housekeeping display only; the real lifecycle is enforced in the
	DocType controllers.
	"""
	if plan.get("status") == "Cancelled":
		return "Cancelled"

	schedules = frappe.db.get_all(
		"PO Delivery Schedule",
		filters={"delivery_plan": plan.get("name")},
		fields=["cancelled", "status"],
	)
	if not schedules:
		return "Draft"

	if all(row.cancelled or row.status == "Received" for row in schedules):
		return "Completed"

	return "Active"


def set_plan_status(plan_name: str) -> None:
	"""Persist the computed plan status on the document."""
	plan = frappe.get_doc("PO Delivery Plan", plan_name)
	plan.db_set("status", compute_plan_status(plan))
	return plan