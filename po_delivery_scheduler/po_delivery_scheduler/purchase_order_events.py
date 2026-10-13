# Copyright (c) 2026, CAF and Contributors
# See license.txt

"""Hook handlers for Purchase Order lifecycle events.

Behaviour (documented product rules)
------------------------------------
* Schedules can only be created against *submitted* Purchase Orders.
* When a Purchase Order is cancelled, its delivery plan is cancelled and all
  open schedules are cancelled. The cancelled records are kept for audit.
* When a Purchase Order is amended, ERPNext cancels the original order, which
  triggers the cancellation above. The amended order is a new document with no
  plan; the purchasing team must create a fresh plan for it.
* If a Purchase Order's quantities are reduced, ``validate_schedules_against_po``
  prevents the over-scheduled state from being saved silently.
"""

import frappe
from frappe import _
from frappe.utils import flt

from po_delivery_scheduler.po_delivery_scheduler.utils import get_plan_for_po


def on_purchase_order_cancel(po, method=None) -> None:
	plan_name = get_plan_for_po(po.name)
	if not plan_name:
		return

	plan = frappe.get_doc("PO Delivery Plan", plan_name)
	plan.db_set("status", "Cancelled")

	# Cancel only outstanding schedules. Fully received schedules keep their
	# ``Received`` status and quantities so the delivery history is preserved.
	open_schedules = frappe.get_all(
		"PO Delivery Schedule",
		filters={
			"delivery_plan": plan_name,
			"cancelled": 0,
			"status": ("!=", "Received"),
		},
		pluck="name",
	)
	for name in open_schedules:
		frappe.db.set_value(
			"PO Delivery Schedule",
			name,
			{
				"cancelled": 1,
				"cancellation_reason": _("Purchase Order cancelled"),
				"status": "Cancelled",
			},
			update_modified=False,
		)


def validate_schedules_against_po(po, method=None) -> None:
	"""Prevent saving a Purchase Order that would over-schedule its items.

	This is a safety net. In normal operation schedule totals are validated when
	the schedule is saved; this hook re-validates whenever the parent Purchase
	Order itself is saved (including amendments).
	"""
	plan_name = get_plan_for_po(po.name)
	if not plan_name:
		return

	order_qty = {
		d.name: d.qty for d in (po.get("items") or [])
	}

	rows = frappe.db.sql(
		"""
		SELECT purchase_order_item, SUM(scheduled_qty) AS scheduled
		FROM `tabPO Delivery Schedule`
		WHERE delivery_plan = %s AND cancelled = 0
		GROUP BY purchase_order_item
		""",
		plan_name,
		as_list=1,
	)

	for purchase_order_item, scheduled in rows or []:
		if purchase_order_item not in order_qty:
			frappe.throw(
				_(
					"Purchase Order Item {0} no longer exists on Purchase Order {1} "
					"but is still referenced by delivery schedules."
				).format(purchase_order_item, po.name)
			)
		if flt(scheduled) > flt(order_qty[purchase_order_item]) + 1e-6:
			frappe.throw(
				_(
					"Purchase Order {0} item {1} is scheduled for {2} units but only "
					"{3} units are ordered. Reduce the delivery schedule before saving."
				).format(
					po.name,
					purchase_order_item,
					frappe.bold(flt(scheduled)),
					frappe.bold(flt(order_qty[purchase_order_item])),
				)
			)
