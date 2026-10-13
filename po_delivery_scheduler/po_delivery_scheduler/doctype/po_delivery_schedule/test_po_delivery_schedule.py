# Copyright (c) 2026, CAF and Contributors
# See license.txt

"""Tests for PO Delivery Schedule creation, validation and receipt integration."""

import frappe
from frappe import ValidationError
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from po_delivery_scheduler.po_delivery_scheduler.tests import (
	get_item_warehouse,
	make_item,
	make_plan,
	make_purchase_order,
	make_receipt,
	make_schedule,
	make_supplier,
)


class TestPODeliverySchedule(FrappeTestCase):
	def setUp(self):
		self.warehouse = get_item_warehouse()
		self.supplier = make_supplier()
		make_item("Test Delivery Item")

	def test_schedule_defaults_from_po_item(self):
		po = make_purchase_order(qty=10, schedule_date=add_days(today(), 7))
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=4, scheduled_date=add_days(today(), 7))

		self.assertEqual(schedule.item_code, "Test Delivery Item")
		self.assertEqual(schedule.uom, "Nos")
		self.assertEqual(flt(schedule.conversion_factor), 1.0)
		self.assertEqual(schedule.status, "Planned")
		plan.reload()
		self.assertEqual(plan.status, "Active")
		self.assertEqual(schedule.outstanding_qty, 4)

	def test_schedule_qty_must_be_positive(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		with self.assertRaises(ValidationError):
			make_schedule(plan, qty=0)

	def test_overscheduling_rejected(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		make_schedule(plan, qty=6)
		with self.assertRaises(ValidationError):
			make_schedule(plan, qty=6)
		# exact total is allowed
		make_schedule(plan, qty=4)

	def test_duplicate_schedule_rejected(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		make_schedule(plan, qty=5, scheduled_date=today())
		with self.assertRaises(ValidationError):
			make_schedule(plan, qty=5, scheduled_date=today())
		# a different quantity on the same date is fine
		make_schedule(plan, qty=3, scheduled_date=today())

	def test_plan_requires_submitted_po(self):
		po = make_purchase_order(qty=10, do_not_submit=True)
		with self.assertRaises(ValidationError):
			make_plan(po)

	def test_schedule_cancelled_cannot_receive(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=5)
		schedule.db_set({"cancelled": 1, "status": "Cancelled"})
		schedule.reload()

		with self.assertRaises(ValidationError):
			make_receipt(po, delivery_schedule=schedule.name, qty=5)

	def test_wrong_item_link_rejected(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=5)

		other_item = make_item("Test Other Item")
		other_po = make_purchase_order(item_code="Test Other Item", qty=10, supplier=self.supplier.name)

		with self.assertRaises(ValidationError):
			make_receipt(po, delivery_schedule=schedule.name, qty=5, item_code="Test Other Item")

		# schedule from a different PO cannot be used on this PO
		plan2 = make_plan(other_po)
		schedule2 = make_schedule(plan2, qty=5)
		with self.assertRaises(ValidationError):
			make_receipt(po, delivery_schedule=schedule2.name, qty=5)

	def test_receipt_updates_schedule_quantities_and_status(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=10, scheduled_date=add_days(today(), 7))

		pr = make_receipt(po, delivery_schedule=schedule.name, qty=4)
		schedule.reload()
		self.assertEqual(schedule.received_qty, 4)
		self.assertEqual(schedule.outstanding_qty, 6)
		self.assertEqual(schedule.status, "Partially Received")

		pr2 = make_receipt(po, delivery_schedule=schedule.name, qty=6)
		schedule.reload()
		self.assertEqual(schedule.received_qty, 10)
		self.assertEqual(schedule.status, "Received")
		plan.reload()
		self.assertEqual(plan.status, "Completed")

		# cancelling the second receipt rolls the quantity back
		pr2.cancel()
		schedule.reload()
		self.assertEqual(schedule.received_qty, 4)
		self.assertEqual(schedule.status, "Partially Received")

	def test_return_reduces_received_quantity(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=10, scheduled_date=add_days(today(), 7))

		pr = make_receipt(po, delivery_schedule=schedule.name, qty=10)
		schedule.reload()
		self.assertEqual(schedule.status, "Received")

		# a return against the delivered line subtracts the returned quantity
		return_pr = make_receipt(
			po,
			qty=-4,
			is_return=1,
			return_against=pr.name,
			purchase_receipt_item=pr.items[0].name,
		)
		schedule.reload()
		self.assertEqual(schedule.received_qty, 6)
		self.assertEqual(schedule.status, "Partially Received")

	def test_overdue_status(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=5, scheduled_date=add_days(today(), -2))
		self.assertEqual(schedule.status, "Overdue")

	def test_confirmed_status(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(
			plan,
			qty=5,
			scheduled_date=add_days(today(), 7),
			confirmation_status="Confirmed",
			supplier_confirmed_date=add_days(today(), 2),
		)
		self.assertEqual(schedule.status, "Confirmed")

	def test_recalculating_is_idempotent(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=10, scheduled_date=add_days(today(), 7))

		from po_delivery_scheduler.po_delivery_scheduler.receipt_integration import recalculate_schedule

		make_receipt(po, delivery_schedule=schedule.name, qty=4)
		recalculate_schedule(schedule.name)
		recalculate_schedule(schedule.name)
		schedule.reload()
		self.assertEqual(schedule.received_qty, 4)
		self.assertEqual(schedule.outstanding_qty, 6)