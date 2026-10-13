# Copyright (c) 2026, CAF and Contributors
# See license.txt

"""Regression tests for the PO Delivery Overview report.

Covers:
* permission / data isolation (User Permissions, missing read permission);
* the unallocated received quantity calculation (allocated vs unallocated
  receipts and returns);
* single-counting of the per-PO-Item unallocated figure across rows.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from po_delivery_scheduler.po_delivery_scheduler.report.po_delivery_overview.po_delivery_overview import (
	execute,
	get_unallocated_receipt_qty,
)
from po_delivery_scheduler.po_delivery_scheduler.tests import (
	get_item_warehouse,
	make_item,
	make_plan,
	make_purchase_order,
	make_receipt,
	make_schedule,
	make_supplier,
)


class TestPODeliveryOverviewReport(FrappeTestCase):
	def setUp(self):
		self.warehouse = get_item_warehouse()
		self.supplier = make_supplier()
		make_item("Test Delivery Item")

	def _rows(self, **filters):
		_columns, data = execute(filters)
		return data

	def _row_for(self, data, schedule_name):
		return next(row for row in data if row["name"] == schedule_name)

	def _unallocated_for(self, po_item):
		return get_unallocated_receipt_qty([{"purchase_order_item": po_item}]).get(po_item)

	# -- unallocated quantity calculation ---------------------------------

	def test_unallocated_receipt_is_counted(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=5, scheduled_date=add_days(today(), 7))

		make_receipt(po, qty=4)  # no schedule link -> unallocated

		self.assertEqual(flt(self._unallocated_for(po.items[0].name)), 4)
		row = self._row_for(self._rows(purchase_order=po.name), schedule.name)
		self.assertEqual(flt(row["unallocated_qty"]), 4)

	def test_allocated_receipt_is_not_unallocated(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=5, scheduled_date=add_days(today(), 7))

		make_receipt(po, delivery_schedule=schedule.name, qty=5)

		self.assertEqual(flt(self._unallocated_for(po.items[0].name)), 0)

	def test_return_against_unallocated_reduces_unallocated(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		make_schedule(plan, qty=5, scheduled_date=add_days(today(), 7))

		original = make_receipt(po, qty=4)  # unallocated
		make_receipt(
			po,
			qty=-2,
			is_return=1,
			return_against=original.name,
			purchase_receipt_item=original.items[0].name,
		)

		self.assertEqual(flt(self._unallocated_for(po.items[0].name)), 2)

	def test_return_against_allocated_does_not_reduce_unallocated(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=5, scheduled_date=add_days(today(), 7))

		original = make_receipt(po, delivery_schedule=schedule.name, qty=5)  # allocated
		make_receipt(
			po,
			qty=-2,
			is_return=1,
			return_against=original.name,
			purchase_receipt_item=original.items[0].name,
		)

		# the return belongs to the schedule, so it must not touch the
		# unallocated bucket
		self.assertEqual(flt(self._unallocated_for(po.items[0].name)), 0)

	def test_draft_and_cancelled_receipts_are_excluded(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		make_schedule(plan, qty=5, scheduled_date=add_days(today(), 7))

		make_receipt(po, qty=3, submitted=0)  # draft, excluded
		cancelled = make_receipt(po, qty=2)
		cancelled.cancel()

		self.assertEqual(flt(self._unallocated_for(po.items[0].name)), 0)

	def test_unallocated_is_reported_once_per_po_item(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		make_schedule(plan, qty=3, scheduled_date=add_days(today(), 7))
		make_schedule(plan, qty=3, scheduled_date=add_days(today(), 8))

		make_receipt(po, qty=4)  # unallocated

		data = self._rows(purchase_order=po.name)
		values = [
			flt(row["unallocated_qty"]) for row in data if row["purchase_order_item"] == po.items[0].name
		]
		# exactly one row carries the value, so summing the column is correct
		self.assertEqual(sum(values), 4)
		self.assertEqual(values.count(4), 1)

	# -- permissions / data isolation -------------------------------------

	def test_report_respects_supplier_user_permission(self):
		supplier_a = make_supplier("Report Supplier A").name
		supplier_b = make_supplier("Report Supplier B").name

		po_a = make_purchase_order(qty=10, supplier=supplier_a)
		schedule_a = make_schedule(make_plan(po_a), qty=5, scheduled_date=add_days(today(), 7))

		po_b = make_purchase_order(qty=10, supplier=supplier_b)
		schedule_b = make_schedule(make_plan(po_b), qty=5, scheduled_date=add_days(today(), 7))

		user = self._make_user("pds_report_allowed@example.com", ["Purchase User"])
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user.name,
				"allow": "Supplier",
				"for_value": supplier_a,
			}
		).insert(ignore_permissions=True)

		frappe.set_user(user.name)
		try:
			names = {row["name"] for row in self._rows()}
		finally:
			frappe.set_user("Administrator")

		self.assertIn(schedule_a.name, names)
		self.assertNotIn(schedule_b.name, names)

	def test_report_denies_user_without_read_permission(self):
		po = make_purchase_order(qty=10)
		make_schedule(make_plan(po), qty=5, scheduled_date=add_days(today(), 7))

		user = self._make_user("pds_report_denied@example.com", ["Accounts User"])

		frappe.set_user(user.name)
		try:
			with self.assertRaises(frappe.PermissionError):
				self._rows()
		finally:
			frappe.set_user("Administrator")

	# -- helpers ----------------------------------------------------------

	def _make_user(self, email, roles):
		if frappe.db.exists("User", email):
			return frappe.get_doc("User", email)

		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True)

		def _cleanup():
			if frappe.db.exists("User", email):
				for permission in frappe.get_all("User Permission", filters={"user": email}, pluck="name"):
					frappe.delete_doc("User Permission", permission, force=True, ignore_permissions=True)
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)

		self.addCleanup(_cleanup)
		return user
