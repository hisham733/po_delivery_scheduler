# Copyright (c) 2026, CAF and contributors
# For license information, please see license.txt

"""PO Delivery Overview report.

Each row is one delivery schedule. Receipt figures are pulled from the
authoritative Purchase Receipt data (submitted receipts only) and converted
into the schedule UOM.

The ``unallocated_qty`` column surfaces submitted receipt quantities for a
Purchase Order Item that have NOT been linked to any delivery schedule - the
system never silently assigns unallocated stock to a schedule.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})

	schedule = frappe.qb.DocType("PO Delivery Schedule")
	plan = frappe.qb.DocType("PO Delivery Plan")

	query = (
		frappe.qb.from_(schedule)
		.inner_join(plan)
		.on(plan.name == schedule.delivery_plan)
		.select(
			schedule.name,
			schedule.delivery_plan,
			schedule.purchase_order,
			schedule.purchase_order_item,
			schedule.supplier,
			schedule.company,
			schedule.item_code,
			schedule.item_name,
			schedule.scheduled_date,
			schedule.scheduled_qty,
			schedule.uom,
			schedule.received_qty,
			schedule.outstanding_qty,
			schedule.status,
			schedule.confirmation_status,
			schedule.supplier_confirmed_date,
			schedule.cancelled,
			schedule.last_reminder_date,
		)
	)

	cond = []
	if filters.get("company"):
		cond.append(plan.company == filters.company)
	if filters.get("supplier"):
		cond.append(plan.supplier == filters.supplier)
	if filters.get("purchase_order"):
		cond.append(schedule.purchase_order == filters.purchase_order)
	if filters.get("from_date"):
		cond.append(schedule.scheduled_date >= getdate(filters.from_date))
	if filters.get("to_date"):
		cond.append(schedule.scheduled_date <= getdate(filters.to_date))
	if filters.get("status"):
		cond.append(schedule.status == filters.status)

	for c in cond:
		query = query.where(c)

	rows = query.orderby(schedule.purchase_order, schedule.scheduled_date, schedule.item_code).run(
		as_dict=1
	)

	unallocated = get_unallocated_receipt_qty(rows)

	data = []
	for row in rows:
		row["unallocated_qty"] = flt(unallocated.get(row.purchase_order_item or "", 0))
		data.append(row)

	columns = get_columns()
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "name",
			"label": _("Schedule"),
			"fieldtype": "Link",
			"options": "PO Delivery Schedule",
			"width": 140,
		},
		{
			"fieldname": "delivery_plan",
			"label": _("Delivery Plan"),
			"fieldtype": "Link",
			"options": "PO Delivery Plan",
			"width": 130,
		},
		{
			"fieldname": "purchase_order",
			"label": _("Purchase Order"),
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 150,
		},
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 160,
		},
		{
			"fieldname": "company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 100,
		},
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{
			"fieldname": "scheduled_date",
			"label": _("Scheduled Date"),
			"fieldtype": "Date",
			"width": 110,
		},
		{"fieldname": "scheduled_qty", "label": _("Scheduled Qty"), "fieldtype": "Float", "width": 100},
		{
			"fieldname": "uom",
			"label": _("UOM"),
			"fieldtype": "Link",
			"options": "UOM",
			"width": 70,
		},
		{
			"fieldname": "received_qty",
			"label": _("Received Qty"),
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"fieldname": "outstanding_qty",
			"label": _("Outstanding Qty"),
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"fieldname": "unallocated_qty",
			"label": _("Unallocated Received Qty (PO Item)"),
			"fieldtype": "Float",
			"width": 150,
		},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "confirmation_status",
			"label": _("Confirmation"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "supplier_confirmed_date",
			"label": _("Supplier Confirmed Date"),
			"fieldtype": "Date",
			"width": 110,
		},
		{"fieldname": "cancelled", "label": _("Cancelled"), "fieldtype": "Check", "width": 60},
	]


def get_unallocated_receipt_qty(rows):
	"""Map purchase_order_item -> submitted, received, unallocated qty in PO UOM.

	Unallocated means the receipt line has no ``po_delivery_schedule`` link.
	Returns are subtracted so returned goods are not shown as unallocated stock.
	"""
	po_items = {row.get("purchase_order_item") for row in rows} - {None, ""}
	if not po_items:
		return {}

	direct = frappe.db.sql(
		"""
		SELECT item.purchase_order_item AS po_item, item.qty, item.conversion_factor AS cf,
		       item.po_delivery_schedule AS schedule
		FROM `tabPurchase Receipt Item` item
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = item.parent
		WHERE pr.docstatus = 1
			AND pr.is_return = 0
			AND item.purchase_order_item IN %s
		""",
		(tuple(po_items),),
		as_dict=1,
	)

	returned = frappe.db.sql(
		"""
		SELECT chk.purchase_order_item AS po_item, abs(chk.qty) AS qty, chk.conversion_factor AS cf
		FROM `tabPurchase Receipt Item` chk
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = chk.parent
		WHERE pr.docstatus = 1
			AND pr.is_return = 1
			AND chk.purchase_receipt_item IN (
				SELECT name FROM `tabPurchase Receipt Item`
				WHERE purchase_order_item IN %s
			)
		""",
		(tuple(po_items),),
		as_dict=1,
	)

	po_cf = {d.name: flt(d.conversion_factor or 1) for d in frappe.db.get_all(
		"Purchase Order Item", filters={"name": ("in", list(po_items))}, fields=["name", "conversion_factor"]
	)}

	allocated_received = {}
	for row in direct:
		key = row.po_item
		received = flt(row.qty) * flt(row.cf or 1)
		allocated_received.setdefault(key, 0.0)
		if not row.schedule:
			allocated_received[key] += received

	for row in returned:
		key = row.po_item
		received = flt(row.qty) * flt(row.cf or 1)
		allocated_received.setdefault(key, 0.0)
		allocated_received[key] -= received

	return {key: flt(value / flt(po_cf.get(key) or 1), 6) for key, value in allocated_received.items()}