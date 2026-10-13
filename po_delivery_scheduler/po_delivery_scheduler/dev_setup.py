"""Developer helper to bootstrap DocTypes, custom fields, role and report.

Run with:
    bench --site development.localhost execute \
        po_delivery_scheduler.po_delivery_scheduler.dev_setup.run

In developer_mode Frappe writes the generated DocType JSON files back into the
app module folder, which is what we version as the app source of truth.
"""

import frappe

MODULE = "PO Delivery Scheduler"
APP = "po_delivery_scheduler"

# DocPerm child rows default every boolean to 1, so every flag must be set
# explicitly to avoid accidentally granting create/write/delete to read-only roles.
PERMISSION_FLAGS = (
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"share",
	"print",
	"email",
	"select",
	"import",
	"if_owner",
)


def perm(role: str, **flags) -> dict:
	row = {flag: 0 for flag in PERMISSION_FLAGS}
	row["role"] = role
	row.update(flags)
	return row


PLAN_PERMISSIONS = [
	perm("System Manager", read=1, write=1, create=1, delete=1, report=1, export=1, share=1, print=1, email=1),
	perm("Purchase Manager", read=1, write=1, create=1, delete=1, report=1, export=1, share=1, print=1, email=1),
	perm("Purchase User", read=1, report=1, export=1, print=1, email=1),
	perm("Stock Manager", read=1, report=1, export=1, print=1, email=1),
	perm("Stock User", read=1, print=1, email=1),
	perm("PO Delivery Manager", read=1, write=1, create=1, delete=1, report=1, export=1, share=1, print=1, email=1),
]

PLAN_FIELDS = [
	{"fieldname": "section_break_po", "fieldtype": "Section Break", "label": "Purchase Order"},
	{
		"fieldname": "purchase_order",
		"fieldtype": "Link",
		"label": "Purchase Order",
		"options": "Purchase Order",
		"reqd": 1,
		"unique": 1,
		"in_list_view": 1,
		"in_standard_filter": 1,
	},
	{
		"fieldname": "supplier",
		"fieldtype": "Link",
		"label": "Supplier",
		"options": "Supplier",
		"reqd": 1,
		"in_list_view": 1,
		"in_standard_filter": 1,
	},
	{
		"fieldname": "company",
		"fieldtype": "Link",
		"label": "Company",
		"options": "Company",
		"reqd": 1,
		"in_standard_filter": 1,
	},
	{"fieldname": "column_break_po", "fieldtype": "Column Break"},
	{
		"fieldname": "status",
		"fieldtype": "Select",
		"label": "Status",
		"options": "Draft\nActive\nCompleted\nCancelled",
		"default": "Draft",
		"read_only": 1,
		"in_list_view": 1,
		"in_standard_filter": 1,
	},
	{
		"fieldname": "po_status",
		"fieldtype": "Data",
		"label": "Purchase Order Status",
		"read_only": 1,
		"fetch_from": "purchase_order.status",
	},
	{
		"fieldname": "owner_user",
		"fieldtype": "Link",
		"label": "Responsible Purchasing User",
		"options": "User",
		"default": "__user",
		"description": "Internal user that receives delivery reminders.",
	},
	{"fieldname": "section_break_settings", "fieldtype": "Section Break", "label": "Settings"},
	{
		"fieldname": "reminders_enabled",
		"fieldtype": "Check",
		"label": "Reminders Enabled",
		"default": "1",
	},
	{
		"fieldname": "reminder_lead_days",
		"fieldtype": "Int",
		"label": "Reminder Lead Days",
		"default": "3",
		"description": "Send 'due soon' reminders this many days before the scheduled date.",
	},
	{"fieldname": "column_break_settings", "fieldtype": "Column Break"},
	{"fieldname": "notes", "fieldtype": "Small Text", "label": "Notes"},
	{"fieldname": "section_break_schedules", "fieldtype": "Section Break"},
	{
		"fieldname": "schedules_html",
		"fieldtype": "HTML",
		"label": "Delivery Schedule Entries",
	},
]

