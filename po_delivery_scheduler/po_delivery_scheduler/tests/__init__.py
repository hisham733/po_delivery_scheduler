# Copyright (c) 2026, CAF and Contributors
# See license.txt

"""Shared fixtures / builders used by the PO Delivery Scheduler tests."""

import frappe

COMPANY = "CAF"


def get_company_defaults():
	return frappe.get_cached_value(
		"Company",
		COMPANY,
		["default_expense_account", "default_payable_account", "cost_center"],
		as_dict=True,
	)


def get_item_warehouse():
	warehouse = frappe.get_all(
		"Warehouse",
		filters={"company": COMPANY, "is_group": 0},
		fields=["name"],
		limit=1,
	)
	if not warehouse:
		raise Exception(f"No non-group warehouse found for company {COMPANY}")
	return warehouse[0].name


def make_item(item_code="Test Delivery Item"):
	if frappe.db.exists("Item", item_code):
		item = frappe.get_doc("Item", item_code)
	else:
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"is_purchase_item": 1,
				"is_sales_item": 1,
				"has_variants": 0,
				"include_item_in_manufacturing": 0,
				"opening_stock": 0,
			}
		).insert(ignore_permissions=True)
	return item


def make_supplier(name="Test Delivery Supplier"):
	if frappe.db.exists("Supplier", name):
		return frappe.get_doc("Supplier", name)
	supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
	return frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": name,
			"supplier_group": supplier_group or "All Supplier Groups",
		}
	).insert(ignore_permissions=True)


def make_purchase_order(
	item_code="Test Delivery Item",
	qty=10,
	rate=10,
	schedule_date=None,
	warehouse=None,
	do_not_submit=False,
	supplier=None,
):
	po = frappe.new_doc("Purchase Order")
	po.company = COMPANY
	po.supplier = supplier or make_supplier().name
	po.transaction_date = frappe.utils.today()
	po.schedule_date = schedule_date or frappe.utils.today()
	po.set_warehouse = warehouse or get_item_warehouse()
	po.set(
		"items",
		[
			{
				"item_code": item_code,
				"qty": qty,
				"rate": rate,
				"uom": "Nos",
				"conversion_factor": 1,
				"schedule_date": schedule_date or frappe.utils.today(),
				"warehouse": warehouse or get_item_warehouse(),
			}
		],
	)
	po.insert(ignore_permissions=True)
	if not do_not_submit:
		po.submit()
	return po


def make_receipt(po, submitted=1, delivery_schedule=None, qty=None, item_code=None, is_return=0, return_against=None, purchase_receipt_item=None):
	defaults = get_company_defaults()
	pr = frappe.new_doc("Purchase Receipt")
	pr.company = COMPANY
	pr.supplier = po.supplier
	pr.posting_date = frappe.utils.today()
	pr.set_warehouse = po.set_warehouse or get_item_warehouse()
	if is_return:
		pr.is_return = 1
		pr.return_against = return_against or ""
	po_item = po.items[0]
	pr.append(
		"items",
		{
			"item_code": item_code or po_item.item_code,
			"qty": qty if qty is not None else po_item.qty,
			"rate": po_item.rate,
			"uom": po_item.uom,
			"conversion_factor": po_item.conversion_factor,
			"purchase_order": po.name,
			"purchase_order_item": po_item.name,
			"po_delivery_schedule": delivery_schedule or "",
			"warehouse": po.set_warehouse or get_item_warehouse(),
			"expense_account": defaults.default_expense_account,
			"purchase_receipt_item": purchase_receipt_item or "",
		},
	)
	pr.insert(ignore_permissions=True)
	if submitted:
		pr.submit()
	return pr


def make_receipt_lines(po, lines, submitted=1):
	"""Build a Purchase Receipt with one item row per entry in ``lines``.

	Each entry is a dict accepting ``qty`` (required), ``delivery_schedule``,
	``item_code``, ``uom``, ``conversion_factor``, ``purchase_order_item`` and
	``purchase_receipt_item``. Missing values fall back to the PO's first item.
	Useful for exercising multi-line receipts that reference several schedules
	or repeat the same schedule on more than one line.
	"""
	defaults = get_company_defaults()
	pr = frappe.new_doc("Purchase Receipt")
	pr.company = COMPANY
	pr.supplier = po.supplier
	pr.posting_date = frappe.utils.today()
	pr.set_warehouse = po.set_warehouse or get_item_warehouse()
	po_item = po.items[0]
	for line in lines:
		pr.append(
			"items",
			{
				"item_code": line.get("item_code", po_item.item_code),
				"qty": line["qty"],
				"rate": po_item.rate,
				"uom": line.get("uom", po_item.uom),
				"conversion_factor": line.get("conversion_factor", po_item.conversion_factor),
				"purchase_order": po.name,
				"purchase_order_item": line.get("purchase_order_item", po_item.name),
				"po_delivery_schedule": line.get("delivery_schedule", ""),
				"warehouse": po.set_warehouse or get_item_warehouse(),
				"expense_account": defaults.default_expense_account,
				"purchase_receipt_item": line.get("purchase_receipt_item", ""),
			},
		)
	pr.insert(ignore_permissions=True)
	if submitted:
		pr.submit()
	return pr


def make_plan(po=None, with_schedule=None, reminders_enabled=0, reminder_lead_days=0):
	po = po or make_purchase_order()
	plan = frappe.get_doc(
		{
			"doctype": "PO Delivery Plan",
			"purchase_order": po.name,
		}
	).insert(ignore_permissions=True)

	if with_schedule:
		make_schedule(plan, qty=with_schedule)

	if reminders_enabled or reminder_lead_days:
		plan.db_set(
			{
				"reminders_enabled": reminders_enabled,
				"reminder_lead_days": reminder_lead_days,
			}
		)
	return plan


def get_po_item(purchase_order):
	return frappe.db.get_value(
		"Purchase Order Item",
		{"parent": purchase_order},
		"name",
		order_by="idx asc",
	)


def make_schedule(plan, qty=5, scheduled_date=None, confirmation_status=None, supplier_confirmed_date=None):
	schedule = frappe.get_doc(
		{
			"doctype": "PO Delivery Schedule",
			"delivery_plan": plan.name,
			"purchase_order_item": get_po_item(plan.purchase_order),
			"scheduled_date": scheduled_date or frappe.utils.today(),
			"scheduled_qty": qty,
			"confirmation_status": confirmation_status or "Not Requested",
			"supplier_confirmed_date": supplier_confirmed_date,
		}
	).insert(ignore_permissions=True)
	schedule.reload()
	return schedule