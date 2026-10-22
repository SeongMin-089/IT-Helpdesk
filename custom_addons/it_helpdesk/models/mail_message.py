from odoo import api, models
from odoo.exceptions import AccessError, UserError


class HelpdeskMailMessage(models.Model):
    _inherit = "mail.message"

    @api.model
    def _helpdesk_attachment_ids(self, commands):
        attachment_ids = set()
        for command in commands or []:
            if isinstance(command, int):
                attachment_ids.add(command)
            elif command[0] == 4:
                attachment_ids.add(command[1])
            elif command[0] == 6:
                attachment_ids.update(command[2])
            elif command[0] == 0:
                raise AccessError(
                    "문의 메시지의 첨부파일은 먼저 안전하게 업로드해야 합니다."
                )
        return attachment_ids

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

            tickets_by_id = {ticket.id: ticket for ticket in tickets}
            for vals in vals_list:
                if vals.get("model") != "it.helpdesk.ticket" or not vals.get("res_id"):
                    continue
                ticket = tickets_by_id.get(vals["res_id"])
                self.env["ir.attachment"]._helpdesk_check_ticket_access(ticket)
                attachment_ids = self._helpdesk_attachment_ids(
                    vals.get("attachment_ids")
                )
                if not attachment_ids:
                    continue
                attachments = self.env["ir.attachment"].sudo().browse(
                    attachment_ids
                ).exists()
                if len(attachments) != len(attachment_ids) or any(
                    attachment.res_model != "it.helpdesk.ticket"
                    or attachment.res_id != ticket.id
                    for attachment in attachments
                ):
                    raise AccessError(
                        "문의에 안전하게 연결된 첨부파일만 메시지에 추가할 수 있습니다."
                    )
                attachments._validate_helpdesk_records()

        return super().create(vals_list)
