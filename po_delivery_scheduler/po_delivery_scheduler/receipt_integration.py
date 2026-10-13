# Copyright (c) 2026, CAF and Contributors
# See license.txt

"""Integration between delivery schedules and actual Purchase Receipts.

Design
------
Every eligible *submitted* (docstatus == 1) Purchase Receipt Item can carry a
Link to a PO Delivery Schedule (custom field ``po_delivery_schedule`` on
``Purchase Receipt Item``). We deliberately use an explicit, auditable Link
field instead of inferring the relationship from item codes or dates.

Rules enforced here
-------------------
* Only submitted Purchase Receipts count (docstatus == 1).
* Cancelled / draft / deleted receipts never count.
* A receipt line can only be allocated to a schedule belonging to the same
  Purchase Order, same Purchase Order Item and same Item.
* Returns (``is_return == 1``) are attributed back to the delivery schedule of
  the original Purchase Receipt Item they reference (``purchase_receipt_item``)
  and subtract from the received quantity.
* Quantities are always converted into the schedule's reference UOM
  (the Purchase Order Item UOM) using each document's own ``conversion_factor``
  before aggregation.
* Received/outstanding quantities are recomputed from the database on every
  relevant event (receipt submit, cancel, trash, schedule save) - never from
  values sent by the browser.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from po_delivery_scheduler.po_delivery_scheduler.utils import (
	compute_schedule_status,
	set_plan_status,
)

# hook points are defensively exported here so tests can reference them

def _schedule_name(item) -> str | None:
	return (item or {}).get("po_delivery_schedule")


def _convert_to_schedule_uom(qty, conversion_factor, schedule_conversion_factor) -> float:
	"""Convert a quantity from the receipt line UOM into the schedule UOM.

	``qty * conversion_factor`` converts the receipt line quantity to the item
	stock UOM. Dividing by ``schedule_conversion_factor`` then converts from the
	stock UOM back into the schedule UOM (which equals the PO Item UOM).
	"""
	stock_qty = flt(qty) * flt(conversion_factor or 1)
	return flt(stock_qty / flt(schedule_conversion_factor or 1), 6)


def get_received_quantity_for_schedule(schedule_name: str, schedule_conversion_factor: float) -> float:
	"""Sum authoritative receipt quantities for one delivery schedule."""
	direct = frappe.db.sql(
		"""
		SELECT item.qty AS qty, item.conversion_factor AS conversion_factor
		FROM `tabPurchase Receipt Item` item
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = item.parent
		WHERE pr.docstatus = 1
			AND pr.is_return = 0
			AND item.po_delivery_schedule = %s
		""",
		(schedule_name,),
		as_dict=1,
	)

	returned = frappe.db.sql(
		"""
		SELECT abs(rim.qty) AS qty, rim.conversion_factor AS conversion_factor
		FROM `tabPurchase Receipt Item` rim
		INNER JOIN `tabPurchase Receipt` rpr ON rpr.name = rim.parent
		WHERE rpr.docstatus = 1
			AND rpr.is_return = 1
			AND rim.purchase_receipt_item IN (
				SELECT name
				FROM `tabPurchase Receipt Item`
				WHERE po_delivery_schedule = %s
			)
		""",
		(schedule_name,),
		as_dict=1,
	)

	received = sum(
		_convert_to_schedule_uom(row.qty, row.conversion_factor, schedule_conversion_factor)
		for row in direct
	)
	returned_qty = sum(
		_convert_to_schedule_uom(row.qty, row.conversion_factor, schedule_conversion_factor)
		for row in returned
	)
	return flt(received - returned_qty, 6)


def recalculate_schedule(schedule_name: str) -> None:
	"""Recompute received_qty / outstanding_qty / status from authoritative data.

	Idempotent: repeated calls never inflate quantities because they always
	reset from the database.
	"""
	values = frappe.db.get_value(
		"PO Delivery Schedule",
		schedule_name,
		[
			"delivery_plan",
			"scheduled_qty",
			"scheduled_date",
			"conversion_factor",
			"cancelled",
			"confirmation_status",
		],
		as_dict=1,
	)
	if not values:
		return

	scheduled_qty = flt(values.scheduled_qty)
	schedule_conversion_factor = flt(values.conversion_factor or 1)

	received_qty = get_received_quantity_for_schedule(schedule_name, schedule_conversion_factor)
	outstanding_qty = flt(max(0.0, scheduled_qty - received_qty))
	status = compute_schedule_status(
		cancelled=values.cancelled,
		received_qty=received_qty,
		scheduled_qty=scheduled_qty,
		scheduled_date=values.scheduled_date,
		confirmation_status=values.confirmation_status,
	)

	frappe.db.set_value(
		"PO Delivery Schedule",
		schedule_name,
		{
			"received_qty": received_qty,
			"outstanding_qty": outstanding_qty,
			"status": status,
		},
		update_modified=False,
	)

	set_plan_status(values.delivery_plan)


def _recalc_for_receipt(pr) -> None:
	"""Recalculate every schedule touched by a Purchase Receipt document."""
	schedules: set[str] = set()
	for item in pr.get("items") or []:
		if schedule := _schedule_name(item):
			schedules.add(schedule)

	# Return receipts reference the original lines, not the schedule itself.
	if pr.get("is_return"):
		for item in pr.get("items") or []:
			if not item.get("purchase_receipt_item"):
				continue
			original = frappe.db.get_value(
				"Purchase Receipt Item", item.get("purchase_receipt_item"), "po_delivery_schedule"
			)
			if original:
				schedules.add(original)

	for schedule_name in schedules:
		recalculate_schedule(schedule_name)


def validate_receipt_schedule_links(pr, method=None) -> None:
	"""Validate every schedule link present on receipt lines.

	Registered as a ``validate`` doc_event on Purchase Receipt. Runs on every
	save so a wrong link is rejected before the receipt can be submitted.
	"""
	items = pr.get("items") or []
	for item in items:
		schedule_name = _schedule_name(item)
		if not schedule_name:
			continue

		values = frappe.db.get_value(
			"PO Delivery Schedule",
			schedule_name,
			["purchase_order", "purchase_order_item", "item_code", "cancelled", "delivery_plan"],
			as_dict=1,
		)
		if not values:
			frappe.throw(
				_("{0}: Delivery Schedule {1} does not exist or was deleted.").format(
					item.idx, schedule_name
				)
			)

		if values.cancelled:
			frappe.throw(
				_("{0}: Delivery Schedule {1} is cancelled and cannot receive stock.").format(
					item.idx, schedule_name
				)
			)

		if values.purchase_order != item.get("purchase_order"):
			frappe.throw(
				_(
					"{0}: Delivery Schedule {1} belongs to Purchase Order {2}, but this line "
					"references Purchase Order {3}."
				).format(
					item.idx, schedule_name, values.purchase_order, item.get("purchase_order")
				)
			)

		if values.purchase_order_item != item.get("purchase_order_item"):
			frappe.throw(
				_(
					"{0}: Delivery Schedule {1} refers to Purchase Order Item {2}, "
					"but this line references Purchase Order Item {3}."
				).format(
					item.idx, schedule_name, values.purchase_order_item, item.get("purchase_order_item")
				)
			)

		if values.item_code != item.get("item_code"):
			frappe.throw(
				_(
					"{0}: Delivery Schedule {1} is for item {2}, "
					"but this line references item {3}."
				).format(item.idx, schedule_name, values.item_code, item.get("item_code"))
			)

		if not frappe.has_permission("PO Delivery Schedule", "read", doc=frappe.get_doc("PO Delivery Schedule", schedule_name)):
			frappe.throw(
				_("{0}: You do not have permission to use Delivery Schedule {1}.").format(
					item.idx, schedule_name
				)
			)


def on_purchase_receipt_submit(pr, method=None) -> None:
	_recalc_for_receipt(pr)


def on_purchase_receipt_cancel(pr, method=None) -> None:
	# A cancelled receipt is excluded automatically (docstatus != 1),
	# so recalculating drops its quantities from every affected schedule.
	_recalc_for_receipt(pr)


def on_purchase_receipt_trash(pr, method=None) -> None:
	# Deleting a draft receipt cannot affect submitted data, but recalculating
	# is cheap and keeps things consistent if the document was ever submitted.
	_recalc_for_receipt(pr)