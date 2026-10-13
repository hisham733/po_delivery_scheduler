# Copyright (c) 2026, CAF and contributors
# For license information, please see license.txt

"""PO Delivery Overview report.

Each row is one delivery schedule. Receipt figures are pulled from the
authoritative Purchase Receipt data (submitted receipts only) and converted
into the schedule UOM.

The ``unallocated_qty`` column surfaces submitted receipt quantities for a
Purchase Order Item that have NOT been linked to any delivery schedule - the
system never silently assigns unallocated stock to a schedule.

Permissions
-----------
Rows are read through ``frappe.get_list`` (never raw SQL) so that Frappe role
permissions and User Permissions (including Company and Supplier restrictions)
are always applied. A user only ever sees the schedules they are allowed to
read; the receipt-aggregation helper is fed only with the Purchase Order Items
of those already-filtered rows, so it cannot widen the result set.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

SCHEDULE_FIELDS = [
	"name",
	"delivery_plan",
	"purchase_order",
	"purchase_order_item",
	"supplier",
	"company",
	"item_code",
	"item_name",
	"scheduled_date",
	"scheduled_qty",
	"uom",
	"received_qty",
	"outstanding_qty",
	"status",
	"confirmation_status",
	"supplier_confirmed_date",
	"cancelled",
	"last_reminder_date",
]


def execute(filters=None):
	filters = frappe._dict(filters or {})

	conditions = []
	doctype = "PO Delivery Schedule"
	if filters.get("company"):
		conditions.append([doctype, "company", "=", filters.company])
	if filters.get("supplier"):
		conditions.append([doctype, "supplier", "=", filters.supplier])
	if filters.get("purchase_order"):
		conditions.append([doctype, "purchase_order", "=", filters.purchase_order])
	if filters.get("from_date"):
		conditions.append([doctype, "scheduled_date", ">=", getdate(filters.from_date)])
	if filters.get("to_date"):
		conditions.append([doctype, "scheduled_date", "<=", getdate(filters.to_date)])
	if filters.get("status"):
		conditions.append([doctype, "status", "=", filters.status])

	# frappe.get_list enforces role permissions and User Permissions.
	rows = frappe.get_list(
		doctype,
		fields=SCHEDULE_FIELDS,
		filters=conditions,
		order_by="purchase_order asc, scheduled_date asc, item_code asc",
		limit_page_length=0,
	)

	unallocated = get_unallocated_receipt_qty(rows)

	data = []
	seen_po_items: set = set()
	for row in rows:
		po_item = row.get("purchase_order_item")
		if po_item and po_item not in seen_po_items:
			# Report the PO-Item level figure exactly once so that exporting /
			# summing the column does not double count across schedule rows.
			row["unallocated_qty"] = flt(unallocated.get(po_item, 0))
			seen_po_items.add(po_item)
		else:
			row["unallocated_qty"] = 0.0
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
	"""Map purchase_order_item -> submitted, unallocated qty in the PO UOM.

	Unallocated means the *original* receipt line has no ``po_delivery_schedule``
	link. Only the following enter the calculation:

	* submitted (docstatus = 1), non-return receipt lines with no schedule link;
	* returns whose *original* line was itself unallocated - a return against a
	  schedule-allocated receipt reduces that schedule, never the unallocated
	  bucket.

	Quantities are converted into the Purchase Order Item UOM using each line's
	own ``conversion_factor``. Cancelled/draft documents are excluded.
	"""
	po_items = {row.get("purchase_order_item") for row in rows} - {None, ""}
	if not po_items:
		return {}

	direct = frappe.db.sql(
		"""
		SELECT item.purchase_order_item AS po_item, item.qty AS qty,
		       item.conversion_factor AS cf, item.po_delivery_schedule AS schedule
		FROM `tabPurchase Receipt Item` item
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = item.parent
		WHERE pr.docstatus = 1
			AND pr.is_return = 0
			AND item.purchase_order_item IN %s
		""",
		(tuple(po_items),),
		as_dict=1,
	)

	# Only returns that reference an *unallocated* original line reduce the
	# unallocated bucket. Returns against scheduled receipts belong to that
	# schedule and are handled by get_received_quantity_for_schedule.
	returned = frappe.db.sql(
		"""
		SELECT chk.purchase_order_item AS po_item, abs(chk.qty) AS qty,
		       chk.conversion_factor AS cf
		FROM `tabPurchase Receipt Item` chk
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = chk.parent
		INNER JOIN `tabPurchase Receipt Item` orig ON orig.name = chk.purchase_receipt_item
		WHERE pr.docstatus = 1
			AND pr.is_return = 1
			AND chk.purchase_order_item IN %s
			AND (orig.po_delivery_schedule IS NULL OR orig.po_delivery_schedule = '')
		""",
		(tuple(po_items),),
		as_dict=1,
	)

	po_cf = {d.name: flt(d.conversion_factor or 1) for d in frappe.db.get_all(
		"Purchase Order Item", filters={"name": ("in", list(po_items))}, fields=["name", "conversion_factor"]
	)}

	unallocated = {}
	for row in direct:
		if row.schedule:
			continue
		key = row.po_item
		unallocated[key] = unallocated.get(key, 0.0) + flt(row.qty) * flt(row.cf or 1)

	for row in returned:
		key = row.po_item
		unallocated[key] = unallocated.get(key, 0.0) - flt(row.qty) * flt(row.cf or 1)

	return {key: flt(value / flt(po_cf.get(key) or 1), 6) for key, value in unallocated.items()}
