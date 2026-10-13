// Copyright (c) 2026, CAF and contributors
// For license information, please see license.txt

frappe.ui.form.on("PO Delivery Plan", {
	refresh: function (frm) {
		if (!frm.is_new() && frm.doc.purchase_order) {
			frm.add_custom_button(
				__("Purchase Order"),
				function () {
					frappe.set_route("Form", "Purchase Order", frm.doc.purchase_order);
				},
				__("View")
			);

			frm.add_custom_button(
				__("Add Schedule Entry"),
				function () {
					open_add_schedule_dialog(frm);
				},
				__("Delivery Schedule")
			);

			frm.add_custom_button(
				__("Recalculate"),
				function () {
					frappe.call({
						method:
							"po_delivery_scheduler.po_delivery_scheduler.api.recalculate_plan",
						args: { delivery_plan: frm.doc.name },
						callback: function () {
							frappe.show_alert({ message: __("Delivery plan recalculated"), indicator: "green" });
							frm.reload_doc();
						},
						freeze: true,
					});
				},
				__("Delivery Schedule")
			);

			frm.add_custom_button(
				__("Cancel Plan"),
				function () {
					cancel_plan(frm);
				},
				__("Delivery Schedule")
			);

			render_schedules(frm);
		}
	},
});

function render_schedules(frm) {
	frappe.call({
		method: "po_delivery_scheduler.po_delivery_scheduler.api.get_plan_schedules",
		args: { delivery_plan: frm.doc.name },
		callback: function (r) {
			set_schedules_html(frm, r.message || []);
		},
	});
}

const STATUS_COLORS = {
	"Planned": "gray",
	"Confirmed": "blue",
	"Partially Received": "orange",
	"Received": "green",
	"Overdue": "red",
	"Cancelled": "darkgrey",
};

function set_schedules_html(frm, schedules) {
	const wrapper = frm.get_field("schedules_html").$wrapper;
	if (!schedules.length) {
		wrapper.html(
			'<div class="text-muted" style="padding: 8px;">' +
				__("No delivery schedule entries yet. Use 'Add Schedule Entry' above.") +
			"</div>"
		);
		return;
	}

	let rows = schedules
		.map(function (s) {
			const color = STATUS_COLORS[s.status] || "gray";
			const actions =
				'<button class="btn btn-xs btn-default" data-action="edit" data-name="' +
				s.name +
				'">' +
				__("Edit") +
				"</button> ";
			actions +=
				s.cancelled
					? '<button class="btn btn-xs btn-default" data-action="reopen" data-name="' +
					  s.name +
					  '">' +
					  __("Re-open") +
					  "</button>"
					: '<button class="btn btn-xs btn-danger" data-action="cancel" data-name="' +
					  s.name +
					  '">' +
					  __("Cancel") +
					  "</button>";
			return (
				"<tr>" +
				'<td><a href="/app/po-delivery-schedule/' +
				s.name +
				'">' +
				s.name +
				"</a></td>" +
				"<td>" +
				(s.item_code || "") +
				"</td>" +
				"<td>" +
				(s.item_name || "") +
				"</td>" +
				"<td>" +
				(s.scheduled_date || "") +
				"</td>" +
				"<td class='text-right'>" +
				s.scheduled_qty +
				"</td>" +
				"<td>" +
				(s.uom || "") +
				"</td>" +
				"<td>" +
				(s.confirmation_status || "") +
				"</td>" +
				"<td>" +
				(s.supplier_confirmed_date || "") +
				"</td>" +
				"<td class='text-right'>" +
				(s.received_qty || 0) +
				"</td>" +
				"<td class='text-right'>" +
				(s.outstanding_qty || 0) +
				"</td>" +
				'<td><span class="indicator-pill ' +
				color +
				'">' +
				s.status +
				"</span></td>" +
				"<td>" +
				actions +
				"</td>" +
				"</tr>"
			);
		})
		.join("");

	const html =
		'<table class="table table-bordered table-hover" style="margin-top: 8px;">' +
		"<thead><tr>" +
		"<th>" +
		__("Schedule") +
		"</th>" +
		"<th>" +
		__("Item Code") +
		"</th>" +
		"<th>" +
		__("Item Name") +
		"</th>" +
		"<th>" +
		__("Date") +
		"</th>" +
		"<th>" +
		__("Qty") +
		"</th>" +
		"<th>" +
		__("UOM") +
		"</th>" +
		"<th>" +
		__("Confirmation") +
		"</th>" +
		"<th>" +
		__("Confirmed Date") +
		"</th>" +
		"<th>" +
		__("Received") +
		"</th>" +
		"<th>" +
		__("Outstanding") +
		"</th>" +
		"<th>" +
		__("Status") +
		"</th>" +
		"<th>" +
		__("Actions") +
		"</th>" +
		"</tr></thead><tbody>" +
		rows +
		"</tbody></table>";

	wrapper.html(html);

	wrapper.find("[data-action]").on("click", function () {
		const action = $(this).data("action");
		const name = $(this).data("name");
		if (action === "edit") {
			frappe.set_route("Form", "PO Delivery Schedule", name);
		} else if (action === "cancel") {
			cancel_schedule(frm, name);
		} else if (action === "reopen") {
			reopen_schedule(frm, name);
		}
	});
}

