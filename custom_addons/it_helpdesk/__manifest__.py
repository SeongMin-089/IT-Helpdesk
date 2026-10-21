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
        "security/ir.model.access.csv",
        "data/category_data.xml",
        "wizard/resolution_wizard_views.xml",
        "wizard/reopen_wizard_views.xml",
        "views/ticket_views.xml",
        "views/menu.xml",
    ],
    "application": True,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
