from odoo import models, fields


class HelpdeskCategory(models.Model):
    _name = "it.helpdesk.category"
    _description = "IT Helpdesk Category"
    _order = "name"

    name = fields.Char(
        string="유형명",
        required=True,
    )

    code = fields.Char(
        string="유형 코드",
        required=True,
    )

    description = fields.Text(
        string="설명",
    )

    default_user_id = fields.Many2one(
        "res.users",
        string="기본 담당자",
    )

    active = fields.Boolean(
        string="활성",
        default=True,
    )
