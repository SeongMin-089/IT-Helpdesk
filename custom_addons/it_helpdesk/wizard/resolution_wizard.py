from odoo import models, fields


class HelpdeskResolutionWizard(models.TransientModel):
    _name = "it.helpdesk.resolution.wizard"
    _description = "IT Helpdesk Resolution Wizard"

    ticket_id = fields.Many2one(
        "it.helpdesk.ticket",
        string="대상 문의",
        required=True,
        readonly=True,
    )

    resolution_method = fields.Selection(
        [
            ("onsite", "현장 방문"),
            ("remote", "원격/안내"),
        ],
        string="해결 방식", 
        required=True,
    )

    resolution = fields.Text(
        string="해결 내용",
        required=True,
    )
