app_name = "pmo"
app_title = "PMO"
app_publisher = "Consultoria en Negocios y Aplicaciones"
app_description = "Project Management Office"
app_email = "it@buzola.mx"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "pmo",
# 		"logo": "/assets/pmo/logo.png",
# 		"title": "PMO",
# 		"route": "/pmo",
# 		"has_permission": "pmo.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/pmo/css/pmo.css"
# app_include_js = "/assets/pmo/js/pmo.js"

# include js, css files in header of web template
# web_include_css = "/assets/pmo/css/pmo.css"
# web_include_js = "/assets/pmo/js/pmo.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "pmo/public/scss/website"

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

# PMO — Task > Gantt ordenado por lft (nested set) en lugar de por fechas.
# El archivo se carga después del task_calendar.js de ERPNext y extiende
# frappe.views.calendar["Task"].gantt.order_by = "lft" (ASC nativo en GanttView).
doctype_calendar_js = {"Task": "public/js/task_calendar_pmo.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "pmo/public/icons.svg"

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

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "pmo.utils.jinja_methods",
# 	"filters": "pmo.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "pmo.install.before_install"
# after_install = "pmo.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "pmo.uninstall.before_uninstall"
# after_uninstall = "pmo.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "pmo.utils.before_app_install"
# after_app_install = "pmo.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "pmo.utils.before_app_uninstall"
# after_app_uninstall = "pmo.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "pmo.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "pmo.notifications.get_notification_config"

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

# P0 — Aislamiento READ de Project/Task (ADR-0002). Ver pmo/permissions.py.
permission_query_conditions = {
	"Project": "pmo.permissions.get_permission_query_conditions_project",
	"Task": "pmo.permissions.get_permission_query_conditions_task",
}

has_permission = {
	"Project": "pmo.permissions.has_permission_project",
	"Task": "pmo.permissions.has_permission_task",
}

# Fixtures: Custom Field pmo_members en Project + roles PMO (importados en migrate).
fixtures = [
	{"dt": "Custom Field", "filters": [["name", "in", ["Project-pmo_members"]]]},
	{"dt": "Role", "filters": [["name", "in", ["PMO Manager", "PMO Executive Access"]]]},
]

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

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"pmo.tasks.all"
# 	],
# 	"daily": [
# 		"pmo.tasks.daily"
# 	],
# 	"hourly": [
# 		"pmo.tasks.hourly"
# 	],
# 	"weekly": [
# 		"pmo.tasks.weekly"
# 	],
# 	"monthly": [
# 		"pmo.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "pmo.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "pmo.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "pmo.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "pmo.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["pmo.utils.before_request"]
# after_request = ["pmo.utils.after_request"]

# Job Events
# ----------
# before_job = ["pmo.utils.before_job"]
# after_job = ["pmo.utils.after_job"]

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
# 	"pmo.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
