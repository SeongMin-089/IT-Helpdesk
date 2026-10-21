from odoo import models, fields
from odoo.exceptions import AccessError, UserError


class HelpdeskCloseWizard(models.TransientModel):
    _name = "it.helpdesk.close.wizard"
    _description = "IT Helpdesk 종료 승인"

    ticket_id = fields.Many2one(
        "it.helpdesk.ticket",
        string="문의",
        required=True,
        readonly=True,
    )

    def action_confirm(self):
        self.ensure_one()

        ticket = self.ticket_id

        if not ticket:
            raise UserError("종료할 문의를 찾을 수 없습니다.")

        if ticket.requester_id != self.env.user:
            raise AccessError(
                "문의를 등록한 요청자 본인만 종료를 승인할 수 있습니다."
            )

        ticket.action_close_ticket()

        return {"type": "ir.actions.act_window_close"}
