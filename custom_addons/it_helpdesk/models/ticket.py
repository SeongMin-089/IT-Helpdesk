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
                # 일반 직원은 본인 명의로만 문의 등록
                if not is_agent and vals.get("requester_id") not in (
                    None,
                    False,
                    self.env.user.id,
                ):
                    raise AccessError(
                        "일반 직원은 본인 명의로만 " "문의를 등록할 수 있습니다."
                    )
                if not is_agent:
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
        # 서버에서 문의 번호 자동 발급
        for vals in vals_list:
            vals["reference"] = (
                self.env["ir.sequence"].next_by_code("it.helpdesk.ticket") or "New"
            )
        return super().create(vals_list)

    # 문의 등록 및 수정 시 입력값 검증
    @api.constrains(
        "name",
        "description",
        "location",
        "contact",
    )
    def _check_ticket_input(self):
        for ticket in self:
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
        if not new_agent or not new_agent.active:
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
