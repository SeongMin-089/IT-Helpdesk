from odoo import models, fields


class HelpdeskHistory(models.Model):
    _name = "it.helpdesk.history"
    _description = "IT Helpdesk Change History"
    _order = "change_date desc, id desc"

    ticket_id = fields.Many2one(
        "it.helpdesk.ticket",
        string="문의",
        required=True,
        ondelete="cascade",
    )

    change_type = fields.Selection(
        [
            ("state", "상태 변경"),
            ("assignment", "담당자 변경"),
            ("priority", "긴급도 변경"),
            ("reopen", "재처리 요청"),
            ("resolution", "해결 조치"),
        ],
        string="변경 유형",
        required=True,
    )

    old_value = fields.Char(string="변경 전 값")
    new_value = fields.Char(string="변경 후 값")

    changed_by = fields.Many2one(
        "res.users",
        string="변경자",
        required=True,
        default=lambda self: self.env.user,
    )

    change_date = fields.Datetime(
        string="변경 일시",
        required=True,
        default=fields.Datetime.now,
    )

    description = fields.Text(string="변경 내용 및 사유")
