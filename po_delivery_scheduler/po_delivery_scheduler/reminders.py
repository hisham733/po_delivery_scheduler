# Copyright (c) 2026, CAF and Contributors
# See license.txt

"""Daily reminders about upcoming / overdue deliveries.

Design
------
* Runs daily through the Frappe scheduler (``send_delivery_reminders``).
* Only schedules whose plan has ``reminders_enabled`` and is not Cancelled are
  considered; cancelled and fully-received schedules are skipped.
* Emails are sent to the internal responsible user (``PO Delivery Plan.owner_user``)
  only. Suppliers are never emailed by this feature in the MVP.
* Idempotency: ``last_reminder_date`` records the day a schedule was last
  reminded. A schedule is only reminded once per calendar day.
* If outbound email is not configured, ``frappe.sendmail`` is wrapped so the
  scheduler job never fails; the failure is recorded in ``reminder_note`` and
  logged via ``frappe.log_error``.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate


def _today():
	return getdate(nowdate())


def _due_flags(schedule, plan, today=None):
	"""Classify a schedule into reminder buckets."""
	today = today or _today()
	flags = frappe._dict(
		overdue=False,
		due_today=False,
		due_soon=False,
		confirmed_date_passed=False,
	)

	if schedule.get("status") == "Received" or schedule.get("cancelled"):
		return flags

	if schedule.get("received_qty") and flt(schedule.get("received_qty")) >= flt(
		schedule.get("scheduled_qty")
	):
		return flags

	scheduled_date = schedule.get("scheduled_date")
	if scheduled_date:
		d = getdate(scheduled_date)
		if d < today:
			flags.overdue = True
		elif d == today:
			flags.due_today = True
		elif d <= add_days(today, flt(plan.get("reminder_lead_days") or 0)):
			flags.due_soon = True

	confirmed_date = schedule.get("supplier_confirmed_date")
	if confirmed_date and getdate(confirmed_date) < today:
		flags.confirmed_date_passed = True

	return flags


def get_due_deliveries(today=None):
	"""Return schedules that need a reminder, with their flags.

	This is the pure, testable core of the reminder job. It never sends email.
	"""
	today = today or _today()

	schedule = frappe.qb.DocType("PO Delivery Schedule")
	plan = frappe.qb.DocType("PO Delivery Plan")

	rows = (
		frappe.qb.from_(schedule)
		.inner_join(plan)
		.on(plan.name == schedule.delivery_plan)
		.select(
			schedule.name,
			schedule.delivery_plan,
			schedule.purchase_order,
			schedule.item_code,
			schedule.item_name,
			schedule.scheduled_date,
			schedule.scheduled_qty,
			schedule.uom,
			schedule.supplier_confirmed_date,
			schedule.confirmation_status,
			schedule.received_qty,
			schedule.outstanding_qty,
			schedule.status,
			schedule.cancelled,
			schedule.last_reminder_date,
			schedule.owner,
			plan.owner_user,
			plan.reminders_enabled,
			plan.reminder_lead_days,
			plan.status.as_("plan_status"),
		)
		.where(
			(plan.reminders_enabled == 1)
			& (plan.status != "Cancelled")
			& (schedule.cancelled == 0)
			& (schedule.status != "Received")
			& (schedule.scheduled_date.isnotnull())
			& (
				(schedule.last_reminder_date.isnull())
				| (schedule.last_reminder_date < today.isoformat())
			)
		)
	).run(as_dict=1)

	due = []
	for row in rows:
		flags = _due_flags(row, row, today=today)
		if any(flags.values()):
			row.flags = flags
			due.append(row)
	return due


def _build_message_lines(schedule):
	"""Human-readable bullet lines describing why a delivery needs attention."""
	flags = schedule.flags
	lines = []
	if flags.overdue:
		lines.append(_("Overdue: scheduled delivery date {} has passed.").format(schedule.scheduled_date))
	if flags.due_today:
		lines.append(_("Due today ({}) - no full receipt yet.").format(schedule.scheduled_date))
	if flags.due_soon:
		lines.append(
			_("Due soon ({}): scheduled within the reminder window.").format(schedule.scheduled_date)
		)
	if flags.confirmed_date_passed:
		lines.append(
			_("Supplier confirmed date {} has passed but the delivery is not fully received.").format(
				schedule.supplier_confirmed_date
			)
		)
	return lines


def _enqueue_email(owner_user, subject, message):
	"""Send one email, tolerating an unconfigured outbound mail server."""
	try:
		frappe.sendmail(
			recipients=[owner_user],
			subject=subject,
			message=message,
			reference_doctype="PO Delivery Plan",
			communication_type="Automated Message",
		)
		return None
	except Exception as exc:  # noqa: BLE001 - must never break the scheduler job
		frappe.log_error(
			title=_("PO Delivery reminder email failed"),
			message=f"recipient={owner_user}\nerror={exc}",
			reference_doctype="PO Delivery Schedule",
		)
		return f"Email failed: {exc}"


def send_delivery_reminders(commit: bool = True):
	"""Scheduler entry point: send one digest per owner, idempotently per day."""
	due = get_due_deliveries()
	if not due:
		return 0

	by_owner: dict = {}
	for schedule in due:
		key = schedule.get("owner_user") or schedule.get("owner")
		by_owner.setdefault(key, []).append(schedule)

	sent = 0
	for owner_user, schedules in by_owner.items():
		lines = []
		for schedule in schedules:
			subject_piece = ", ".join(_build_message_lines(schedule))
			schedule.reminder_label = (
				f"{schedule.item_code} {schedule.scheduled_date} - {subject_piece}"
			)
			lines.append(f"<li>{schedule.reminder_label}</li>")
			schedule._marked = True

		html = (
			"<p>" + _("The following scheduled deliveries need attention:") + "</p><ul>" + "".join(lines) + "</ul>"
		)
		error = _enqueue_email(owner_user, _("PO Delivery Schedule Reminder"), html)

		for schedule in schedules:
			note = "Reminded " + _today().isoformat()
			if error:
				note = f"Reminder FAILED: {error}"
			frappe.db.set_value(
				"PO Delivery Schedule",
				schedule.name,
				{"last_reminder_date": _today().isoformat(), "reminder_note": note},
				update_modified=False,
			)
			sent += 1

	if commit:
		frappe.db.commit()
	return sent