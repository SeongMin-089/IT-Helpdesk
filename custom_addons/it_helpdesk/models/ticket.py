from odoo import models, fields, api


class HelpdeskTicket(models.Model):
    _name = "it.helpdesk.ticket"
    _description = "IT Helpdesk Ticket"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "create_date desc"

    # 문의 기본 정보
    reference = fields.Char(
        string="문의 번호",
        readonly=True,
        copy=False,
        default="New",
    )

    name = fields.Char(
        string="문의 제목",
        required=True,
    )

    description = fields.Text(
        string="문의 내용",
        required=True,
    )

    requester_id = fields.Many2one(
        "res.users",
        string="요청자",
        required=True,
        default=lambda self: self.env.user,
    )

    assigned_user_id = fields.Many2one(
        "res.users",
        string="담당자",
    )

    category_id = fields.Many2one(
        "it.helpdesk.category",
        string="문의 유형",
        required=True,
    )

    # 긴급도
    priority = fields.Selection(
        [
            ("low", "낮음"),
            ("normal", "보통"),
            ("high", "높음"),
            ("urgent", "긴급"),
        ],
        string="긴급도",
        required=True,
        default="normal",
    )

    priority_order = fields.Integer(
        string="긴급도 정렬값",
        compute="_compute_priority_order",
        store=True,
    )

    @api.depends("priority")
    def _compute_priority_order(self):
        order_map = {
            "low": 1,
            "normal": 2,
            "high": 3,
            "urgent": 4,
        }
        for ticket in self:
            ticket.priority_order = order_map.get(ticket.priority, 2)

    # 문의 처리 상태
    state = fields.Selection(
        [
            ("received", "접수"),
            ("assigned", "배정"),
            ("in_progress", "처리 중"),
            ("resolved", "해결"),
            ("closed", "종료"),
        ],
        string="처리 상태",
        required=True,
        default="received",
    )

    # 추가 정보
    contact = fields.Char(string="연락처")

    location = fields.Char(
        string="발생 위치/부서",
        required=True,
    )

    # 해결 정보
    resolution = fields.Text(string="해결 내용")

    resolution_method = fields.Selection(
        [
            ("onsite", "현장 방문"),
            ("remote", "원격/안내"),
        ],
        string="해결 방식",
    )

    resolved_date = fields.Datetime(string="해결 일시")
    closed_date = fields.Datetime(string="종료 일시")

    reopen_count = fields.Integer(
        string="재처리 횟수",
        default=0,
        readonly=True,
    )

    # 아카이브
    active = fields.Boolean(
        string="활성",
        default=True,
    )

    # 변경 이력 (History)
    history_ids = fields.One2many(
        "it.helpdesk.history",
        "ticket_id",
        string="변경 이력",
        readonly=True,
    )
