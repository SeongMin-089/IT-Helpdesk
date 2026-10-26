"""Day 9 backend regression tests for IT Helpdesk.

Run with an Odoo test database and --test-tags /it_helpdesk:it_helpdesk_day9.
These tests run inside Odoo's transaction test framework.
"""

from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "it_helpdesk_day9")
class TestHelpdeskDay9(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = new_test_user(
            cls.env,
            login="helpdesk_day9_employee",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.other_employee = new_test_user(
            cls.env,
            login="helpdesk_day9_other_employee",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.agent = new_test_user(
            cls.env,
            login="helpdesk_day9_agent",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.other_agent = new_test_user(
            cls.env,
            login="helpdesk_day9_other_agent",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.category_assigned = cls.env["it.helpdesk.category"].with_user(
            cls.agent
        ).create({
            "name": "Day9 자동 배정",
            "code": "DAY9_ASSIGNED",
            "default_user_id": cls.agent.id,
        })
        cls.category_unassigned = cls.env["it.helpdesk.category"].with_user(
            cls.agent
        ).create({
            "name": "Day9 미배정",
            "code": "DAY9_UNASSIGNED",
        })
        cls.category_other = cls.env["it.helpdesk.category"].with_user(
            cls.agent
        ).create({
            "name": "Day9 다른 담당자",
            "code": "DAY9_OTHER",
            "default_user_id": cls.other_agent.id,
        })

    def _ticket(self, requester=None, category=None):
        return self.env["it.helpdesk.ticket"].with_user(
            requester or self.employee
        ).create({
            "name": "Day9 문의 원본 제목",
            "description": "Day 9 회귀 테스트용 장애 상황을 자세하게 작성합니다.",
            "location": "테스트 부서",
            "priority": "normal",
            "category_id": (category or self.category_assigned).id,
        })

    def test_employee_can_edit_received_and_assigned_tickets(self):
        for category in (self.category_unassigned, self.category_assigned):
            ticket = self._ticket(category=category)
            self.assertIn(ticket.state, ("received", "assigned"))
            ticket.with_user(self.employee).write({"name": "Day9 변경된 문의 제목"})
            self.assertEqual(ticket.name, "Day9 변경된 문의 제목")

    def test_employee_cannot_edit_other_requester_ticket(self):
        ticket = self._ticket()
        with self.assertRaises(AccessError):
            ticket.with_user(self.other_employee).write({
                "name": "Day9 타인 문의 수정 시도",
            })

    def test_employee_archive_restore_and_no_edit_while_archived(self):
        ticket = self._ticket()
        ticket.with_user(self.employee).write({"active": False})
        self.assertFalse(ticket.active)
        archived = self.env["it.helpdesk.ticket"].with_user(
            self.employee
        ).with_context(active_test=False).search([("id", "=", ticket.id)])
        self.assertEqual(archived, ticket)
        with self.assertRaises(AccessError):
            archived.write({"name": "Day9 보관 중 내용 수정 시도"})
        with self.assertRaises(AccessError):
            archived.write({"active": True, "name": "Day9 동시 수정 시도"})
        archived.write({"active": True})
        self.assertTrue(ticket.active)
        ticket.with_user(self.employee).write({"name": "Day9 복원 이후 수정 성공"})
        self.assertEqual(ticket.name, "Day9 복원 이후 수정 성공")

    def test_employee_cannot_archive_or_restore_after_progress(self):
        ticket = self._ticket()
        ticket.with_user(self.agent).action_start_progress()
        with self.assertRaises(UserError):
            ticket.with_user(self.employee).write({"active": False})
        with self.assertRaises(UserError):
            ticket.with_user(self.employee).write({"name": "Day9 진행 중 수정 시도"})

    def test_agent_own_ticket_edit_and_other_ticket_blocked(self):
        own = self._ticket(requester=self.agent)
        own.with_user(self.agent).write({
            "description": "Day9 IT 담당자가 본인 문의 내용을 변경했습니다.",
        })
        self.assertIn("담당자가", own.description)
        other = self._ticket(requester=self.employee)
        with self.assertRaises(AccessError):
            other.with_user(self.agent).write({
                "name": "Day9 타인 문의 내용 수정 시도",
            })
        other.with_user(self.agent).write({"priority": "high"})
        self.assertEqual(other.priority, "high")

    def test_agent_archived_own_ticket_cannot_edit_content(self):
        own = self._ticket(requester=self.agent)
        own.with_user(self.agent).write({"active": False})
        with self.assertRaises(AccessError):
            own.with_user(self.agent).write({
                "name": "Day9 보관 중 담당자 내용 수정 시도",
            })
        own.with_user(self.agent).write({"active": True})
        own.with_user(self.agent).write({"name": "Day9 복원된 담당자 문의"})
        self.assertEqual(own.name, "Day9 복원된 담당자 문의")

    def test_category_change_reassigns_and_records_history(self):
        ticket = self._ticket()
        self.assertEqual(ticket.assigned_user_id, self.agent)
        ticket.with_user(self.employee).write({
            "category_id": self.category_other.id,
        })
        self.assertEqual(ticket.assigned_user_id, self.other_agent)
        self.assertEqual(ticket.state, "assigned")
        self.assertTrue(ticket.history_ids.filtered(
            lambda h: h.change_type == "assignment"
            and h.new_value == self.other_agent.name
        ))
        ticket.with_user(self.employee).write({
            "category_id": self.category_unassigned.id,
        })
        self.assertFalse(ticket.assigned_user_id)
        self.assertEqual(ticket.state, "received")
        self.assertTrue(ticket.history_ids.filtered(
            lambda h: h.change_type == "state" and h.new_value == "접수"
        ))

    def test_form_readonly_rules_for_both_roles(self):
        arch = etree.fromstring(self.env.ref(
            "it_helpdesk.view_it_helpdesk_ticket_form"
        ).arch_db.encode())
        for field_name in ("name", "description", "category_id", "location", "contact"):
            fields = arch.xpath(f"//field[@name='{field_name}']")
            for group, condition in (
                (
                    "it_helpdesk.group_it_helpdesk_agent",
                    "id != False and (not active or requester_id != uid or state not in ('received', 'assigned'))",
                ),
                (
                    "!it_helpdesk.group_it_helpdesk_agent",
                    "id != False and (not active or state not in ('received', 'assigned'))",
                ),
            ):
                matches = [f for f in fields if f.get("groups") == group]
                self.assertEqual(len(matches), 1, (field_name, group))
                self.assertEqual(matches[0].get("readonly"), condition)

    def test_archived_filter_disables_active_test(self):
        arch = etree.fromstring(self.env.ref(
            "it_helpdesk.view_it_helpdesk_my_ticket_search"
        ).arch_db.encode())
        filters = arch.xpath("//filter[@name='archived_my_tickets']")
        self.assertEqual(len(filters), 1)
        self.assertIn("('active', '=', False)", filters[0].get("domain"))
        self.assertIn("'active_test': False", filters[0].get("context"))

    def test_helpdesk_navigation_keeps_native_action_container(self):
        # Static architecture regression; browser-level layout still needs manual checks.
        from pathlib import Path
        base = Path(__file__).resolve().parents[1]
        xml = (base / "static/src/sidebar/webclient_patch.xml").read_text(encoding="utf-8")
        root = etree.fromstring(xml.encode())
        self.assertEqual(len(root.xpath("//xpath[@position='before']/HelpdeskSidebar")), 1)
        self.assertEqual(len(root.xpath("//xpath[@position='replace']")), 0)
