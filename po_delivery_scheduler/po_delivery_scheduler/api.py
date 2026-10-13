# Copyright (c) 2026, CAF and Contributors
# See license.txt

"""Whitelisted server methods used by the Desk UI."""

import frappe
from frappe import _
from frappe.utils import flt

from po_delivery_scheduler.po_delivery_scheduler.utils import get_plan_for_po


@frappe.whitelist()
def get_or_create_delivery_plan(purchase_order: str):
	"""Return the delivery plan for a Purchase Order, creating it if needed.

	Used by the "Manage Delivery Schedule" button on the Purchase Order form.
	Never creates a duplicate plan for the same Purchase Order.
	"""
	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("read")

	if existing := get_plan_for_po(purchase_order):
		plan = frappe.get_doc("PO Delivery Plan", existing)
		plan.check_permission("read")
		return plan

	if not frappe.has_permission("PO Delivery Plan", "create"):
		frappe.throw(_("You do not have permission to create a delivery plan."))

	plan = frappe.new_doc("PO Delivery Plan")
	plan.update(
		{
			"purchase_order": purchase_order,
			"supplier": po.supplier,
			"company": po.company,
			"owner_user": frappe.session.user,
		}
	)
	plan.insert(ignore_permissions=False)

	return plan


@frappe.whitelist()
def get_po_item_query(purchase_order: str, txt: str = None):
	"""Item picker for the plan's Add-Schedule dialog.

	Shopws the Item Code (plus item name) instead of the raw Purchase Order
	Item row name. Returns ``[{value: po_item_name, label: "ITEM CODE - name"}]``
	so the Autocomplete stores a valid Purchase Order Item reference while the
	user reads a meaningful label.
	"""
	po = frappe.get_cached_doc("Purchase Order", purchase_order)
	po.check_permission("read")

	rows = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": purchase_order},
		fields=["name", "item_code", "item_name"],
		order_by="idx asc",
		limit_page_length=0,
	)

	needle = (txt or "").strip().lower()
	out = []
	for r in rows:
		label = f"{r.item_code} - {r.item_name}"
		if needle and needle not in r.item_code.lower() and needle not in label.lower():
			continue
		out.append({"value": r.name, "label": label})
	return out


@frappe.whitelist()
def get_plan_schedules(delivery_plan: str):
	"""List the schedules of a plan for rendering on the plan form."""
	plan = frappe.get_doc("PO Delivery Plan", delivery_plan)
	plan.check_permission("read")

	return frappe.get_all(
		"PO Delivery Schedule",
		filters={"delivery_plan": delivery_plan},
		fields=[
			"name",
			"purchase_order",
			"purchase_order_item",
			"item_code",
			"item_name",
			"scheduled_date",
			"scheduled_qty",
			"uom",
			"confirmation_status",
			"supplier_confirmed_date",
			"received_qty",
			"outstanding_qty",
			"status",
			"cancelled",
			"cancellation_reason",
			"remarks",
		],
		order_by="scheduled_date asc, item_code asc",
	)


@frappe.whitelist()
def create_schedule_entry(
	delivery_plan: str,
	purchase_order_item: str,
	scheduled_date: str,
	scheduled_qty: float,
	supplier_confirmed_date: str = None,
	confirmation_status: str = None,
	remarks: str = None,
):
	"""Create a single schedule entry from the plan form dialog."""
	plan = frappe.get_doc("PO Delivery Plan", delivery_plan)
	plan.check_permission("read")

	if not frappe.has_permission("PO Delivery Schedule", "create"):
		frappe.throw(_("You do not have permission to create delivery schedules."))

	schedule = frappe.new_doc("PO Delivery Schedule")
	schedule.delivery_plan = delivery_plan
	schedule.purchase_order_item = purchase_order_item
	schedule.scheduled_date = scheduled_date
	schedule.scheduled_qty = flt(scheduled_qty)
	if confirmed_date := supplier_confirmed_date:
		schedule.supplier_confirmed_date = confirmed_date
		schedule.confirmation_status = confirmation_status or "Awaiting Confirmation"
	elif confirmation_status:
		schedule.confirmation_status = confirmation_status
	if remarks:
		schedule.remarks = remarks
	schedule.insert(ignore_permissions=False)

	return schedule


