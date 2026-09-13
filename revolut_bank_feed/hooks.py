app_name = "revolut_bank_feed"
app_title = "Revolut Bank Feed"
app_publisher = "Revolut Bank Feed contributors"
app_description = "Read-only Revolut Business bank feeds for ERPNext"
app_email = ""
app_license = "MIT"
required_apps = ["erpnext"]
app_home = "/desk/revolut-setup"
app_logo_url = "/assets/revolut_bank_feed/images/bank-feed.svg"
add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": app_logo_url,
        "route": app_home,
        "has_permission": "revolut_bank_feed.navigation.has_app_permission",
    }
]

before_install = "revolut_bank_feed.install.check_versions"
after_install = "revolut_bank_feed.install.after_migrate"
after_migrate = "revolut_bank_feed.install.after_migrate"
before_uninstall = "revolut_bank_feed.install.before_uninstall"

scheduler_events = {
    "cron": {
        "*/15 * * * *": ["revolut_bank_feed.sync.schedule"],
        "7 * * * *": ["revolut_bank_feed.enrichment.schedule"],
    },
    "daily": ["revolut_bank_feed.sync.cleanup"],
}

doc_events = {
    "Bank Transaction": {
        "validate": "revolut_bank_feed.guards.validate_bank_transaction",
        "before_update_after_submit": "revolut_bank_feed.guards.validate_bank_transaction",
        "before_cancel": "revolut_bank_feed.guards.before_cancel",
        "on_trash": "revolut_bank_feed.guards.before_delete",
    },
}
