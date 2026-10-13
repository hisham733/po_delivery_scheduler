# Copyright (c) 2026, CAF and Contributors
# See license.txt

"""Transaction-level tests for concurrent Purchase Receipt submission.

These tests use two real database connections (``primary_connection`` /
``secondary_connection`` from :class:`FrappeTestCase`) so the InnoDB
REPEATABLE READ semantics that the over-receipt guard depends on are exercised
for real, not simulated with a single connection.

They prove three things about ``validate_receipt_schedule_links``:

1. The ``PO Delivery Schedule`` row is locked ``FOR UPDATE`` before remaining
   quantity is validated, so a concurrent transaction cannot acquire the same
   lock (serialisation).
2. After acquiring the lock the aggregate of already-received quantities is
   read as a *current* (locking) read; a plain read would still be pinned to the
   transaction snapshot taken before a concurrent receipt committed.
3. Consequently a second receipt that would push the schedule past its allowed
   quantity is rejected even though a naive snapshot read would have seen zero
   received.

Because cross-connection visibility requires committed rows, this module commits
its fixtures and removes them again in cleanup. That is why it cannot rely on
``FrappeTestCase``'s class-level rollback alone.

Note: ``secondary_connection()`` calls ``frappe.connect()``, which replaces
``frappe.local.db``; it does not restore the previous connection afterwards (the
restored value is the secondary). Every primary-side action below therefore runs
inside an explicit ``primary_connection()`` block, matching the pattern used by
Frappe's own ``TestConcurrency``.
"""

import frappe
from frappe import ValidationError
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from po_delivery_scheduler.po_delivery_scheduler.receipt_integration import (
	get_received_quantity_for_schedule,
	validate_receipt_schedule_links,
)
from po_delivery_scheduler.po_delivery_scheduler.tests import (
	get_item_warehouse,
	get_po_item,
	make_item,
	make_plan,
	make_purchase_order,
	make_receipt,
	make_schedule,
	make_supplier,
)


