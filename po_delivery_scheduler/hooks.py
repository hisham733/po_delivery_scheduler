app_name = "po_delivery_scheduler"
app_title = "PO Delivery Scheduler"
app_publisher = "CAF"
app_description = "Schedule multiple partial deliveries against a single Purchase Order"
app_email = "dev@example.com"
app_license = "mit"

required_apps = ["erpnext"]

# Apps
# ------------------

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "po_delivery_scheduler",
# 		"logo": "/assets/po_delivery_scheduler/logo.png",
# 		"title": "PO Delivery Scheduler",
# 		"route": "/po_delivery_scheduler",
# 		"has_permission": "po_delivery_scheduler.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/po_delivery_scheduler/css/po_delivery_scheduler.css"
# app_include_js = "/assets/po_delivery_scheduler/js/po_delivery_scheduler.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "po_delivery_scheduler/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

doctype_js = {
	"Purchase Order": "public/js/purchase_order.js",
	"Purchase Receipt": "public/js/purchase_receipt.js",
}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "po_delivery_scheduler/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "po_delivery_scheduler.utils.jinja_methods",
# 	"filters": "po_delivery_scheduler.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "po_delivery_scheduler.install.before_install"
# after_install = "po_delivery_scheduler.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "po_delivery_scheduler.uninstall.before_uninstall"
# after_uninstall = "po_delivery_scheduler.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "po_delivery_scheduler.utils.before_app_install"
# after_app_install = "po_delivery_scheduler.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "po_delivery_scheduler.utils.before_app_uninstall"
# after_app_uninstall = "po_delivery_scheduler.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "po_delivery_scheduler.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
	"Purchase Receipt": {
		"validate": "po_delivery_scheduler.po_delivery_scheduler.receipt_integration.validate_receipt_schedule_links",
		"on_submit": "po_delivery_scheduler.po_delivery_scheduler.receipt_integration.on_purchase_receipt_submit",
		"on_cancel": "po_delivery_scheduler.po_delivery_scheduler.receipt_integration.on_purchase_receipt_cancel",
		"on_trash": "po_delivery_scheduler.po_delivery_scheduler.receipt_integration.on_purchase_receipt_trash",
	},
	"Purchase Order": {
		"validate": "po_delivery_scheduler.po_delivery_scheduler.purchase_order_events.validate_schedules_against_po",
		"on_cancel": "po_delivery_scheduler.po_delivery_scheduler.purchase_order_events.on_purchase_order_cancel",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"po_delivery_scheduler.po_delivery_scheduler.reminders.send_delivery_reminders"
	],
}

# Fixtures (installed idempotently on migrate)
# --------------------------------------------

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "PO Delivery Scheduler"]]},
	{"dt": "Role", "filters": [["name", "=", "PO Delivery Manager"]]},
]
# }

# Testing
# -------

# before_tests = "po_delivery_scheduler.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "po_delivery_scheduler.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "po_delivery_scheduler.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["po_delivery_scheduler.utils.before_request"]
# after_request = ["po_delivery_scheduler.utils.after_request"]

# Job Events
# ----------
# before_job = ["po_delivery_scheduler.utils.before_job"]
# after_job = ["po_delivery_scheduler.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"po_delivery_scheduler.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

