import ast

from lxml import etree
from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "it_helpdesk_day6")
class TestHelpdeskDay6(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = new_test_user(
            cls.env,
            login="helpdesk_day6_requester",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.agent1 = new_test_user(
            cls.env,
            login="helpdesk_day6_agent1",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.agent2 = new_test_user(
            cls.env,
            login="helpdesk_day6_agent2",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.agent3 = new_test_user(
            cls.env,
            login="helpdesk_day6_agent3",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.non_agent = new_test_user(
            cls.env,
            login="helpdesk_day6_non_agent",
            groups="base.group_user",
        )
        cls.portal_user = new_test_user(
            cls.env,
            login="helpdesk_day6_portal",
            groups="base.group_portal",
        )
        cls.agent_group = cls.env.ref("it_helpdesk.group_it_helpdesk_agent")
        cls.portal_group = cls.env.ref("base.group_portal")

    def _category(self, code, default_user=None):
        values = {
            "name": f"Day 6 유형 {code}",
            "code": f"DAY6_{code}",
        }
        if default_user:
            values["default_user_id"] = default_user.id
        return (
            self.env["it.helpdesk.category"]
            .with_user(self.agent1)
            .create(values)
        )

    @staticmethod
    def _ticket_values(category, suffix="기본"):
        return {
            "name": f"Day 6 문의 {suffix}",
            "description": "자동 담당자 배정 검증을 위한 충분히 긴 문의 내용입니다.",
            "category_id": category.id,
            "priority": "normal",
            "location": "테스트 부서",
        }

    def _create_ticket(self, category, suffix="기본", user=None):
        return (
            self.env["it.helpdesk.ticket"]
            .with_user(user or self.requester)
            .create(self._ticket_values(category, suffix))
        )

    def test_valid_default_agent_auto_assigns_and_records_history(self):
        first_category = self._category("NORMAL_1", self.agent1)
        second_category = self._category("NORMAL_2", self.agent1)

        first = self._create_ticket(first_category, "정상 배정")
        second = self._create_ticket(second_category, "복수 유형")

        for ticket in (first, second):
            self.assertEqual(ticket.requester_id, self.requester)
            self.assertEqual(ticket.assigned_user_id, self.agent1)
            self.assertEqual(ticket.state, "assigned")
            assignment_history = ticket.history_ids.filtered(
                lambda item: item.change_type == "assignment"
            )
            self.assertEqual(len(assignment_history), 1)
            self.assertEqual(assignment_history.old_value, "미배정")
            self.assertEqual(assignment_history.new_value, self.agent1.name)
            self.assertEqual(assignment_history.changed_by, self.requester)
            self.assertEqual(
                assignment_history.description,
                "문의 유형에 따른 담당자 자동 배정",
            )

    def test_missing_default_agent_stays_received_without_history(self):
        category = self._category("NO_DEFAULT")
        ticket = self._create_ticket(category, "기본 담당자 없음")

        self.assertFalse(ticket.assigned_user_id)
        self.assertEqual(ticket.state, "received")
        self.assertFalse(
            ticket.history_ids.filtered(
                lambda item: item.change_type == "assignment"
            )
        )

    def test_invalidated_defaults_skip_auto_assignment(self):
        inactive_category = self._category("INACTIVE", self.agent1)
        revoked_category = self._category("REVOKED", self.agent2)
        external_category = self._category("EXTERNAL", self.agent3)

        self.agent1.sudo().write({"active": False})
        self.agent2.sudo().write(
            {"group_ids": [Command.unlink(self.agent_group.id)]}
        )
        self.agent3.sudo().write(
            {"group_ids": [Command.set([self.portal_group.id])]}
        )

        tickets = (
            self.env["it.helpdesk.ticket"]
            .with_user(self.requester)
            .create(
                [
                    self._ticket_values(inactive_category, "비활성"),
                    self._ticket_values(revoked_category, "권한 제거"),
                    self._ticket_values(external_category, "외부 사용자"),
                ]
            )
        )
        self.assertEqual(tickets.mapped("state"), ["received"] * 3)
        self.assertFalse(tickets.mapped("assigned_user_id"))
        self.assertFalse(
            tickets.mapped("history_ids").filtered(
                lambda item: item.change_type == "assignment"
            )
        )

    def test_default_agent_configuration_validation_and_view(self):
        category = self._category("VALIDATION")
        view_ids = [
            "it_helpdesk.view_it_helpdesk_category_list",
            "it_helpdesk.view_it_helpdesk_category_form",
        ]
        for view_id in view_ids:
            arch = etree.fromstring(self.env.ref(view_id).arch_db.encode())
            fields = arch.xpath("//field[@name='default_user_id']")
            self.assertEqual(len(fields), 1)
            options = ast.literal_eval(fields[0].get("options"))
            self.assertTrue(options["no_create"])
            self.assertTrue(options["no_create_edit"])
            self.assertTrue(options["no_open"])

        with self.assertRaises(AccessError):
            category.with_user(self.requester).write(
                {"default_user_id": self.agent1.id}
            )
        for invalid_user in (self.non_agent, self.portal_user):
            with self.assertRaises(ValidationError):
                category.with_user(self.agent1).write(
                    {"default_user_id": invalid_user.id}
                )

        self.agent2.sudo().write({"active": False})
        with self.assertRaises(ValidationError):
            category.with_user(self.agent1).write(
                {"default_user_id": self.agent2.id}
            )

        category.with_user(self.agent1).write(
            {"default_user_id": self.agent1.id}
        )
        self.agent1.sudo().write({"active": False})
        category.with_user(self.agent2).write({"description": "설명 변경 허용"})
        self.assertEqual(category.description, "설명 변경 허용")

    def test_client_cannot_inject_assignment_or_initial_state(self):
        category = self._category("SECURITY", self.agent1)
        assigned_values = self._ticket_values(category, "담당자 조작")
        assigned_values["assigned_user_id"] = self.agent2.id
        with self.assertRaises(AccessError):
            self.env["it.helpdesk.ticket"].with_user(self.requester).create(
                assigned_values
            )

        state_values = self._ticket_values(category, "상태 조작")
        state_values["state"] = "assigned"
        with self.assertRaises(AccessError):
            self.env["it.helpdesk.ticket"].with_user(self.requester).create(
                state_values
            )

    def test_auto_assignment_remains_compatible_with_manual_workflow(self):
        category = self._category("REASSIGN", self.agent1)
        ticket = self._create_ticket(category, "재배정")

        ticket.with_user(self.agent1).action_assign_to(self.agent2.id)
        self.assertEqual(ticket.assigned_user_id, self.agent2)
        self.assertEqual(ticket.state, "assigned")
        assignment_history = ticket.history_ids.filtered(
            lambda item: item.change_type == "assignment"
        )
        self.assertEqual(len(assignment_history), 2)
        self.assertTrue(
            any(
                "담당자 배정:" in item.description
                for item in assignment_history
            )
        )

        ticket.sudo()._write_workflow({"state": "closed"})
        with self.assertRaises(UserError):
            ticket.with_user(self.agent2).action_assign_to(self.agent1.id)

    def test_category_change_does_not_reassign_existing_ticket(self):
        original = self._category("ORIGINAL", self.agent1)
        replacement = self._category("REPLACEMENT", self.agent2)
        ticket = self._create_ticket(original, "유형 변경")
        history_count = len(ticket.history_ids)

        ticket.sudo()._write_workflow({"category_id": replacement.id})

        self.assertEqual(ticket.category_id, replacement)
        self.assertEqual(ticket.assigned_user_id, self.agent1)
        self.assertEqual(len(ticket.history_ids), history_count)

    def test_multi_create_assigns_each_category_and_keeps_references_unique(self):
        assigned_category = self._category("MULTI_ASSIGNED", self.agent1)
        unassigned_category = self._category("MULTI_UNASSIGNED")
        tickets = (
            self.env["it.helpdesk.ticket"]
            .with_user(self.requester)
            .create(
                [
                    self._ticket_values(assigned_category, "다중 배정"),
                    self._ticket_values(unassigned_category, "다중 미배정"),
                ]
            )
        )

        self.assertEqual(tickets[0].assigned_user_id, self.agent1)
        self.assertEqual(tickets[0].state, "assigned")
        self.assertFalse(tickets[1].assigned_user_id)
        self.assertEqual(tickets[1].state, "received")
        self.assertNotEqual(tickets[0].reference, tickets[1].reference)

        tickets[0].with_user(self.agent1).write({"active": False})
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.cr.execute(
                "UPDATE it_helpdesk_ticket SET reference = %s WHERE id = %s",
                [tickets[0].reference, tickets[1].id],
            )