function open_add_schedule_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Schedule Entry"),
		fields: [
			{
				fieldname: "purchase_order_item",
				label: __("Item"),
				fieldtype: "Autocomplete",
				reqd: 1,
				get_query: function () {
					return {
						query:
							"po_delivery_scheduler.po_delivery_scheduler.api.get_po_item_query",
						params: { purchase_order: frm.doc.purchase_order },
					};
				},
			},
			{
				fieldname: "scheduled_date",
				label: __("Scheduled Delivery Date"),
				fieldtype: "Date",
				reqd: 1,
			},
			{ fieldname: "scheduled_qty", label: __("Scheduled Quantity"), fieldtype: "Float", reqd: 1 },
			{
				fieldname: "confirmation_status",
				label: __("Confirmation Status"),
				fieldtype: "Select",
				options: ["Not Requested", "Awaiting Confirmation", "Confirmed", "Rejected"],
				default: "Not Requested",
			},
			{
				fieldname: "supplier_confirmed_date",
				label: __("Supplier Confirmed Date"),
				fieldtype: "Date",
			},
			{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text" },
		],
		primary_action_label: __("Create"),
		primary_action: function (values) {
			frappe.call({
				method: "po_delivery_scheduler.po_delivery_scheduler.api.create_schedule_entry",
				args: {
					delivery_plan: frm.doc.name,
					purchase_order_item: values.purchase_order_item,
					scheduled_date: values.scheduled_date,
					scheduled_qty: values.scheduled_qty,
					confirmation_status: values.confirmation_status,
					supplier_confirmed_date: values.supplier_confirmed_date,
					remarks: values.remarks,
				},
				callback: function (r) {
					if (r.message) {
						dialog.hide();
						frappe.show_alert({
							message: __("Schedule created: {0}", [r.message.name]),
							indicator: "green",
						});
						frm.reload_doc();
					}
				},
				freeze: true,
			});
		},
	});

	dialog.show();

	// After picking an item, Awesomplete replaces the input with the raw value
	// (the Purchase Order Item row name). Keep the readable "ITEM CODE - name"
	// label in the box instead; the underlying value is still the row name,
	// which get_input_value() recovers from the label -> value mapping.
	const item_field = dialog.fields_dict.purchase_order_item;
	if (item_field && item_field.awesomplete) {
		item_field.awesomplete.replace = function (text) {
			this.input.value = text.label;
		};
	}
}

function cancel_schedule(frm, name) {
	frappe.confirm(
		__("Cancel delivery schedule {0}?", [name]),
		function () {
			frappe.call({
				method: "po_delivery_scheduler.po_delivery_scheduler.api.cancel_schedule",
				args: { schedule_name: name, cancellation_reason: __("Cancelled from plan form") },
				callback: function () {
					frappe.show_alert({ message: __("Schedule cancelled"), indicator: "orange" });
					frm.reload_doc();
				},
				freeze: true,
			});
		}
	);
}

function reopen_schedule(frm, name) {
	frappe.call({
		method: "po_delivery_scheduler.po_delivery_scheduler.api.reopen_schedule",
		args: { schedule_name: name },
		callback: function () {
			frappe.show_alert({ message: __("Schedule re-opened"), indicator: "green" });
			frm.reload_doc();
		},
		freeze: true,
	});
}

function cancel_plan(frm) {
	frappe.confirm(
		__("Cancel the whole delivery plan and all open schedules?"),
		function () {
			frappe.call({
				method: "po_delivery_scheduler.po_delivery_scheduler.api.cancel_plan",
				args: { delivery_plan: frm.doc.name },
				callback: function () {
					frappe.show_alert({ message: __("Delivery plan cancelled"), indicator: "orange" });
					frm.reload_doc();
				},
				freeze: true,
			});
		}
	);
}