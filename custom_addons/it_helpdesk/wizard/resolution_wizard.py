from odoo import models, fields
from odoo.exceptions import AccessError, UserError, ValidationError


class HelpdeskResolutionWizard(models.TransientModel):
    _name = "it.helpdesk.resolution.wizard"
    _description = "IT Helpdesk 해결 처리"

    ticket_id = fields.Many2one(
        "it.helpdesk.ticket",
        string="문의",
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

    def action_confirm(self):
        self.ensure_one()

        if not self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent"):
            raise AccessError("IT 담당자만 해결 처리할 수 있습니다.")

        ticket = self.ticket_id

        if not ticket or ticket.state not in (
            "in_progress",
            "reopened_in_progress",
        ):
            raise UserError("처리 중 또는 재처리 중 상태의 문의만 해결할 수 있습니다.")

        if not self.resolution_method or not (self.resolution or "").strip():
            raise ValidationError("해결 방식과 해결 내용을 모두 입력해 주세요.")

        previous_state = ticket.state
        state_names = {
            "in_progress": "처리 중",
            "reopened_in_progress": "재처리 중",
        }

        # 전용 업무 메서드로 처리하여 일반 write()의 상태 변경 차단 유지
        ticket._write_workflow({
            "state": "resolved",
            "resolution_method": self.resolution_method,
            "resolution": self.resolution.strip(),
            "resolved_date": fields.Datetime.now(),
        })

        self.env["it.helpdesk.history"].create({
            "ticket_id": ticket.id,
            "change_type": "resolution",
            "old_value": "",
            "new_value": dict(self._fields["resolution_method"].selection)[
                self.resolution_method
            ],
            "description": self.resolution.strip(),
        })

        self.env["it.helpdesk.history"].create({
            "ticket_id": ticket.id,
            "change_type": "state",
            "old_value": state_names[previous_state],
            "new_value": "해결",
            "description": "IT 담당자가 문의 해결 처리를 완료했습니다.",
        })

        return {"type": "ir.actions.act_window_close"}