SCHEDULE_FIELDS = [
	{"fieldname": "section_break_po", "fieldtype": "Section Break", "label": "Purchase Order"},
	{
		"fieldname": "delivery_plan",
		"fieldtype": "Link",
		"label": "Delivery Plan",
		"options": "PO Delivery Plan",
		"reqd": 1,
		"in_standard_filter": 1,
	},
	{
		"fieldname": "purchase_order",
		"fieldtype": "Link",
		"label": "Purchase Order",
		"options": "Purchase Order",
		"reqd": 1,
		"in_list_view": 1,
		"in_standard_filter": 1,
	},
	{
		"fieldname": "supplier",
		"fieldtype": "Link",
		"label": "Supplier",
		"options": "Supplier",
		"reqd": 1,
		"in_standard_filter": 1,
	},
	{
		"fieldname": "company",
		"fieldtype": "Link",
		"label": "Company",
		"options": "Company",
		"reqd": 1,
		"in_standard_filter": 1,
	},
	{"fieldname": "column_break_po", "fieldtype": "Column Break"},
	{
		"fieldname": "purchase_order_item",
		"fieldtype": "Link",
		"label": "Purchase Order Item",
		"options": "Purchase Order Item",
		"reqd": 1,
		"ignore_user_permissions": 1,
	},
	{
		"fieldname": "item_code",
		"fieldtype": "Link",
		"label": "Item Code",
		"options": "Item",
		"reqd": 1,
		"in_list_view": 1,
		"in_standard_filter": 1,
	},
	{
		"fieldname": "item_name",
		"fieldtype": "Data",
		"label": "Item Name",
		"fetch_from": "purchase_order_item.item_name",
		"read_only": 1,
	},
	{"fieldname": "section_break_schedule", "fieldtype": "Section Break", "label": "Schedule"},
	{
		"fieldname": "scheduled_date",
		"fieldtype": "Date",
		"label": "Scheduled Delivery Date",
		"reqd": 1,
		"in_list_view": 1,
	},
	{
		"fieldname": "scheduled_qty",
		"fieldtype": "Float",
		"label": "Scheduled Quantity",
		"reqd": 1,
		"in_list_view": 1,
	},
	{"fieldname": "uom", "fieldtype": "Link", "label": "UOM", "options": "UOM", "reqd": 1},
	{
		"fieldname": "conversion_factor",
		"fieldtype": "Float",
		"label": "UOM Conversion Factor",
		"read_only": 1,
		"default": "1",
		"description": "Conversion factor of the Purchase Order Item UOM to the stock UOM.",
	},
	{"fieldname": "column_break_schedule", "fieldtype": "Column Break"},
	{
		"fieldname": "status",
		"fieldtype": "Select",
		"label": "Status",
		"options": "Planned\nConfirmed\nPartially Received\nReceived\nOverdue\nCancelled",
		"default": "Planned",
		"read_only": 1,
		"in_list_view": 1,
		"in_standard_filter": 1,
	},
	{"fieldname": "cancelled", "fieldtype": "Check", "label": "Cancelled", "default": "0"},
	{"fieldname": "cancellation_reason", "fieldtype": "Small Text", "label": "Cancellation Reason"},
	{"fieldname": "section_break_confirmation", "fieldtype": "Section Break", "label": "Supplier Confirmation"},
	{
		"fieldname": "confirmation_status",
		"fieldtype": "Select",
		"label": "Confirmation Status",
		"options": "Not Requested\nAwaiting Confirmation\nConfirmed\nRejected",
		"default": "Not Requested",
		"in_standard_filter": 1,
	},
	{"fieldname": "supplier_confirmed_date", "fieldtype": "Date", "label": "Supplier Confirmed Date"},
	{"fieldname": "column_break_confirmation", "fieldtype": "Column Break"},
	{"fieldname": "remarks", "fieldtype": "Small Text", "label": "Remarks"},
	{"fieldname": "section_break_tracking", "fieldtype": "Section Break", "label": "Receipt Tracking"},
	{
		"fieldname": "received_qty",
		"fieldtype": "Float",
		"label": "Received Quantity",
		"read_only": 1,
		"no_copy": 1,
		"in_list_view": 1,
	},
	{
		"fieldname": "outstanding_qty",
		"fieldtype": "Float",
		"label": "Outstanding Quantity",
		"read_only": 1,
		"no_copy": 1,
		"in_list_view": 1,
	},
	{"fieldname": "column_break_tracking", "fieldtype": "Column Break"},
	{
		"fieldname": "last_reminder_date",
		"fieldtype": "Date",
		"label": "Last Reminder Date",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "reminder_note",
		"fieldtype": "Small Text",
		"label": "Reminder Note",
		"read_only": 1,
		"no_copy": 1,
	},
]

