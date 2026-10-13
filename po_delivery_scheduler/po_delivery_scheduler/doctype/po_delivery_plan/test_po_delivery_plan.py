# Copyright (c) 2026, CAF and Contributors
# See license.txt

"""Tests for PO Delivery Plan lifecycle, reminders and the overview report."""

from unittest.mock import patch

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


class TestPODeliveryPlan(FrappeTestCase):
	def setUp(self):
		self.warehouse = get_item_warehouse()
		self.supplier = make_supplier()
		make_item("Test Delivery Item")

	def test_get_or_create_delivery_plan_is_idempotent(self):
		po = make_purchase_order(qty=10)

		from po_delivery_scheduler.po_delivery_scheduler.api import get_or_create_delivery_plan

		plan1 = get_or_create_delivery_plan(po.name)
		plan2 = get_or_create_delivery_plan(po.name)
		self.assertEqual(plan1.name, plan2.name)
		self.assertEqual(plan1.supplier, po.supplier)
		self.assertEqual(plan1.company, po.company)
		self.assertEqual(plan1.status, "Draft")

	def test_po_item_picker_shows_item_code(self):
		po = make_purchase_order(qty=10)

		from po_delivery_scheduler.po_delivery_scheduler.api import get_po_item_query

		options = get_po_item_query(po.name)
		self.assertEqual(len(options), 1)
		self.assertEqual(options[0]["label"], "Test Delivery Item - Test Delivery Item")
		self.assertEqual(options[0]["value"], po.items[0].name)

		options_txt = get_po_item_query(po.name, txt="NOPE")
		self.assertEqual(len(options_txt), 0)

	def test_unique_plan_enforced(self):
		po = make_purchase_order(qty=10)
		make_plan(po)
		with self.assertRaises(ValidationError):
			make_plan(po)

	def test_po_cancel_cancels_plan_and_schedules(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		make_schedule(plan, qty=5)

		po.cancel()

		plan.reload()
		self.assertEqual(plan.status, "Cancelled")
		schedule = frappe.db.get_value(
			"PO Delivery Schedule", {"delivery_plan": plan.name}, ["name", "cancelled", "status"], as_dict=True
		)
		self.assertEqual((schedule.cancelled, schedule.status), (1, "Cancelled"))

	def test_cancel_plan_cancels_all_schedules(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		make_schedule(plan, qty=5, scheduled_date=add_days(today(), 2))
		s2 = make_schedule(plan, qty=5, scheduled_date=add_days(today(), 5))

		plan.cancel_plan()

		plan.reload()
		self.assertEqual(plan.status, "Cancelled")
		s2.reload()
		self.assertEqual(s2.status, "Cancelled")

	def test_plan_status_lifecycle(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		self.assertEqual(plan.status, "Draft")

		schedule = make_schedule(plan, qty=10, scheduled_date=add_days(today(), 7))
		plan.reload()
		self.assertEqual(plan.status, "Active")

		make_receipt(po, delivery_schedule=schedule.name, qty=10)
		plan.reload()
		self.assertEqual(plan.status, "Completed")

	def test_overview_report_returns_data(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=6, scheduled_date=add_days(today(), 7))

		from po_delivery_scheduler.po_delivery_scheduler.report.po_delivery_overview.po_delivery_overview import (
			execute,
		)

		columns, data = execute({"company": "CAF", "purchase_order": po.name})
		self.assertTrue(columns and data)
		self.assertTrue(any(row["name"] == schedule.name for row in data))
		self.assertIn("unallocated_qty", data[0])

	def test_due_deliveries_are_flagged(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po, reminders_enabled=1, reminder_lead_days=3)
		overdue = make_schedule(plan, qty=5, scheduled_date=add_days(today(), -5))
		due_soon = make_schedule(plan, qty=5, scheduled_date=add_days(today(), 2))

		from po_delivery_scheduler.po_delivery_scheduler.reminders import get_due_deliveries

		due = get_due_deliveries()
		names = {d.name: d.flags for d in due}
		self.assertEqual(names[overdue.name].overdue, True)
		self.assertEqual(names[due_soon.name].due_soon, True)

	def test_reminder_sent_once_per_day(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po, reminders_enabled=1, reminder_lead_days=3)
		overdue = make_schedule(plan, qty=5, scheduled_date=add_days(today(), -5))

		from po_delivery_scheduler.po_delivery_scheduler.reminders import (
			get_due_deliveries,
			send_delivery_reminders,
		)

		with patch("frappe.sendmail") as sendmail:
			first = send_delivery_reminders(commit=False)
			self.assertGreaterEqual(first, 1)

			# idempotency: our schedule must not be due again on the same day
			due_after = {d.name for d in get_due_deliveries()}
			self.assertNotIn(overdue.name, due_after)

		overdue.reload()
		self.assertEqual(frappe.utils.getdate(overdue.last_reminder_date), frappe.utils.getdate())
		self.assertTrue(overdue.reminder_note)

	def test_reminder_does_not_fail_when_email_errors(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po, reminders_enabled=1, reminder_lead_days=3)
		schedule = make_schedule(plan, qty=5, scheduled_date=add_days(today(), -5))

		from po_delivery_scheduler.po_delivery_scheduler.reminders import send_delivery_reminders

		with patch("frappe.sendmail", side_effect=RuntimeError("no smtp")):
			sent = send_delivery_reminders(commit=False)
		self.assertGreaterEqual(sent, 1)

		schedule.reload()
		self.assertIn("FAILED", schedule.reminder_note)