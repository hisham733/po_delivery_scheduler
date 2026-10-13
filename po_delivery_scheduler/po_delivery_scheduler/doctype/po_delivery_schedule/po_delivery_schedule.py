# Copyright (c) 2026, CAF and contributors
# For license information, please see license.txt

import frappe
from frappe import _, throw
from frappe.model.document import Document
from frappe.utils import flt, getdate

from po_delivery_scheduler.po_delivery_scheduler.receipt_integration import recalculate_schedule

LOCK_SQL = "SELECT name FROM `tabPurchase Order Item` WHERE name = %s FOR UPDATE"


class PODeliverySchedule(Document):
	def before_insert(self):
		plan = frappe.get_cached_doc("PO Delivery Plan", self.delivery_plan)
		self.purchase_order = plan.purchase_order
		self.supplier = plan.supplier
		self.company = plan.company

	def before_validate(self):
		self.set_po_item_defaults()

	def set_po_item_defaults(self):
		"""Auto-fill item / UOM data from the authoritative Purchase Order Item."""
		if not self.purchase_order_item:
			return
		po_item = frappe.db.get_value(
			"Purchase Order Item",
			self.purchase_order_item,
			["parent", "item_code", "item_name", "uom", "conversion_factor", "schedule_date"],
			as_dict=1,
		)
		if not po_item:
			throw(_("Purchase Order Item {0} was not found.").format(self.purchase_order_item))
		if not self.item_code:
			self.item_code = po_item.item_code
		if not self.item_name:
			self.item_name = po_item.item_name
		if not self.uom:
			self.uom = po_item.uom
		if not self.scheduled_date:
			self.scheduled_date = po_item.schedule_date
		self.conversion_factor = flt(po_item.conversion_factor or 1)

	def validate(self):
		self.validate_links()
		self.validate_po_is_active()
		self.validate_scheduled_qty()
		self.validate_confirmation_status()
		self.validate_not_over_scheduled()
		self.validate_no_duplicate()

	def validate_links(self):
		"""Validate every linked document relationship on the server."""
		plan = frappe.db.get_value(
			"PO Delivery Plan",
			self.delivery_plan,
			["purchase_order", "supplier", "company"],
			as_dict=1,
		)
		if not plan:
			throw(_("Delivery Plan {0} does not exist.").format(self.delivery_plan))

		if not self.purchase_order:
			throw(_("Purchase Order is required on a delivery schedule."))

		po = frappe.get_doc("Purchase Order", self.purchase_order)
		if not frappe.has_permission("Purchase Order", "read", doc=po):
			throw(_("You do not have read access to Purchase Order {0}.").format(self.purchase_order))

		if plan.purchase_order != self.purchase_order:
			throw(
				_("Delivery Plan {0} belongs to Purchase Order {1}, not {2}.").format(
					self.delivery_plan, plan.purchase_order, self.purchase_order
				)
			)

		po_item = frappe.db.get_value(
			"Purchase Order Item",
			self.purchase_order_item,
			["parent", "item_code", "uom", "conversion_factor"],
			as_dict=1,
		)
		if not po_item:
			throw(_("Purchase Order Item {0} was not found.").format(self.purchase_order_item))

		if po_item.parent != self.purchase_order:
			throw(
				_("Purchase Order Item {0} does not belong to Purchase Order {1}.").format(
					self.purchase_order_item, self.purchase_order
				)
			)

		if self.item_code and self.item_code != po_item.item_code:
			throw(
				_("Item {0} does not match the Item {1} of Purchase Order Item {2}.").format(
					self.item_code, po_item.item_code, self.purchase_order_item
				)
			)

		if self.uom and self.uom != po_item.uom:
			throw(
				_(
					"UOM must match the Purchase Order Item UOM ({0}). "
					"Conversion factors are resolved against the stock UOM automatically."
				).format(po_item.uom)
			)

		if self.supplier and self.supplier != plan.supplier:
			throw(
				_("Supplier {0} does not match the plan supplier {1}.").format(
					self.supplier, plan.supplier
				)
			)

		if self.company and self.company != plan.company:
			throw(
				_("Company {0} does not match the plan company {1}.").format(
					self.company, plan.company
				)
			)

	def validate_po_is_active(self):
		po = frappe.get_doc("Purchase Order", self.purchase_order)
		if po.docstatus != 1:
			throw(_("Delivery schedules can only be linked to submitted Purchase Orders."))
		if po.status == "Cancelled":
			throw(_("Cannot schedule deliveries on a cancelled Purchase Order."))

	def validate_scheduled_qty(self):
		if flt(self.scheduled_qty) <= 0:
			throw(_("Scheduled quantity must be greater than zero."))

	def validate_confirmation_status(self):
		if (
			self.confirmation_status == "Confirmed"
			and self.supplier_confirmed_date
			and getdate(self.supplier_confirmed_date) < getdate(self.scheduled_date)
		):
			frappe.msgprint(
				_(
					"Supplier confirmed date {0} is before the scheduled date {1}."
				).format(
					frappe.bold(self.supplier_confirmed_date),
					frappe.bold(self.scheduled_date),
				),
				alert=True,
			)
		if not self.supplier_confirmed_date and self.confirmation_status == "Confirmed":
			frappe.msgprint(
				_("Confirmation status is 'Confirmed' but no supplier confirmed date is set."),
				alert=True,
			)

	def validate_not_over_scheduled(self):
		"""Prevent scheduling more than the ordered quantity.

		Concurrency: the Purchase Order Item row is locked with ``FOR UPDATE`` so
		two users cannot simultaneously oversubscribe the same item.
		"""
		frappe.db.sql(LOCK_SQL, self.purchase_order_item)

		po_qty = flt(frappe.db.get_value("Purchase Order Item", self.purchase_order_item, "qty"))

		active_scheduled = flt(self.scheduled_qty) if not self.cancelled else 0.0
		other_schedules = frappe.db.get_all(
			"PO Delivery Schedule",
			filters={
				"delivery_plan": self.delivery_plan,
				"purchase_order_item": self.purchase_order_item,
				"cancelled": 0,
				"name": ("!=", self.name),
			},
			fields=["scheduled_qty"],
		)
		active_scheduled += flt(sum(flt(row.scheduled_qty) for row in other_schedules))

		if active_scheduled - po_qty > 1e-6:
			throw(
				_(
					"Item {0} on Purchase Order {1} is ordered for {2} units. "
					"The active schedules total {3} units, which exceeds the ordered "
					"quantity."
				).format(
					frappe.bold(self.item_code),
					frappe.bold(self.purchase_order),
					frappe.bold(po_qty),
					frappe.bold(flt(active_scheduled, 6)),
				)
			)

	def validate_no_duplicate(self):
		"""Prevent exact duplicate allocation rows for the same item + date + qty."""
		duplicates = frappe.db.get_all(
			"PO Delivery Schedule",
			filters={
				"delivery_plan": self.delivery_plan,
				"purchase_order_item": self.purchase_order_item,
				"scheduled_date": self.scheduled_date,
				"cancelled": 0,
				"name": ("!=", self.name),
			},
			fields=["name", "scheduled_qty"],
		)
		for dup in duplicates:
			if abs(flt(dup.scheduled_qty) - flt(self.scheduled_qty)) <= 1e-6:
				throw(
					_(
						"A schedule for item {0} on {1} with quantity {2} already exists "
						"as {3}. Adjust the quantity or scheduled date."
					).format(
						self.item_code,
						self.scheduled_date,
						flt(self.scheduled_qty),
						frappe.bold(dup.name),
					)
				)

	def on_update(self):
		# Recompute receipt tracking from the database (idempotent) whenever the
		# schedule itself is saved (quantity, date, cancellation, confirmation...).
		recalculate_schedule(self.name)