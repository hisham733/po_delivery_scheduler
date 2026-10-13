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

	def test_get_plan_schedules_returns_rows_for_authorized_user(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=5, scheduled_date=add_days(today(), 7))

		from po_delivery_scheduler.po_delivery_scheduler.api import get_plan_schedules

		names = {row["name"] for row in get_plan_schedules(plan.name)}
		self.assertIn(schedule.name, names)

	def test_get_plan_schedules_enforces_schedule_read_permission(self):
		"""A user who may read the plan but not its schedules gets no rows.

		Regression guard for the earlier use of ``frappe.get_all`` (which sets
		``ignore_permissions=True``): the schedule query must itself be
		permission-aware.
		"""
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		make_schedule(plan, qty=5, scheduled_date=add_days(today(), 7))

		role = "PDS Plan Only Reader"
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
		from frappe.permissions import add_permission

		add_permission("PO Delivery Plan", role, ptype="read")

		user = self._make_user("pds_plan_only@example.com", [role])

		from po_delivery_scheduler.po_delivery_scheduler.api import get_plan_schedules

		frappe.set_user(user.name)
		try:
			# plan read is allowed, but PO Delivery Schedule read is not
			with self.assertRaises(frappe.PermissionError):
				get_plan_schedules(plan.name)
		finally:
			frappe.set_user("Administrator")


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

	def test_cancel_plan_preserves_received_schedules(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		received = make_schedule(plan, qty=5, scheduled_date=add_days(today(), 5))
		make_receipt(po, delivery_schedule=received.name, qty=5)
		open_schedule = make_schedule(plan, qty=5, scheduled_date=add_days(today(), 6))

		plan.cancel_plan()

		plan.reload()
		self.assertEqual(plan.status, "Cancelled")

		# the completed delivery keeps its history
		received.reload()
		self.assertEqual(received.status, "Received")
		self.assertEqual(received.cancelled, 0)
		self.assertEqual(received.received_qty, 5)

		# the outstanding schedule is cancelled
		open_schedule.reload()
		self.assertEqual(open_schedule.status, "Cancelled")
		self.assertEqual(open_schedule.cancelled, 1)

	def test_po_cancel_preserves_received_schedule_history(self):
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		received = make_schedule(plan, qty=5, scheduled_date=add_days(today(), 5))
		# Simulate a fully delivered schedule. ERPNext blocks cancelling a PO
		# that has a submitted receipt against it, so set the tracking fields
		# directly instead of creating a receipt.
		frappe.db.set_value(
			"PO Delivery Schedule",
			received.name,
			{"received_qty": 5, "outstanding_qty": 0, "status": "Received"},
		)
		open_schedule = make_schedule(plan, qty=5, scheduled_date=add_days(today(), 6))

		po.cancel()

		plan.reload()
		self.assertEqual(plan.status, "Cancelled")

		received.reload()
		self.assertEqual(received.status, "Received")
		self.assertEqual(received.cancelled, 0)

		open_schedule.reload()
		self.assertEqual(open_schedule.status, "Cancelled")
		self.assertEqual(open_schedule.cancelled, 1)

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
