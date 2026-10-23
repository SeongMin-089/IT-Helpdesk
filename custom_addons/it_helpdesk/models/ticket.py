import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError, AccessError, UserError


class HelpdeskTicket(models.Model):
    _name = "it.helpdesk.ticket"
    _description = "IT Helpdesk Ticket"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "create_date desc"
    # Chatter 댓글은 Ticket 조회 권한을 기준으로 작성 가능
    _mail_post_access = "read"

    _reference_unique = models.Constraint(
        "UNIQUE (reference)",
        "문의 번호는 중복될 수 없습니다.",
    )

    _dashboard_states = [
        ("received", "접수"),
        ("assigned", "배정"),
        ("in_progress", "처리 중"),
        ("reopen_requested", "재처리 요청"),
        ("reopened_in_progress", "재처리 중"),
        ("resolved", "해결"),
        ("closed", "종료"),
    ]
    _dashboard_priorities = [
        ("low", "낮음"),
        ("normal", "보통"),
        ("high", "높음"),
        ("urgent", "긴급"),
    ]

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
        domain=[("active", "=", True)],
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
            ("reopen_requested", "재처리 요청"),
            ("reopened_in_progress", "재처리 중"),
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
    # 변경 이력
    history_ids = fields.One2many(
        "it.helpdesk.history",
        "ticket_id",
        string="변경 이력",
        readonly=True,
    )

    @api.model
    def get_dashboard_data(self):
        """Return role-scoped dashboard data without bypassing record rules."""
        is_agent = self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent")
        is_employee = self.env.user.has_group("it_helpdesk.group_it_helpdesk_user")
        if not is_agent and not is_employee:
            raise AccessError("IT Helpdesk 대시보드 접근 권한이 없습니다.")

        base_domain = [("active", "=", True)]
        if not is_agent:
            base_domain.append(("requester_id", "=", self.env.uid))

        def count(extra_domain=None):
            return self.search_count(base_domain + (extra_domain or []))

        def serialize(tickets):
            return [
                {
                    "id": ticket.id,
                    "reference": ticket.reference,
                    "name": ticket.name,
                    "state": ticket.state,
                    "state_label": dict(self._dashboard_states).get(ticket.state),
                    "priority": ticket.priority,
                    "priority_label": dict(self._dashboard_priorities).get(
                        ticket.priority
                    ),
                    "create_date": fields.Datetime.to_string(ticket.create_date),
                    "requester_name": ticket.requester_id.name,
                    "assigned_user_name": ticket.assigned_user_id.name or False,
                }
                for ticket in tickets
            ]

        state_distribution = [
            {
                "key": state,
                "label": label,
                "count": count([("state", "=", state)]),
            }
            for state, label in self._dashboard_states
        ]
        recent_tickets = self.search(
            base_domain,
            order="create_date desc, id desc",
            limit=5,
        )

        if not is_agent:
            return {
                "role": "employee",
                "kpis": [
                    {
                        "key": "total",
                        "label": "내 전체 문의",
                        "count": count(),
                        "domain": [],
                    },
                    {
                        "key": "processing",
                        "label": "처리 중",
                        "count": count(
                            [
                                (
                                    "state",
                                    "in",
                                    [
                                        "assigned",
                                        "in_progress",
                                        "reopened_in_progress",
                                    ],
                                )
                            ]
                        ),
                        "domain": [
                            [
                                "state",
                                "in",
                                [
                                    "assigned",
                                    "in_progress",
                                    "reopened_in_progress",
                                ],
                            ]
                        ],
                    },
                    {
                        "key": "resolved",
                        "label": "해결 대기",
                        "count": count([("state", "=", "resolved")]),
                        "domain": [["state", "=", "resolved"]],
                    },
                    {
                        "key": "closed",
                        "label": "종료 완료",
                        "count": count([("state", "=", "closed")]),
                        "domain": [["state", "=", "closed"]],
                    },
                ],
                "state_distribution": state_distribution,
                "priority_distribution": [],
                "recent_tickets": serialize(recent_tickets),
                "urgent_tickets": [],
            }

        unresolved_states = [
            "received",
            "assigned",
            "in_progress",
            "reopen_requested",
            "reopened_in_progress",
        ]
        priority_distribution = [
            {
                "key": priority,
                "label": label,
                "count": count([("priority", "=", priority)]),
            }
            for priority, label in self._dashboard_priorities
        ]
        urgent_domain = [
            ("priority", "=", "urgent"),
            ("state", "in", unresolved_states),
        ]
        urgent_tickets = self.search(
            base_domain + urgent_domain,
            order="create_date desc, id desc",
            limit=5,
        )
        return {
            "role": "agent",
            "kpis": [
                {
                    "key": "total",
                    "label": "전체 문의",
                    "count": count(),
                    "domain": [],
                },
                {
                    "key": "unassigned",
                    "label": "미배정",
                    "count": count(
                        [
                            ("assigned_user_id", "=", False),
                            ("state", "!=", "closed"),
                        ]
                    ),
                    "domain": [
                        ["assigned_user_id", "=", False],
                        ["state", "!=", "closed"],
                    ],
                },
                {
                    "key": "processing",
                    "label": "진행 중",
                    "count": count(
                        [
                            (
                                "state",
                                "in",
                                [
                                    "assigned",
                                    "in_progress",
                                    "reopen_requested",
                                    "reopened_in_progress",
                                ],
                            )
                        ]
                    ),
                    "domain": [
                        [
                            "state",
                            "in",
                            [
                                "assigned",
                                "in_progress",
                                "reopen_requested",
                                "reopened_in_progress",
                            ],
                        ]
                    ],
                },
                {
                    "key": "urgent",
                    "label": "긴급 미해결",
                    "count": count(urgent_domain),
                    "domain": [
                        ["priority", "=", "urgent"],
                        ["state", "in", unresolved_states],
                    ],
                },
            ],
            "state_distribution": state_distribution,
            "priority_distribution": priority_distribution,
            "recent_tickets": serialize(recent_tickets),
            "urgent_tickets": serialize(urgent_tickets),
        }

    # Chatter 댓글 작성 권한 및 종료 상태 검증
    def message_post(self, **kwargs):
        self.ensure_one()
        # Odoo 19 Chatter 컨트롤러는 sudo()로 메시지를 작성하므로
        # 실제 로그인 사용자의 Ticket 조회 권한을 별도로 확인한다.
        self.sudo(False).check_access("read")
        if self.state == "closed":
            raise UserError("종료된 문의에는 댓글을 작성할 수 없습니다.")
        return super().message_post(**kwargs)

    # 입력값 검증 공통 함수
    def _validate_ticket_values(self, vals):
        checks = [
            ("name", "문의 제목", 5, 100),
            ("description", "문의 내용", 10, 5000),
            ("location", "발생 위치/부서", 2, 100),
        ]
        for field_name, label, minimum, maximum in checks:
            value = vals.get(field_name) or ""
            length = len("".join(value.split()))
            if not minimum <= length <= maximum:
                raise ValidationError(
                    f"{label}은(는) 공백을 제외하고 "
                    f"{minimum}~{maximum:,}자로 입력해야 합니다."
                )
        self._validate_contact_only(vals.get("contact"))

    @staticmethod
    def _validate_contact_only(contact):
        contact = (contact or "").strip()
        if contact:
            digits = re.sub(r"\D", "", contact)
            if not re.fullmatch(r"[0-9\s-]+", contact) or not 9 <= len(digits) <= 11:
                raise ValidationError(
                    "연락처는 숫자 9~11자리로 입력해 주세요. "
                    "하이픈(-)과 공백은 사용할 수 있습니다."
                )

    # 연락처 하이픈 자동 변환
    @staticmethod
    def _format_contact(contact):
        if not contact or not str(contact).strip():
            return False
        digits = re.sub(r"\D", "", contact)
        # 서울 지역번호
        if digits.startswith("02") and len(digits) in (9, 10):
            return f"02-{digits[2:-4]}-{digits[-4:]}"
        # 일반 10자리 또는 11자리
        if len(digits) in (10, 11):
            return f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}"
        # 9자리 번호
        if len(digits) == 9:
            return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
        return contact

    # 신규 문의 생성 권한 및 초기 상태 검증
    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        auto_assignment_user_ids = []
        if not self.env.su:
            is_agent = self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent")
            is_employee = self.env.user.has_group("it_helpdesk.group_it_helpdesk_user")
            if not is_agent and not is_employee:
                raise AccessError("IT Helpdesk 문의 등록 권한이 없습니다.")
        initial_values = {
            "state": (False, "received"),
            "assigned_user_id": (False, None),
            "resolution": (False, None, ""),
            "resolution_method": (False, None, ""),
            "resolved_date": (False, None),
            "closed_date": (False, None),
            "reopen_count": (False, None, 0),
            "reference": (False, None, "", "New"),
            "active": (True, None),
        }
        forbidden_fields = {
            "history_ids",
            "priority_order",
        }
        for vals in vals_list:
            if not self.env.su:
                if forbidden_fields.intersection(vals):
                    raise AccessError(
                        "신규 문의에서 이력이나 내부 정렬값을 " "지정할 수 없습니다."
                    )
                for field_name, allowed_values in initial_values.items():
                    if field_name in vals and vals[field_name] not in allowed_values:
                        raise AccessError(
                            "신규 문의는 접수·미배정 상태로만 " "등록할 수 있습니다."
                        )
                # 직원과 담당자 모두 본인 명의로만 문의 등록
                if vals.get("requester_id") not in (
                    None,
                    False,
                    self.env.user.id,
                ):
                    raise AccessError(
                        "본인 명의로만 문의를 등록할 수 있습니다."
                    )
                vals["requester_id"] = self.env.user.id
                vals.update(
                    {
                        "state": "received",
                        "assigned_user_id": False,
                        "active": True,
                    }
                )
            # 입력값 검증 후 연락처 정규화
            self._validate_ticket_values(vals)
            if "contact" in vals:
                vals["contact"] = self._format_contact(vals["contact"])
            # 클라이언트 입력 검증이 끝난 뒤 서버가 유형의 기본 담당자를
            # 검증하여 신규 문의에만 자동 배정을 적용한다.
            auto_agent = self.env["res.users"]
            if (
                not vals.get("assigned_user_id")
                and vals.get("state", "received") == "received"
                and vals.get("category_id")
            ):
                category = (
                    self.env["it.helpdesk.category"]
                    .sudo()
                    .browse(vals["category_id"])
                    .exists()
                )
                candidate = category.default_user_id if category else auto_agent
                if category and category._is_valid_default_user(candidate):
                    auto_agent = candidate
                    vals.update(
                        {
                            "assigned_user_id": auto_agent.id,
                            "state": "assigned",
                        }
                    )
            auto_assignment_user_ids.append(auto_agent.id)
        # 서버에서 문의 번호 자동 발급. 기존 데이터나 조정된 시퀀스와
        # 충돌하더라도 새 문의에는 이미 사용 중인 번호를 부여하지 않는다.
        for vals in vals_list:
            for _attempt in range(100):
                reference = self.env["ir.sequence"].next_by_code(
                    "it.helpdesk.ticket"
                )
                if reference and not self.sudo().with_context(
                    active_test=False
                ).search_count(
                    [("reference", "=", reference)],
                    limit=1,
                ):
                    vals["reference"] = reference
                    break
            else:
                raise ValidationError(
                    "고유한 문의 번호를 발급할 수 없습니다. "
                    "문의 번호 시퀀스를 확인해 주세요."
                )
        tickets = super().create(vals_list)
        history_values = [
            {
                "ticket_id": ticket.id,
                "change_type": "assignment",
                "old_value": "미배정",
                "new_value": ticket.assigned_user_id.name,
                "changed_by": self.env.user.id,
                "description": "문의 유형에 따른 담당자 자동 배정",
            }
            for ticket, user_id in zip(tickets, auto_assignment_user_ids)
            if user_id
        ]
        if history_values:
            # 일반 직원은 History 생성 ACL이 없으므로 서버 업무로 기록한다.
            # Ticket 생성과 같은 트랜잭션이어서 기록 실패 시 함께 롤백된다.
            self.env["it.helpdesk.history"].sudo().create(history_values)
        return tickets

    @api.constrains("reference")
    def _check_reference_unique(self):
        for ticket in self.filtered(lambda record: record.reference):
            # ORM search_count() flushes the pending duplicate write before
            # this Python validation can return its friendly error. Query the
            # stored rows directly and leave the DB constraint as the final
            # concurrency guard.
            self.env.cr.execute(
                """
                SELECT 1
                  FROM it_helpdesk_ticket
                 WHERE reference = %s
                   AND id != %s
                 LIMIT 1
                """,
                [ticket.reference, ticket.id],
            )
            if self.env.cr.fetchone():
                raise ValidationError("문의 번호는 중복될 수 없습니다.")

    # 문의 등록 및 수정 시 입력값 검증
    @api.constrains(
        "category_id",
        "name",
        "description",
        "location",
        "contact",
    )
    def _check_ticket_input(self):
        for ticket in self:
            if not ticket.category_id.active:
                raise ValidationError("활성화된 문의 유형만 선택할 수 있습니다.")
            self._validate_ticket_values(
                {
                    "name": ticket.name,
                    "description": ticket.description,
                    "location": ticket.location,
                    "contact": ticket.contact,
                }
            )

    # 승인된 업무 기능에서만 내부 처리 필드 수정
    def _write_workflow(self, vals):
        return super(HelpdeskTicket, self).write(vals)

    # 일반 문의 수정 권한 검증
    def write(self, vals):
        priority_before = {}
        if not self.env.su:
            is_agent = self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent")
            is_employee = self.env.user.has_group("it_helpdesk.group_it_helpdesk_user")
            if not is_agent and not is_employee:
                raise AccessError("IT Helpdesk 문의 수정 권한이 없습니다.")
            # 내부 업무 필드는 일반 write()로 수정 불가
            workflow_fields = {
                "state",
                "assigned_user_id",
                "requester_id",
                "reference",
                "resolution",
                "resolution_method",
                "resolved_date",
                "closed_date",
                "reopen_count",
                "history_ids",
                "priority_order",
            }
            if workflow_fields.intersection(vals):
                raise AccessError(
                    "상태, 담당자, 해결 정보 등은 "
                    "전용 업무 기능에서만 변경할 수 있습니다."
                )
            for ticket in self:
                if is_agent:
                    # IT 담당자는 긴급도 및 보관/복원만 일반 수정 가능
                    allowed_fields = {"priority", "active"}
                    if set(vals) - allowed_fields:
                        raise AccessError(
                            "IT 담당자는 긴급도와 보관/복원만 수정할 수 있습니다."
                        )
                    # 종료 문의는 보관/복원만 허용
                    if ticket.state == "closed":
                        if set(vals) - {"active"}:
                            raise UserError("종료된 문의는 보관/복원만 가능합니다.")
                    # 우선순위 변경 전 값을 보관
                    if "priority" in vals and ticket.priority != vals["priority"]:
                        priority_before[ticket.id] = ticket.priority
                else:
                    # 일반 직원은 자신의 문의만 수정
                    if ticket.requester_id != self.env.user:
                        raise AccessError("본인이 등록한 문의만 수정할 수 있습니다.")
                    if ticket.state != "received" or ticket.assigned_user_id:
                        raise UserError(
                            "접수 상태이고 담당자가 배정되지 않은 "
                            "문의만 수정하거나 보관할 수 있습니다."
                        )
                    allowed_fields = {
                        "name",
                        "description",
                        "category_id",
                        "location",
                        "contact",
                        "active",
                    }
                    if set(vals) - allowed_fields:
                        raise AccessError(
                            "수정 권한이 없는 문의 항목이 " "포함되어 있습니다."
                        )
                    if "active" in vals and vals["active"] is not False:
                        raise AccessError(
                            "일반 직원은 보관된 문의를 " "복원할 수 없습니다."
                        )
        # 연락처 검증 및 자동 포맷팅
        if "contact" in vals:
            self._validate_contact_only(vals["contact"])
            vals = dict(
                vals,
                contact=self._format_contact(vals["contact"]),
            )
        result = super().write(vals)
        # 긴급도 변경 시 History 자동 기록
        if priority_before:
            priority_names = dict(self._fields["priority"].selection)
            history_values = []
            for ticket in self:
                if ticket.id in priority_before:
                    old_priority = priority_before[ticket.id]
                    history_values.append(
                        {
                            "ticket_id": ticket.id,
                            "change_type": "priority",
                            "old_value": priority_names.get(old_priority, old_priority),
                            "new_value": priority_names.get(
                                ticket.priority, ticket.priority
                            ),
                            "changed_by": self.env.user.id,
                            "description": ("IT 담당자가 문의 긴급도를 변경했습니다."),
                        }
                    )
            self.env["it.helpdesk.history"].create(history_values)
        return result

    # 문의 실제 삭제 금지
    def unlink(self):
        raise UserError(
            "문의는 실제 삭제할 수 없습니다. " "삭제 대신 보관 기능을 사용해 주세요."
        )

    # IT 담당자 수동 배정 및 재배정
    def action_assign_to(self, user_id):
        self.ensure_one()
        if not self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent"):
            raise AccessError("IT 담당자만 문의 담당자를 배정할 수 있습니다.")
        if self.state == "closed":
            raise UserError("종료된 문의는 담당자를 변경할 수 없습니다.")
        new_agent = self.env["res.users"].browse(user_id).exists()
        if not new_agent or not new_agent.active or new_agent.share:
            raise ValidationError("유효한 담당자를 선택해 주세요.")
        if not new_agent.has_group("it_helpdesk.group_it_helpdesk_agent"):
            raise ValidationError(
                "IT 담당자 권한이 있는 사용자만 " "배정할 수 있습니다."
            )
        old_agent = self.assigned_user_id
        if old_agent == new_agent:
            raise UserError("이미 해당 담당자에게 배정된 문의입니다.")
        # 최초 배정이면 접수 → 배정
        values = {
            "assigned_user_id": new_agent.id,
        }
        if self.state == "received":
            values["state"] = "assigned"
        self._write_workflow(values)
        # 담당자 변경 이력
        self.env["it.helpdesk.history"].create(
            {
                "ticket_id": self.id,
                "change_type": "assignment",
                "old_value": (old_agent.name if old_agent else "미배정"),
                "new_value": new_agent.name,
                "description": (
                    f"담당자 배정: "
                    f"{old_agent.name if old_agent else '미배정'}"
                    f" → {new_agent.name}"
                ),
            }
        )
        # 최초 배정 시 상태 변경 이력
        if "state" in values:
            self.env["it.helpdesk.history"].create(
                {
                    "ticket_id": self.id,
                    "change_type": "state",
                    "old_value": "접수",
                    "new_value": "배정",
                    "description": ("최초 담당자 배정으로 " "상태가 변경되었습니다."),
                }
            )
        return True

    # 배정된 문의 처리 시작
    def action_start_progress(self):
        self.ensure_one()
        if not self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent"):
            raise AccessError("IT 담당자만 문의 처리를 시작할 수 있습니다.")
        if self.state != "assigned":
            raise UserError("배정 상태의 문의만 처리를 시작할 수 있습니다.")
        if not self.assigned_user_id:
            raise UserError("담당자를 먼저 배정해 주세요.")
        self._write_workflow(
            {
                "state": "in_progress",
            }
        )
        self.env["it.helpdesk.history"].create(
            {
                "ticket_id": self.id,
                "change_type": "state",
                "old_value": "배정",
                "new_value": "처리 중",
                "description": ("IT 담당자가 문의 처리를 시작했습니다."),
            }
        )
        return True

    # 담당자의 재처리 시작
    def action_start_reopen(self):
        self.ensure_one()
        if not self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent"):
            raise AccessError("IT 담당자만 재처리를 시작할 수 있습니다.")
        if self.state != "reopen_requested":
            raise UserError("재처리 요청 상태의 문의만 " "재처리를 시작할 수 있습니다.")
        if not self.assigned_user_id:
            raise UserError("담당자를 먼저 배정해 주세요.")
        self._write_workflow(
            {
                "state": "reopened_in_progress",
            }
        )
        self.env["it.helpdesk.history"].create(
            {
                "ticket_id": self.id,
                "change_type": "state",
                "old_value": "재처리 요청",
                "new_value": "재처리 중",
                "description": ("IT 담당자가 재처리를 시작했습니다."),
            }
        )
        return True

    # 요청자 재처리 요청
    def action_request_reopen(self, reason):
        self.ensure_one()
        if self.requester_id != self.env.user:
            raise AccessError(
                "문의를 등록한 요청자 본인만 " "재처리를 요청할 수 있습니다."
            )
        if not self.active:
            raise UserError("보관된 문의는 재처리를 요청할 수 없습니다.")
        if self.state != "resolved":
            raise UserError("해결 상태의 문의만 재처리를 요청할 수 있습니다.")
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("재처리 사유를 입력해 주세요.")
        # 이전 해결 정보 보존
        previous_resolution = self.resolution or ""
        previous_method = self.resolution_method or ""
        previous_resolved_date = self.resolved_date
        method_names = {
            "onsite": "현장 방문",
            "remote": "원격/안내",
        }
        previous_method_name = method_names.get(previous_method, "미기록")
        previous_date_text = (
            fields.Datetime.to_string(previous_resolved_date)
            if previous_resolved_date
            else "미기록"
        )
        # 재처리 요청 상태로 변경
        self._write_workflow(
            {
                "state": "reopen_requested",
                "resolution": False,
                "resolution_method": False,
                "resolved_date": False,
                "reopen_count": self.reopen_count + 1,
            }
        )
        # 이전 해결 정보 및 상태 변경 History 기록
        self.env["it.helpdesk.history"].sudo().create(
            [
                {
                    "ticket_id": self.id,
                    "change_type": "reopen",
                    "old_value": previous_method_name,
                    "new_value": "재처리 요청",
                    "description": (
                        f"재처리 사유: {reason}\n\n"
                        f"[이전 해결 정보]\n"
                        f"해결 방식: {previous_method_name}\n"
                        f"해결 일시(서버 기준): "
                        f"{previous_date_text}\n"
                        f"해결 내용:\n{previous_resolution}"
                    ),
                    "changed_by": self.env.user.id,
                },
                {
                    "ticket_id": self.id,
                    "change_type": "state",
                    "old_value": "해결",
                    "new_value": "재처리 요청",
                    "description": (
                        "요청자가 재처리를 요청하여 "
                        "상태가 재처리 요청으로 변경되었습니다."
                    ),
                    "changed_by": self.env.user.id,
                },
            ]
        )
        return True

    # 요청자 문의 종료 승인
    def action_close_ticket(self):
        self.ensure_one()
        if self.requester_id != self.env.user:
            raise AccessError(
                "문의를 등록한 요청자 본인만 " "종료를 승인할 수 있습니다."
            )
        if not self.active:
            raise UserError("보관된 문의는 종료를 승인할 수 없습니다.")
        if self.state != "resolved":
            raise UserError("해결 상태의 문의만 종료할 수 있습니다.")
        self._write_workflow(
            {
                "state": "closed",
                "closed_date": fields.Datetime.now(),
            }
        )
        self.env["it.helpdesk.history"].sudo().create(
            {
                "ticket_id": self.id,
                "change_type": "state",
                "old_value": "해결",
                "new_value": "종료",
                "changed_by": self.env.user.id,
                "description": (
                    "요청자가 해결 결과를 확인하고 " "문의 종료를 승인했습니다."
                ),
            }
        )
        return True
