
from odoo import models, fields


class HelpdeskReopenWizard(models.TransientModel):
    _name = 'it.helpdesk.reopen.wizard'
    _description = 'IT Helpdesk Reopen Wizard'

    ticket_id = fields.Many2one(
        'it.helpdesk.ticket',
        string='대상 문의',
        required=True,
        readonly=True,
    )

    reason = fields.Text(
        string='재처리 사유',
        required=True,
    )