class TestReceiptConcurrency(FrappeTestCase):
	def setUp(self):
		self.warehouse = get_item_warehouse()
		self.supplier = make_supplier()
		make_item("Test Delivery Item")

	# -- helpers ----------------------------------------------------------

	def _locked_schedule_value(self, schedule_name, *, wait=True):
		return frappe.db.get_value(
			"PO Delivery Schedule", schedule_name, "name", for_update=True, wait=wait
		)

	def _synthetic_receipt(self, po, schedule, qty, idx=1):
		"""A minimal stand-in for a Purchase Receipt accepted by the validator."""
		return frappe._dict(
			is_return=0,
			items=[
				frappe._dict(
					idx=idx,
					po_delivery_schedule=schedule.name,
					purchase_order=po.name,
					purchase_order_item=get_po_item(po.name),
					item_code="Test Delivery Item",
					qty=qty,
					conversion_factor=1,
				)
			],
		)

	def _submit_concurrent_receipt(self, po, schedule, qty):
		"""Submit a receipt over the secondary connection and commit it."""
		with self.secondary_connection():
			frappe.db.rollback()
			receipt = make_receipt(po, delivery_schedule=schedule.name, qty=qty)
			frappe.db.commit()
		return receipt

	def _purge(self, *, receipts=(), schedules=(), plan=None, po=None):
		"""Remove committed fixtures created by these tests (on the primary)."""
		try:
			with self.primary_connection():
				frappe.set_user("Administrator")
				# release any locks/snapshots held by the primary connection
				frappe.db.rollback()

				for name in receipts:
					try:
						doc = frappe.get_doc("Purchase Receipt", name)
						if doc.docstatus == 1:
							doc.cancel()
						if doc.docstatus == 2:
							frappe.delete_doc(
								"Purchase Receipt", name, force=True, ignore_permissions=True
							)
					except Exception:
						frappe.clear_last_message()

				for name in schedules:
					try:
						frappe.delete_doc(
							"PO Delivery Schedule", name, force=True, ignore_permissions=True
						)
					except Exception:
						frappe.clear_last_message()

				if plan:
					try:
						frappe.delete_doc(
							"PO Delivery Plan", plan, force=True, ignore_permissions=True
						)
					except Exception:
						frappe.clear_last_message()

				if po:
					try:
						po_doc = frappe.get_doc("Purchase Order", po)
						if po_doc.docstatus == 1:
							po_doc.cancel()
						frappe.delete_doc("Purchase Order", po, force=True, ignore_permissions=True)
					except Exception:
						frappe.clear_last_message()

				frappe.db.commit()
		except Exception:
			frappe.clear_last_message()

	# -- tests ------------------------------------------------------------

	def test_schedule_lock_serializes_concurrent_receipts(self):
		"""A second transaction cannot lock a schedule that is already locked."""
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=5)
		frappe.db.commit()
		self.addCleanup(self._purge, schedules=[schedule.name], plan=plan.name, po=po.name)

		with self.primary_connection():
			# Validation first takes a consistent read, then locks the row.
			frappe.db.get_value("PO Delivery Schedule", schedule.name, "scheduled_qty")
			self.assertEqual(self._locked_schedule_value(schedule.name), schedule.name)

			# While the primary transaction holds the lock, another connection
			# must not be able to acquire it (NOWAIT avoids an indefinite hang).
			with self.secondary_connection():
				self.assertRaises(
					frappe.QueryTimeoutError,
					lambda: self._locked_schedule_value(schedule.name, wait=False),
				)

	def test_validation_uses_current_read_not_stale_snapshot(self):
		"""The received-quantity read must see a concurrently committed receipt."""
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=5)
		frappe.db.commit()

		receipt_name = None
		try:
			# Pin the primary transaction's snapshot while nothing is received.
			with self.primary_connection():
				self.assertEqual(flt(get_received_quantity_for_schedule(schedule.name, 1.0)), 0)

			# A concurrent transaction receives the full scheduled quantity and
			# commits it on a separate connection.
			receipt = self._submit_concurrent_receipt(po, schedule, qty=5)
			receipt_name = receipt.name

			with self.primary_connection():
				# Still invisible to a plain read (stale snapshot)...
				self.assertEqual(flt(get_received_quantity_for_schedule(schedule.name, 1.0)), 0)
				# ...but visible to a locking (current) read.
				self.assertEqual(
					flt(get_received_quantity_for_schedule(schedule.name, 1.0, for_update=True)), 5
				)
		finally:
			self._purge(
				receipts=[receipt_name] if receipt_name else [],
				schedules=[schedule.name],
				plan=plan.name,
				po=po.name,
			)

	def test_second_receipt_cannot_over_receive_after_concurrent_commit(self):
		"""End-to-end: concurrent commit + stale snapshot still cannot over-receive.

		Without the current read the validator would compute ``already_received
		= 0`` from the stale snapshot and accept a second unit on a schedule
		that a concurrent transaction has already fully received.
		"""
		po = make_purchase_order(qty=10)
		plan = make_plan(po)
		schedule = make_schedule(plan, qty=5)
		frappe.db.commit()

		receipt_name = None
		try:
			# Pin the snapshot before the concurrent receipt exists.
			with self.primary_connection():
				self.assertEqual(flt(get_received_quantity_for_schedule(schedule.name, 1.0)), 0)

			receipt = self._submit_concurrent_receipt(po, schedule, qty=5)
			receipt_name = receipt.name

			with self.primary_connection():
				# The stale snapshot still says zero...
				self.assertEqual(flt(get_received_quantity_for_schedule(schedule.name, 1.0)), 0)

				# ...yet validation must reject the extra unit.
				pr = self._synthetic_receipt(po, schedule, qty=1)
				with self.assertRaises(ValidationError) as ctx:
					validate_receipt_schedule_links(pr)
				self.assertIn("over-receive", str(ctx.exception))
		finally:
			self._purge(
				receipts=[receipt_name] if receipt_name else [],
				schedules=[schedule.name],
				plan=plan.name,
				po=po.name,
			)
