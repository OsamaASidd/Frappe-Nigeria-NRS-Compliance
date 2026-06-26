import frappe


def check_app_permission():
    """Allow the NRS Compliance app/workspace for any authenticated user."""
    return frappe.session.user != "Guest"
