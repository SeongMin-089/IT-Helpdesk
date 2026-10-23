from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HelpdeskCategory(models.Model):
    _name = "it.helpdesk.category"
    _description = "IT Helpdesk Category"
    _order = "name"

    _code_unique = models.Constraint(
        "UNIQUE (code)",
        "문의 유형 코드는 중복될 수 없습니다.",
    )

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
                    lambda user: user.has_group(
                        "it_helpdesk.group_it_helpdesk_agent"
                    )
                )
                .ids,
            )
        ],
    )

    active = fields.Boolean(
        string="활성",
        default=True,
    )

    @api.model
    def _is_valid_default_user(self, user):
        user = user.exists()
        return bool(
            user
            and user.active
            and not user.share
            and user.has_group("it_helpdesk.group_it_helpdesk_agent")
        )

    @api.model
    def _validate_default_user_id(self, user_id):
        if not user_id:
            return
        user = self.env["res.users"].sudo().browse(user_id)
        if not self._is_valid_default_user(user):
            raise ValidationError(
                "활성 상태인 내부 IT 담당자만 기본 담당자로 설정할 수 있습니다."
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "default_user_id" in vals:
                self._validate_default_user_id(vals["default_user_id"])
        return super().create(vals_list)

    def write(self, vals):
        # 기존 설정이 나중에 무효화되더라도 다른 필드 수정은 허용한다.
        # 기본 담당자를 새로 지정하거나 변경할 때만 현재 유효성을 검사한다.
        if "default_user_id" in vals:
            self._validate_default_user_id(vals["default_user_id"])
        return super().write(vals)
