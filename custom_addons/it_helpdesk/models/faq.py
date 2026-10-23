import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class HelpdeskFaq(models.Model):
    _name = "it.helpdesk.faq"
    _description = "IT Helpdesk FAQ"
    _order = "write_date desc, id desc"

    name = fields.Char(
        string="FAQ 제목",
        required=True,
    )
    answer = fields.Text(
        string="해결 방법",
        required=True,
    )
    category_id = fields.Many2one(
        "it.helpdesk.category",
        string="문의 유형",
        ondelete="set null",
    )
    keywords = fields.Char(
        string="검색 키워드",
        help="쉼표 또는 공백으로 검색 동의어와 핵심 단어를 입력합니다.",
    )
    is_published = fields.Boolean(
        string="공개",
        default=False,
    )
    active = fields.Boolean(
        string="활성",
        default=True,
    )
    source_ticket_id = fields.Many2one(
        "it.helpdesk.ticket",
        string="원본 문의",
        ondelete="set null",
        groups="it_helpdesk.group_it_helpdesk_agent",
    )
    author_id = fields.Many2one(
        "res.users",
        string="작성자",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
        groups="it_helpdesk.group_it_helpdesk_agent",
    )

    @api.constrains("name", "answer")
    def _check_required_text(self):
        for faq in self:
            if not (faq.name or "").strip():
                raise ValidationError("FAQ 제목을 입력해 주세요.")
            if not (faq.answer or "").strip():
                raise ValidationError("해결 방법을 입력해 주세요.")

    def _check_agent(self):
        if not self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent"):
            raise AccessError("IT 담당자만 FAQ를 관리할 수 있습니다.")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            self._check_agent()
        prepared_values = []
        for values in vals_list:
            values = dict(values)
            if not self.env.su:
                if values.get("is_published"):
                    raise UserError(
                        "신규 FAQ는 초안으로 저장한 뒤 별도로 공개해 주세요."
                    )
                values.update(
                    {
                        "author_id": self.env.user.id,
                        "is_published": False,
                        "active": True,
                    }
                )
            prepared_values.append(values)
        return super().create(prepared_values)

    def write(self, values):
        if not self.env.su:
            self._check_agent()
            if "author_id" in values:
                raise AccessError("FAQ 작성자는 변경할 수 없습니다.")
        return super().write(values)

    def unlink(self):
        raise UserError(
            "FAQ는 실제 삭제할 수 없습니다. 삭제 대신 보관 기능을 사용해 주세요."
        )

    def action_publish(self):
        self._check_agent()
        if any(not faq.active for faq in self):
            raise UserError("보관된 FAQ는 복원한 후 공개할 수 있습니다.")
        self.write({"is_published": True})
        return True

    def action_unpublish(self):
        self._check_agent()
        self.write({"is_published": False})
        return True

    def action_archive(self):
        self._check_agent()
        self.write({"active": False})
        return True

    def action_restore(self):
        self._check_agent()
        self.write({"active": True})
        return True

    @api.model
    def get_dashboard_data(self):
        """Return only the FAQ dashboard payload allowed for the current role."""
        is_agent = self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent")
        is_employee = self.env.user.has_group("it_helpdesk.group_it_helpdesk_user")
        if not is_agent and not is_employee:
            raise AccessError("FAQ 대시보드 정보를 조회할 권한이 없습니다.")

        if not is_agent:
            recent_faqs = self.search(
                [
                    ("active", "=", True),
                    ("is_published", "=", True),
                ],
                order="write_date desc, id desc",
                limit=3,
            )
            return {
                "recent_faqs": [
                    {
                        "id": faq.id,
                        "name": faq.name,
                        "category_name": faq.category_id.name or "전체",
                    }
                    for faq in recent_faqs
                ]
            }

        all_faqs = self.with_context(active_test=False)
        total_count = all_faqs.search_count([])
        published_count = self.search_count(
            [("active", "=", True), ("is_published", "=", True)]
        )
        private_count = self.search_count(
            [("active", "=", True), ("is_published", "=", False)]
        )
        archived_count = all_faqs.search_count([("active", "=", False)])
        return {
            "faq_kpis": [
                {
                    "key": "total",
                    "label": "전체 FAQ",
                    "count": total_count,
                    "domain": [],
                    "context": {"active_test": False},
                },
                {
                    "key": "published",
                    "label": "공개 FAQ",
                    "count": published_count,
                    "domain": [
                        ["active", "=", True],
                        ["is_published", "=", True],
                    ],
                    "context": {"active_test": True},
                },
                {
                    "key": "private",
                    "label": "비공개 FAQ",
                    "count": private_count,
                    "domain": [
                        ["active", "=", True],
                        ["is_published", "=", False],
                    ],
                    "context": {"active_test": True},
                },
                {
                    "key": "archived",
                    "label": "보관 FAQ",
                    "count": archived_count,
                    "domain": [["active", "=", False]],
                    "context": {"active_test": False},
                },
            ]
        }

    @staticmethod
    def _normalize_search_text(value):
        value = (value or "").strip().lower()[:100]
        return re.sub(r"(?<=\w)[-_](?=\w)", "", value)

    @classmethod
    def _search_fragments(cls, query):
        normalized = cls._normalize_search_text(query)
        words = re.findall(r"[0-9a-z가-힣]+", normalized)
        fragments = []
        for word in words:
            if len(word) < 2:
                continue
            fragments.append(word)
            if len(word) >= 3:
                fragments.append(word[:2])
            if len(word) >= 4:
                fragments.append(word[:3])
        return normalized, list(dict.fromkeys(fragments))[:12]

    @api.model
    def search_recommendations(self, query, category_id=False):
        is_agent = self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent")
        is_employee = self.env.user.has_group("it_helpdesk.group_it_helpdesk_user")
        if not is_agent and not is_employee:
            raise AccessError("FAQ 추천을 조회할 권한이 없습니다.")

        normalized_query, fragments = self._search_fragments(query)
        if len(normalized_query) < 2 or not fragments:
            return []
        try:
            category_id = int(category_id or 0)
        except (TypeError, ValueError):
            category_id = 0

        match_domains = []
        for fragment in fragments:
            match_domains.extend(
                [
                    [("name", "ilike", fragment)],
                    [("keywords", "ilike", fragment)],
                    [("category_id.name", "ilike", fragment)],
                ]
            )
        if category_id:
            match_domains.append([("category_id", "=", category_id)])

        domain = fields.Domain.AND(
            [
                fields.Domain(
                    [
                        ("active", "=", True),
                        ("is_published", "=", True),
                    ]
                ),
                fields.Domain.OR(match_domains),
            ]
        )
        candidates = self.search(domain, limit=60)

        def score(faq):
            title = self._normalize_search_text(faq.name)
            keywords = self._normalize_search_text(faq.keywords)
            category = self._normalize_search_text(faq.category_id.name)
            value = 0
            if title == normalized_query:
                value += 100
            elif normalized_query in title:
                value += 60
            for fragment in fragments:
                if fragment in title:
                    value += 20
                if fragment in keywords:
                    value += 12
                if fragment in category:
                    value += 5
            if category_id and faq.category_id.id == category_id:
                value += 10
            return value

        ranked = sorted(
            candidates,
            key=lambda faq: (score(faq), faq.write_date, faq.id),
            reverse=True,
        )[:3]
        return [
            {
                "id": faq.id,
                "name": faq.name,
                "category_name": faq.category_id.name or "전체",
                "answer_preview": " ".join(faq.answer.split())[:160],
            }
            for faq in ranked
        ]

    @api.model
    def open_public_faq(self, faq_id):
        is_agent = self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent")
        is_employee = self.env.user.has_group("it_helpdesk.group_it_helpdesk_user")
        if not is_agent and not is_employee:
            raise AccessError("FAQ를 조회할 권한이 없습니다.")
        faq = self.browse(faq_id).exists()
        if not faq or not faq.active or not faq.is_published:
            raise AccessError("공개된 FAQ만 조회할 수 있습니다.")
        faq.check_access("read")
        return {
            "type": "ir.actions.act_window",
            "name": faq.name,
            "res_model": self._name,
            "res_id": faq.id,
            "views": [
                (
                    self.env.ref(
                        "it_helpdesk.view_it_helpdesk_faq_public_form"
                    ).id,
                    "form",
                )
            ],
            "target": "new",
        }
