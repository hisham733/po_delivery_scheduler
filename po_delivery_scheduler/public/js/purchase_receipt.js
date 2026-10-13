// Copyright (c) 2026, CAF and Contributors
// License: MIT. See license.txt

frappe.ui.form.on("Purchase Receipt", {
	setup: function (frm) {
		// Limit the "Delivery Schedule" link choices on each item line to
		// schedules that actually belong to that line's Purchase Order/Item.
		frm.set_query("po_delivery_schedule", "items", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			return {
				filters: {
					purchase_order: row.purchase_order || undefined,
					item_code: row.item_code || undefined,
					cancelled: 0,
					status: ["in", ["Planned", "Confirmed", "Partially Received", "Overdue"]],
				},
			};
		});
	},
});