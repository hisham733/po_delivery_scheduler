frappe.views.calendar["PO Delivery Schedule"] = {
	field_map: {
		start: "scheduled_date",
		end: "scheduled_date",
		id: "name",
		title: "title",
		allDay: "allDay",
		color: "color",
	},
	order_by: "scheduled_date",
	filters: [
		{
			fieldtype: "Select",
			fieldname: "status",
			options: "Planned\nConfirmed\nPartially Received\nReceived\nOverdue\nCancelled",
			label: __("Status"),
		},
		{
			fieldtype: "Link",
			fieldname: "supplier",
			options: "Supplier",
			label: __("Supplier"),
		},
	],
	get_events_method: "po_delivery_scheduler.po_delivery_scheduler.api.get_calendar_events",
};
