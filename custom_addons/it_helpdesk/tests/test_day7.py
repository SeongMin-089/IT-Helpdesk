import ast

from lxml import etree

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "it_helpdesk_day7")
class TestHelpdeskDay7(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = new_test_user(
            cls.env,
            login="helpdesk_day7_requester",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.other_requester = new_test_user(
            cls.env,
            login="helpdesk_day7_other",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.agent = new_test_user(
            cls.env,
            login="helpdesk_day7_agent",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.other_agent = new_test_user(
            cls.env,
            login="helpdesk_day7_other_agent",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.outsider = new_test_user(
            cls.env,
            login="helpdesk_day7_outsider",
            groups="base.group_user",
        )
        cls.category = (
            cls.env["it.helpdesk.category"]
            .with_user(cls.agent)
            .create(
                {
                    "name": "Day 7 네트워크",
                    "code": "DAY7_NETWORK",
                }
            )
        )

    def _faq_values(self, suffix="기본"):
        return {
            "name": f"Day 7 FAQ {suffix}",
            "answer": "설정 화면에서 연결 상태를 확인하고 다시 연결합니다.",
            "category_id": self.category.id,
            "keywords": "와이파이 wifi 연결 네트워크",
        }

    def _create_faq(self, suffix="기본", publish=False):
        faq = (
            self.env["it.helpdesk.faq"]
            .with_user(self.agent)
            .create(self._faq_values(suffix))
        )
        if publish:
            faq.with_user(self.agent).action_publish()
        return faq

    def _ticket_values(self, suffix="기본", category=None):
        return {
            "name": f"Day 7 문의 {suffix}",
            "description": "개인 계정과 내부 장비 정보가 포함될 수 있는 문의 내용입니다.",
            "category_id": (category or self.category).id,
            "priority": "normal",
            "location": "비공개 부서 위치",
            "contact": "010-1234-5678",
        }

    def _create_ticket(self, suffix="기본", category=None):
        return (
            self.env["it.helpdesk.ticket"]
            .with_user(self.requester)
            .create(self._ticket_values(suffix, category))
        )

    def _set_resolved(self, ticket, state="resolved"):
        ticket.sudo()._write_workflow(
            {
                "state": state,
                "resolution": "네트워크 설정을 초기화하고 안전하게 재연결합니다.",
                "resolution_method": "remote",
                "resolved_date": fields.Datetime.now(),
                "closed_date": fields.Datetime.now() if state == "closed" else False,
            }
        )

    def test_agent_faq_lifecycle_and_required_values(self):
        faq = self._create_faq("생명주기")
        self.assertFalse(faq.is_published)
        self.assertTrue(faq.active)
        self.assertEqual(faq.author_id, self.agent)

        faq.with_user(self.agent).write(
            {
                "answer": "수정된 해결 절차입니다.",
                "keywords": "수정 키워드",
            }
        )
        self.assertEqual(faq.answer, "수정된 해결 절차입니다.")
        faq.with_user(self.agent).action_publish()
        self.assertTrue(faq.is_published)
        faq.with_user(self.agent).action_unpublish()
        self.assertFalse(faq.is_published)
        faq.with_user(self.agent).action_archive()
        self.assertFalse(faq.active)
        faq.with_context(active_test=False).with_user(self.agent).action_restore()
        self.assertTrue(faq.active)

        invalid_values = self._faq_values("공백 차단")
        invalid_values["answer"] = "   "
        with self.assertRaises(ValidationError):
            self.env["it.helpdesk.faq"].with_user(self.agent).create(
                invalid_values
            )
        published_values = self._faq_values("자동 공개 차단")
        published_values["is_published"] = True
        with self.assertRaises(UserError):
            self.env["it.helpdesk.faq"].with_user(self.agent).create(
                published_values
            )
        with self.assertRaises(UserError):
            faq.with_user(self.agent).unlink()

    def test_employee_can_only_read_active_published_faq(self):
        public_faq = self._create_faq("공개", publish=True)
        private_faq = self._create_faq("비공개")
        archived_faq = self._create_faq("보관", publish=True)
        archived_faq.with_user(self.agent).action_archive()

        visible = self.env["it.helpdesk.faq"].with_user(self.requester).search([])
        self.assertIn(public_faq, visible)
        self.assertNotIn(private_faq, visible)
        self.assertNotIn(archived_faq, visible)
        self.assertEqual(
            public_faq.with_user(self.requester).read(["name"])[0]["name"],
            public_faq.name,
        )
        with self.assertRaises(AccessError):
            private_faq.with_user(self.requester).read(["name"])
        with self.assertRaises(AccessError):
            archived_faq.with_context(active_test=False).with_user(
                self.requester
            ).read(["name"])
        with self.assertRaises(AccessError):
            public_faq.with_user(self.requester).read(["source_ticket_id"])

        with self.assertRaises(AccessError):
            self.env["it.helpdesk.faq"].with_user(self.requester).create(
                self._faq_values("직원 생성")
            )
        with self.assertRaises(AccessError):
            public_faq.with_user(self.requester).write({"answer": "변조"})
        with self.assertRaises(AccessError):
            public_faq.with_user(self.requester).action_unpublish()
        with self.assertRaises(UserError):
            public_faq.with_user(self.requester).unlink()

        self.assertEqual(
            private_faq.with_user(self.agent).read(["name"])[0]["name"],
            private_faq.name,
        )

    def test_resolved_ticket_creates_private_sanitized_draft(self):
        ticket = self._create_ticket("해결 초안")
        ticket.with_user(self.requester).message_post(body="비공개 댓글")
        self._set_resolved(ticket)
        original_values = ticket.read(
            ["state", "resolution", "resolved_date", "contact", "location"]
        )[0]
        original_history_count = len(ticket.history_ids)

        action = ticket.with_user(self.agent).action_create_faq_draft()
        faq = self.env["it.helpdesk.faq"].browse(action["res_id"])

        self.assertEqual(faq.name, ticket.name)
        self.assertEqual(faq.answer, ticket.resolution)
        self.assertEqual(faq.category_id, ticket.category_id)
        self.assertEqual(faq.source_ticket_id, ticket)
        self.assertFalse(faq.is_published)
        self.assertTrue(faq.active)
        copied_text = " ".join([faq.name, faq.answer, faq.keywords or ""])
        for private_value in (
            ticket.requester_id.name,
            ticket.contact,
            ticket.location,
            ticket.description,
            "비공개 댓글",
        ):
            self.assertNotIn(private_value, copied_text)
        self.assertEqual(
            ticket.read(
                ["state", "resolution", "resolved_date", "contact", "location"]
            )[0],
            original_values,
        )
        self.assertEqual(len(ticket.history_ids), original_history_count)

    def test_closed_ticket_draft_and_invalid_draft_access(self):
        closed_ticket = self._create_ticket("종료 초안")
        self._set_resolved(closed_ticket, state="closed")
        action = closed_ticket.with_user(self.agent).action_create_faq_draft()
        faq = self.env["it.helpdesk.faq"].browse(action["res_id"])
        self.assertEqual(faq.source_ticket_id, closed_ticket)
        self.assertFalse(faq.is_published)

        unresolved = self._create_ticket("미해결 차단")
        with self.assertRaises(UserError):
            unresolved.with_user(self.agent).action_create_faq_draft()
        with self.assertRaises(AccessError):
            closed_ticket.with_user(self.requester).action_create_faq_draft()

    def test_recommendations_rank_filter_limit_and_hide_private_data(self):
        exact = self._create_faq("사내 Wi-Fi 연결 문제 해결", publish=True)
        exact.with_user(self.agent).write(
            {
                "name": "사내 Wi-Fi 연결 문제 해결",
                "keywords": "와이파이 wifi 무선 연결",
            }
        )
        keyword = self._create_faq("무선 네트워크 점검", publish=True)
        keyword.with_user(self.agent).write({"keywords": "와이파이 인쇄 출력"})
        for index in range(4):
            faq = self._create_faq(f"추가 추천 {index}", publish=True)
            faq.with_user(self.agent).write({"keywords": "와이파이 연결"})
        private_faq = self._create_faq("와이파이 비공개")
        archived_faq = self._create_faq("와이파이 보관", publish=True)
        archived_faq.with_user(self.agent).action_archive()

        faq_model = self.env["it.helpdesk.faq"].with_user(self.requester)
        results = faq_model.search_recommendations(
            "사내 Wi-Fi 연결 문제 해결",
            self.category.id,
        )
        self.assertLessEqual(len(results), 3)
        self.assertEqual(results[0]["id"], exact.id)
        result_ids = {item["id"] for item in results}
        self.assertNotIn(private_faq.id, result_ids)
        self.assertNotIn(archived_faq.id, result_ids)
        for item in results:
            self.assertEqual(
                set(item),
                {"id", "name", "category_name", "answer_preview"},
            )

        keyword_results = faq_model.search_recommendations("인쇄가 안됩니다")
        self.assertIn(keyword.id, {item["id"] for item in keyword_results})
        category_results = faq_model.search_recommendations(
            "관련없는검색어",
            self.category.id,
        )
        self.assertTrue(category_results)
        self.assertEqual(faq_model.search_recommendations(""), [])
        self.assertEqual(faq_model.search_recommendations("가"), [])
        self.assertEqual(faq_model.search_recommendations("검색결과없음"), [])

        agent_results = (
            self.env["it.helpdesk.faq"]
            .with_user(self.agent)
            .search_recommendations("와이파이")
        )
        self.assertNotIn(private_faq.id, {item["id"] for item in agent_results})
        with self.assertRaises(AccessError):
            self.env["it.helpdesk.faq"].with_user(
                self.outsider
            ).search_recommendations("와이파이")
        with self.assertRaises(AccessError):
            faq_model.open_public_faq(private_faq.id)
        public_action = faq_model.open_public_faq(exact.id)
        self.assertEqual(public_action["res_id"], exact.id)
        self.assertEqual(public_action["target"], "new")

    def test_faq_views_and_recommendation_widget_are_scoped(self):
        ticket_view = self.env.ref("it_helpdesk.view_it_helpdesk_ticket_form")
        arch = etree.fromstring(ticket_view.arch_db.encode())
        title_fields = arch.xpath("//field[@name='name']")
        self.assertEqual(len(title_fields), 2)
        self.assertTrue(
            all(
                field.get("widget") == "it_helpdesk_faq_recommendation"
                for field in title_fields
            )
        )
        draft_buttons = arch.xpath("//button[@name='action_create_faq_draft']")
        self.assertEqual(len(draft_buttons), 1)
        self.assertEqual(
            draft_buttons[0].get("groups"),
            "it_helpdesk.group_it_helpdesk_agent",
        )

        public_form = self.env.ref("it_helpdesk.view_it_helpdesk_faq_public_form")
        public_arch = etree.fromstring(public_form.arch_db.encode())
        self.assertFalse(public_arch.xpath("//field[@name='source_ticket_id']"))
        management_form = self.env.ref(
            "it_helpdesk.view_it_helpdesk_faq_management_form"
        )
        management_arch = etree.fromstring(management_form.arch_db.encode())
        self.assertTrue(management_arch.xpath("//button[@name='action_publish']"))
        self.assertTrue(
            management_arch.xpath("//button[@name='action_unpublish']")
        )
        options = ast.literal_eval(
            management_arch.xpath("//field[@name='source_ticket_id']")[0].get(
                "options"
            )
        )
        self.assertTrue(options["no_create"])

    def test_day6_auto_assignment_and_dashboard_regression(self):
        category = (
            self.env["it.helpdesk.category"]
            .with_user(self.agent)
            .create(
                {
                    "name": "Day 7 자동 배정 회귀",
                    "code": "DAY7_AUTO_ASSIGN",
                    "default_user_id": self.agent.id,
                }
            )
        )
        ticket = self._create_ticket("자동 배정 회귀", category)
        self.assertEqual(ticket.assigned_user_id, self.agent)
        self.assertEqual(ticket.state, "assigned")
        self.assertTrue(ticket.reference.startswith("HD-"))
        self.assertTrue(
            ticket.history_ids.filtered(
                lambda history: history.change_type == "assignment"
            )
        )
        ticket.with_user(self.agent).action_assign_to(self.other_agent.id)
        self.assertEqual(ticket.assigned_user_id, self.other_agent)
        dashboard = (
            self.env["it.helpdesk.ticket"]
            .with_user(self.requester)
            .get_dashboard_data()
        )
        self.assertEqual(dashboard["role"], "employee")
        self.assertTrue(
            any(item["id"] == ticket.id for item in dashboard["recent_tickets"])
        )
