from odoo import api, models
from odoo.exceptions import AccessError


class HelpdeskAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.model_create_multi
    def create(self, vals_list):
        # IT Helpdesk 문의에 직접 연결되는 첨부파일 검사
        ticket_ids = {
            vals.get("res_id")
            for vals in vals_list
            if vals.get("res_model") == "it.helpdesk.ticket" and vals.get("res_id")
        }

        if ticket_ids:
            tickets = (
                self.env["it.helpdesk.ticket"]
                .sudo()
                .with_context(active_test=False)
                .browse(list(ticket_ids))
                .exists()
            )

            closed_ids = set(
                tickets.filtered(lambda ticket: ticket.state == "closed").ids
            )

            for vals in vals_list:
                if (
                    vals.get("res_model") == "it.helpdesk.ticket"
                    and vals.get("res_id") in closed_ids
                ):
                    raise AccessError("종료된 문의에는 첨부파일을 추가할 수 없습니다.")

        return super().create(vals_list)
