{
    "name": "IT Helpdesk",
    "version": "1.0.0",
    "category": "Services",
    "summary": "사내 IT 장애 접수 및 처리 관리",
    "description": """
        Odoo 기반 사내 IT 장애 접수 및 해결 관리 시스템
    """,
    "author": "SeongMin",
    "depends": ["base", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/category_data.xml",
        "data/sequence_data.xml",
        "wizard/assignment_wizard_views.xml",
        "wizard/resolution_wizard_views.xml",
        "wizard/reopen_wizard_views.xml",
        "wizard/close_wizard_views.xml",
        "views/ticket_views.xml",
        "views/category_views.xml",
        "views/menu.xml",
    ],
    "application": True,
    "assets": {
        "web.assets_backend": [
            "it_helpdesk/static/src/dashboard/dashboard.js",
            "it_helpdesk/static/src/dashboard/dashboard.xml",
            "it_helpdesk/static/src/dashboard/dashboard.scss",
        ],
    },
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
