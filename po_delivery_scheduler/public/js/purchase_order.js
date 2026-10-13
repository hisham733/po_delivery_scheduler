// Copyright (c) 2026, CAF and Contributors
// License: MIT. See license.txt

frappe.ui.form.on("Purchase Order", {
	refresh: function (frm) {
		if (frm.is_new()) return;

		// Only submitted / active Purchase Orders support delivery scheduling,
		// and only for users who may read delivery plans. Read-only users can
		// still open an existing plan; creation is enforced server-side.
		const can_schedule =
			frm.doc.docstatus === 1 &&
			!["Cancelled", "Closed"].includes(frm.doc.status) &&
			frappe.model.can_read("PO Delivery Plan");

		if (!can_schedule) return;

		frm.add_custom_button(
			__("Manage Delivery Schedule"),
			function () {
				frappe.call({
					method:
						"po_delivery_scheduler.po_delivery_scheduler.api.get_or_create_delivery_plan",
					args: { purchase_order: frm.doc.name },
					callback: function (r) {
						if (!r.message) return;
						frappe.set_route("Form", "PO Delivery Plan", r.message.name);
					},
					freeze: true,
					freeze_message: __("Opening delivery schedule..."),
				});
			},
			__("Delivery Schedule")
		).removeClass("btn-default").addClass("btn-primary");
	},
});