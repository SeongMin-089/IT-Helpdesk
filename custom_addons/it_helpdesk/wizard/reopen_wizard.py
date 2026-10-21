from odoo import models, fields
from odoo.exceptions import AccessError, UserError, ValidationError


class HelpdeskReopenWizard(models.TransientModel):
    _name = "it.helpdesk.reopen.wizard"
    _description = "IT Helpdesk 재처리 요청"

    ticket_id = fields.Many2one(
        "it.helpdesk.ticket",
        string="문의",
        required=True,
        readonly=True,
    )

    reason = fields.Text(
        string="재처리 사유",
        required=True,
    )

    def action_confirm(self):
        self.ensure_one()

        ticket = self.ticket_id

        if not ticket:
            raise UserError("재처리할 문의를 찾을 수 없습니다.")

        if ticket.requester_id != self.env.user:
            raise AccessError(
                "문의를 등록한 요청자 본인만 재처리를 요청할 수 있습니다."
            )

        if ticket.state != "resolved":
            raise UserError(
                "해결 상태의 문의만 재처리를 요청할 수 있습니다."
            )

        reason = (self.reason or "").strip()

        if not reason:
            raise ValidationError(
                "재처리 사유를 입력해 주세요."
            )

        # Ticket 모델에서 권한·상태·이력 처리를 수행
        ticket.action_request_reopen(reason)

        return {"type": "ir.actions.act_window_close"}
