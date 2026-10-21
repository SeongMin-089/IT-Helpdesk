from odoo import models, fields
from odoo.exceptions import AccessError, ValidationError


class HelpdeskAssignmentWizard(models.TransientModel):
    _name = "it.helpdesk.assignment.wizard"
    _description = "IT Helpdesk 담당자 배정"

    ticket_id = fields.Many2one(
        "it.helpdesk.ticket",
        string="문의",
        required=True,
        readonly=True,
    )

    assigned_user_id = fields.Many2one(
        "res.users",
        string="배정할 담당자",
        required=True,
        domain=lambda self: [
            (
                "id",
                "in",
                self.env["res.users"]
                .sudo()
                .search(
                    [
                        ("active", "=", True),
                        ("share", "=", False),
                    ]
                )
                .filtered(
                    lambda user: user.has_group("it_helpdesk.group_it_helpdesk_agent")
                )
                .ids,
            )
        ],
    )

    def action_confirm(self):
        self.ensure_one()

        if not self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent"):
            raise AccessError("IT 담당자만 문의 담당자를 배정할 수 있습니다.")

        if not self.ticket_id:
            raise ValidationError("배정할 문의를 찾을 수 없습니다.")

        self.ticket_id.action_assign_to(self.assigned_user_id.id)

        return {"type": "ir.actions.act_window_close"}
