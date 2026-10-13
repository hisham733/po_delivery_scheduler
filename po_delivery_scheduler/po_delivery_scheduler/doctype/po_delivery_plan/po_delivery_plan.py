# Copyright (c) 2026, CAF and contributors
# For license information, please see license.txt

import frappe
from frappe import _, throw
from frappe.model.document import Document

from po_delivery_scheduler.po_delivery_scheduler.utils import compute_plan_status


class PODeliveryPlan(Document):
	def before_insert(self):
		po = frappe.get_cached_doc("Purchase Order", self.purchase_order)
		if not self.supplier:
			self.supplier = po.supplier
		if not self.company:
			self.company = po.company
		if not self.owner_user:
			self.owner_user = frappe.session.user

	def validate(self):
		self.validate_purchase_order()
		self.validate_unique_plan()

	def validate_purchase_order(self):
		po = frappe.get_doc("Purchase Order", self.purchase_order)

		if po.docstatus != 1:
			throw(_("A delivery plan can only be created for a submitted Purchase Order."))

		if po.status == "Cancelled":
			throw(_("Cannot create a delivery plan for a cancelled Purchase Order."))

		if po.status == "Closed":
			throw(_("Cannot create a delivery plan for a closed Purchase Order."))

		self.supplier = self.supplier or po.supplier
		self.company = self.company or po.company

		if self.supplier and self.supplier != po.supplier:
			throw(
				_("Supplier {0} does not match the Purchase Order supplier {1}.").format(
					self.supplier, po.supplier
				)
			)

		if self.company and self.company != po.company:
			throw(
				_("Company {0} does not match the Purchase Order company {1}.").format(
					self.company, po.company
				)
			)

	def validate_unique_plan(self):
		existing = frappe.db.get_value(
			"PO Delivery Plan",
			{"purchase_order": self.purchase_order, "name": ("!=", self.name)},
			"name",
		)
		if existing:
			throw(
				_("A delivery plan {0} already exists for Purchase Order {1}.").format(
					frappe.bold(existing), frappe.bold(self.purchase_order)
				)
			)

	def after_insert(self):
		self.db_set("status", compute_plan_status(self))

	def on_update(self):
		self.db_set("status", compute_plan_status(self), update_modified=False)

	def cancel_plan(self):
		"""Cancel the plan and all open schedules on it."""
		self.db_set("status", "Cancelled")

		open_schedules = frappe.get_all(
			"PO Delivery Schedule",
			filters={"delivery_plan": self.name, "cancelled": 0},
			pluck="name",
		)
		for name in open_schedules:
			frappe.db.set_value(
				"PO Delivery Schedule",
				name,
				{
					"cancelled": 1,
					"cancellation_reason": _("Delivery plan cancelled"),
					"status": "Cancelled",
				},
				update_modified=False,
			)

	def activate(self):
		"""Activate a plan by ensuring it is not cancelled."""
		if self.status == "Cancelled":
			frappe.throw(
				_("A cancelled delivery plan cannot be re-activated. Create a new one instead.")
			)
		self.db_set("status", compute_plan_status(self))