PLAN_DOCTYPE = {
	"doctype": "DocType",
	"name": "PO Delivery Plan",
	"module": MODULE,
	"custom": 0,
	"is_submittable": 0,
	"track_changes": 1,
	"engine": "InnoDB",
	"allow_rename": 1,
	"autoname": "PODP-.#####",
	"title_field": "purchase_order",
	"search_fields": "purchase_order, supplier, company",
	"sort_field": "modified",
	"sort_order": "DESC",
	"row_format": "Dynamic",
	"fields": PLAN_FIELDS,
	"permissions": PLAN_PERMISSIONS,
}

SCHEDULE_DOCTYPE = {
	"doctype": "DocType",
	"name": "PO Delivery Schedule",
	"module": MODULE,
	"custom": 0,
	"is_submittable": 0,
	"track_changes": 1,
	"engine": "InnoDB",
	"allow_rename": 1,
	"autoname": "PODS-.#####",
	"title_field": "item_code",
	"search_fields": "purchase_order, item_code, supplier",
	"sort_field": "scheduled_date",
	"sort_order": "ASC",
	"row_format": "Dynamic",
	"fields": SCHEDULE_FIELDS,
	"permissions": PLAN_PERMISSIONS,
}

CUSTOM_FIELDS = [
	{
		"doctype": "Custom Field",
		"dt": "Purchase Receipt Item",
		"fieldname": "po_delivery_schedule",
		"fieldtype": "Link",
		"label": "Delivery Schedule",
		"options": "PO Delivery Schedule",
		"insert_after": "purchase_order_item",
		"description": "Optional: link this receipt line to the planned delivery it fulfils.",
		"module": MODULE,
	},
]


def upsert_doctype(definition: dict) -> None:
	name = definition["name"]
	if frappe.db.exists("DocType", name):
		# DocType already exists (e.g. re-run): only ensure the record is present.
		print(f"DocType {name} already exists")
		return
	frappe.get_doc(definition).insert(ignore_permissions=True)
	print(f"Created DocType {name}")


def upsert_custom_field(definition: dict) -> None:
	name = f"{definition['dt']}-{definition['fieldname']}"
	if frappe.db.exists("Custom Field", name):
		print(f"Custom Field {name} already exists")
		return
	frappe.get_doc(definition).insert(ignore_permissions=True)
	print(f"Created Custom Field {name}")


def ensure_role() -> None:
	if frappe.db.exists("Role", "PO Delivery Manager"):
		print("Role PO Delivery Manager already exists")
		return
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": "PO Delivery Manager",
			"desk_access": 1,
			"two_factor_auth": 0,
		}
	).insert(ignore_permissions=True)
	print("Created role PO Delivery Manager")


def sync_permissions() -> None:
	for doctype in ("PO Delivery Plan", "PO Delivery Schedule"):
		if not frappe.db.exists("DocType", doctype):
			continue
		doc = frappe.get_doc("DocType", doctype)
		doc.set("permissions", PLAN_PERMISSIONS)
		doc.save(ignore_permissions=True)
		print(f"Synced permissions for {doctype}")


REPORT_ROLES = [
	"System Manager",
	"Purchase Manager",
	"Purchase User",
	"Stock Manager",
	"Stock User",
	"PO Delivery Manager",
]


def create_report() -> None:
	if frappe.db.exists("Report", "PO Delivery Overview"):
		print("Report PO Delivery Overview already exists")
		return
	frappe.get_doc(
		{
			"doctype": "Report",
			"name": "PO Delivery Overview",
			"report_name": "PO Delivery Overview",
			"ref_doctype": "PO Delivery Schedule",
			"report_type": "Script Report",
			"is_standard": "Yes",
			"module": MODULE,
			"roles": [{"role": role} for role in REPORT_ROLES],
		}
	).insert(ignore_permissions=True)
	print("Created report PO Delivery Overview")


def run() -> None:
	ensure_role()
	upsert_doctype(PLAN_DOCTYPE)
	upsert_doctype(SCHEDULE_DOCTYPE)
	sync_permissions()
	for cf in CUSTOM_FIELDS:
		upsert_custom_field(cf)
	create_report()
	frappe.db.commit()
	frappe.clear_cache()
	print("dev_setup complete")