@frappe.whitelist()
def cancel_schedule(schedule_name: str, cancellation_reason: str = None):
	"""Cancel a schedule entry."""
	schedule = frappe.get_doc("PO Delivery Schedule", schedule_name)
	schedule.check_permission("write")

	plan = frappe.get_doc("PO Delivery Plan", schedule.delivery_plan)
	plan.check_permission("read")

	if plan.status == "Cancelled":
		frappe.throw(_("The delivery plan is cancelled; the schedule cannot be re-opened."))

	schedule.db_set(
		{
			"cancelled": 1,
			"cancellation_reason": cancellation_reason or schedule.cancellation_reason,
			"last_reminder_date": None,
			"reminder_note": None,
		},
		update_modified=True,
	)
	# db_set does not fire on_update, so recalculate explicitly.
	from po_delivery_scheduler.po_delivery_scheduler.receipt_integration import recalculate_schedule

	recalculate_schedule(schedule.name)
	return schedule


@frappe.whitelist()
def reopen_schedule(schedule_name: str):
	"""Re-open a cancelled schedule entry."""
	schedule = frappe.get_doc("PO Delivery Schedule", schedule_name)
	schedule.check_permission("write")

	plan = frappe.get_doc("PO Delivery Plan", schedule.delivery_plan)
	plan.check_permission("read")

	if plan.status == "Cancelled":
		frappe.throw(_("The delivery plan is cancelled; schedules cannot be re-opened."))
	if not schedule.cancelled:
		return schedule

	schedule.db_set(
		{
			"cancelled": 0,
			"cancellation_reason": None,
		},
		update_modified=True,
	)
	# Re-run full validation, including the over-scheduling check, since the
	# schedule is re-entering the active set.
	schedule.reload()
	schedule.validate()
	from po_delivery_scheduler.po_delivery_scheduler.receipt_integration import recalculate_schedule

	recalculate_schedule(schedule.name)
	return schedule


@frappe.whitelist()
def recalculate_plan(delivery_plan: str):
	"""Force a recalculation of every schedule on a plan."""
	plan = frappe.get_doc("PO Delivery Plan", delivery_plan)
	plan.check_permission("read")

	from po_delivery_scheduler.po_delivery_scheduler.receipt_integration import recalculate_schedule

	names = frappe.get_all(
		"PO Delivery Schedule", filters={"delivery_plan": delivery_plan}, pluck="name"
	)
	for name in names:
		recalculate_schedule(name)
	return {"recalculated": len(names)}


@frappe.whitelist()
def cancel_plan(delivery_plan: str):
	"""Cancel a delivery plan and every open schedule on it."""
	plan = frappe.get_doc("PO Delivery Plan", delivery_plan)
	plan.check_permission("write")

	plan.cancel_plan()
	return plan


@frappe.whitelist()
def activate_plan(delivery_plan: str):
	"""Activate a draft delivery plan (group operation for the plan form)."""
	plan = frappe.get_doc("PO Delivery Plan", delivery_plan)
	plan.check_permission("write")

	plan.activate()
	return plan


_CALENDAR_STATUS_COLORS = {
	"Planned": "#2490ef",
	"Confirmed": "#12b886",
	"Partially Received": "#f59f00",
	"Received": "#40c057",
	"Overdue": "#e03131",
	"Cancelled": "#adb5bd",
}


@frappe.whitelist()
def get_calendar_events(start=None, end=None, filters=None, field_map=None, **kwargs):
	"""Colour-coded events for the PO Delivery Schedule calendar view."""
	filters = frappe.parse_json(filters) if filters else []

	if start:
		filters.append(["PO Delivery Schedule", "scheduled_date", ">=", start])
	if end:
		filters.append(["PO Delivery Schedule", "scheduled_date", "<=", end])

	events = frappe.get_list(
		"PO Delivery Schedule",
		fields=[
			"name",
			"scheduled_date",
			"item_code",
			"item_name",
			"scheduled_qty",
			"uom",
			"status",
		],
		filters=filters,
		order_by="scheduled_date",
		limit_page_length=0,
	)

	for event in events:
		event["title"] = _calendar_event_title(event)
		event["color"] = _CALENDAR_STATUS_COLORS.get(event.get("status"), "#2490ef")
		event["allDay"] = 1

	return events


def _calendar_event_title(event):
	parts = [event.get("item_code") or event.get("name")]
	qty = flt(event.get("scheduled_qty"))
	if qty:
		parts.append(f"{qty:g} {event.get('uom') or ''}".strip())
	if event.get("status"):
		parts.append(f"({event['status']})")
	return " ".join(parts)