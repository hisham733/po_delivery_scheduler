// Copyright (c) 2026, CAF and contributors
// For license information, please see license.txt

frappe.query_reports["PO Delivery Overview"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "purchase_order",
			label: __("Purchase Order"),
			fieldtype: "Link",
			options: "Purchase Order",
		},
		{
			fieldname: "from_date",
			label: __("Scheduled From"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("Scheduled To"),
			fieldtype: "Date",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Planned",
				"Confirmed",
				"Partially Received",
				"Received",
				"Overdue",
				"Cancelled",
			],
		},
	],
};