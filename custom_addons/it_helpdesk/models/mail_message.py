from odoo import api, models
from odoo.exceptions import AccessError, UserError


class HelpdeskMailMessage(models.Model):
    _inherit = "mail.message"

    @api.model_create_multi
    def create(self, vals_list):
        # IT Helpdesk 종료 문의에 연결된 새 메시지를 차단
        ticket_ids = {
            vals.get("res_id")
            for vals in vals_list
            if vals.get("model") == "it.helpdesk.ticket" and vals.get("res_id")
        }

        if ticket_ids:
            tickets = (
                self.env["it.helpdesk.ticket"].sudo().browse(list(ticket_ids)).exists()
            )

            closed_ids = set(
                tickets.filtered(lambda ticket: ticket.state == "closed").ids
            )

            for vals in vals_list:
                if (
                    vals.get("model") == "it.helpdesk.ticket"
                    and vals.get("res_id") in closed_ids
                ):
                    raise UserError(
                        "종료된 문의에는 새 메시지나 " "내부 메모를 작성할 수 없습니다."
                    )

        return super().create(vals_list)
