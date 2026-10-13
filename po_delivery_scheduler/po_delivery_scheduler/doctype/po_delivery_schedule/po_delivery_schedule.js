// Copyright (c) 2026, CAF and contributors
// For license information, please see license.txt

frappe.ui.form.on("PO Delivery Schedule", {
	refresh: function (frm) {
		if (frm.is_new()) return;

		frm.set_df_property("scheduled_qty", "read_only", 1);
		frm.set_df_property("scheduled_date", "read_only", 1);
		frm.set_df_property("purchase_order_item", "read_only", 1);
		frm.set_df_property("cancelled", "read_only", 1);
		frm.set_df_property("received_qty", "read_only", 1);
		frm.set_df_property("outstanding_qty", "read_only", 1);
		frm.set_df_property("status", "read_only", 1);

		if (frm.doc.delivery_plan) {
			frm.add_custom_button(
				__("Delivery Plan"),
				function () {
					frappe.set_route("Form", "PO Delivery Plan", frm.doc.delivery_plan);
				},
				__("View")
			);
		}
	},

	onload_post_render: function (frm) {
		if (frm.is_new() && frm.doc.delivery_plan && !frm.doc.purchase_order_item) {
			// Preload eligible Purchase Order Items onto a fresh schedule.
			frappe.call({
				method: "frappe.client.get",
				args: { doctype: "PO Delivery Plan", name: frm.doc.delivery_plan },
				callback: function (r) {
					if (!r.message) return;
					frappe.call({
						method: "frappe.client.get_list",
						args: {
							doctype: "Purchase Order Item",
							filters: { parent: r.message.purchase_order },
							fields: ["name", "item_code", "item_name"],
							limit_page_length: 0,
						},
						callback: function (res) {
							if (res.message) {
								frm.fields_dict.purchase_order_item.query_options =
									res.message.map((d) => d.name);
							}
						},
					});
				},
			});
		}
	},
});