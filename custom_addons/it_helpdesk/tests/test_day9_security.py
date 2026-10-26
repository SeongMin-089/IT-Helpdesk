"""Day 9 targeted security regression cases; run only on the test DB."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "it_helpdesk_day9_security")
class TestHelpdeskDay9Security(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = new_test_user(
            cls.env, login="helpdesk_day9_sec_employee",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.agent = new_test_user(
            cls.env, login="helpdesk_day9_sec_agent",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.other_agent = new_test_user(
            cls.env, login="helpdesk_day9_sec_other_agent",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.outsider = new_test_user(
            cls.env, login="helpdesk_day9_sec_outsider",
            groups="base.group_user",
        )
        cls.category = cls.env["it.helpdesk.category"].with_user(cls.agent).create({
            "name": "Day9 보안 확인", "code": "DAY9_SECURITY_CHECK",
            "default_user_id": cls.agent.id,
        })

    def _ticket(self):
        return self.env["it.helpdesk.ticket"].with_user(self.employee).create({
            "name": "보관/댓글 보안", "description": "보관 상태 전이 방지 회귀 테스트입니다.",
            "location": "보안 테스트", "priority": "normal",
            "category_id": self.category.id,
        })

    def test_archived_ticket_cannot_reassign_or_start_progress(self):
        ticket = self._ticket()
        ticket.with_user(self.agent).write({"active": False})
        for callback in (
            lambda: ticket.with_user(self.agent).action_assign_to(self.other_agent.id),
            lambda: ticket.with_user(self.agent).action_start_progress(),
        ):
            with self.assertRaises(UserError):
                callback()
        self.assertFalse(ticket.active)
        self.assertEqual(ticket.state, "assigned")

    def test_archived_reopen_request_cannot_start_reopen(self):
        ticket = self._ticket()
        ticket.sudo()._write_workflow({"state": "reopen_requested"})
        ticket.with_user(self.agent).write({"active": False})
        with self.assertRaises(UserError):
            ticket.with_user(self.agent).action_start_reopen()
        self.assertEqual(ticket.state, "reopen_requested")

    def test_non_member_cannot_create_ticket_comment_via_sudo(self):
        ticket = self._ticket()
        with self.assertRaises(AccessError):
            self.env["mail.message"].with_user(self.outsider).sudo().create({
                "model": "it.helpdesk.ticket", "res_id": ticket.id,
                "message_type": "comment", "body": "권한 우회 시도",
            })

    def test_employee_can_still_post_on_own_active_ticket(self):
        ticket = self._ticket()
        message = ticket.with_user(self.employee).message_post(body="정상 댓글")
        self.assertEqual(message.model, "it.helpdesk.ticket")
        self.assertEqual(message.res_id, ticket.id)
