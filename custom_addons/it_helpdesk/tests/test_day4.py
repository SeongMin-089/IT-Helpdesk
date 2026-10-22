from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "it_helpdesk_day4")
class TestHelpdeskDay4(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = new_test_user(
            cls.env,
            login="helpdesk_day4_requester",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.other_requester = new_test_user(
            cls.env,
            login="helpdesk_day4_other",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.agent = new_test_user(
            cls.env,
            login="helpdesk_day4_agent",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.category = cls.env.ref("it_helpdesk.category_etc")

    def _ticket_values(self, suffix="기본"):
        return {
            "name": f"테스트 문의 {suffix}",
            "description": "테스트를 위한 충분히 긴 문의 내용입니다.",
            "category_id": self.category.id,
            "priority": "normal",
            "location": "테스트 부서",
        }

    def _create_ticket(self, user=None, suffix="기본"):
        return self.env["it.helpdesk.ticket"].with_user(
            user or self.requester
        ).create(self._ticket_values(suffix))

    def test_requester_is_forced_for_agents_too(self):
        values = self._ticket_values("대리 등록 차단")
        values["requester_id"] = self.requester.id
        with self.assertRaises(AccessError):
            self.env["it.helpdesk.ticket"].with_user(self.agent).create(values)

        ticket = self._create_ticket(self.agent, "담당자 본인 등록")
        self.assertEqual(ticket.requester_id, self.agent)

    def test_new_references_are_unique(self):
        first = self._create_ticket(suffix="번호 1")
        second = self._create_ticket(suffix="번호 2")
        self.assertNotEqual(first.reference, second.reference)

        with self.assertRaises(ValidationError):
            second.sudo()._write_workflow({"reference": first.reference})

    def test_category_code_database_constraint(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["it.helpdesk.category"].create(
                {
                    "name": "중복 코드 테스트",
                    "code": self.category.code,
                }
            )

    def test_attachment_type_size_count_and_owner(self):
        ticket = self._create_ticket(suffix="첨부 제한")
        Attachment = self.env["ir.attachment"].with_user(self.requester)
        base_values = {
            "raw": b"plain text attachment",
            "res_model": ticket._name,
            "res_id": ticket.id,
        }
        for index in range(5):
            Attachment.create({**base_values, "name": f"allowed-{index}.txt"})

        with self.assertRaises(ValidationError):
            Attachment.create({**base_values, "name": "sixth.txt"})

        other_ticket = self._create_ticket(suffix="형식 제한")
        with self.assertRaises(ValidationError):
            Attachment.create(
                {
                    **base_values,
                    "name": "blocked.exe",
                    "res_id": other_ticket.id,
                }
            )
        with self.assertRaises(ValidationError):
            Attachment.create(
                {
                    **base_values,
                    "name": "oversized.txt",
                    "raw": b"x" * (10 * 1024 * 1024 + 1),
                    "res_id": other_ticket.id,
                }
            )
        with self.assertRaises(AccessError):
            self.env["ir.attachment"].with_user(self.other_requester).create(
                {
                    **base_values,
                    "name": "other-user.txt",
                    "res_id": other_ticket.id,
                }
            )

    def test_pending_attachment_reconnect_and_closed_ticket(self):
        ticket = self._create_ticket(suffix="임시 첨부")
        pending = self.env["ir.attachment"].with_user(self.requester).create(
            {
                "name": "pending.txt",
                "raw": b"pending attachment",
                "res_model": "mail.compose.message",
                "res_id": 0,
            }
        )
        pending.sudo().write(
            {"res_model": ticket._name, "res_id": ticket.id}
        )
        self.assertEqual(pending.res_id, ticket.id)

        ticket.sudo()._write_workflow({"state": "closed"})
        another_pending = self.env["ir.attachment"].with_user(
            self.requester
        ).create(
            {
                "name": "closed.txt",
                "raw": b"closed attachment",
                "res_model": "mail.compose.message",
                "res_id": 0,
            }
        )
        with self.assertRaises(AccessError):
            another_pending.sudo().write(
                {"res_model": ticket._name, "res_id": ticket.id}
            )

    def test_normal_chatter_attachment_flow(self):
        ticket = self._create_ticket(suffix="정상 Chatter")
        pending = self.env["ir.attachment"].with_user(self.requester).create(
            {
                "name": "normal.txt",
                "raw": b"normal chatter attachment",
                "res_model": "mail.compose.message",
                "res_id": 0,
            }
        )
        message = ticket.with_user(self.requester).message_post(
            body="정상 댓글과 첨부파일",
            attachment_ids=pending.ids,
        )
        self.assertEqual(pending.res_model, ticket._name)
        self.assertEqual(pending.res_id, ticket.id)
        self.assertIn(pending, message.attachment_ids)

    def test_existing_workflow_history_and_archive_regression(self):
        ticket = self._create_ticket(suffix="업무 흐름 회귀")
        ticket.with_user(self.agent).action_assign_to(self.agent.id)
        ticket.with_user(self.agent).action_start_progress()
        self.env["it.helpdesk.resolution.wizard"].with_user(self.agent).create(
            {
                "ticket_id": ticket.id,
                "resolution_method": "remote",
                "resolution": "원격 안내로 문제를 해결했습니다.",
            }
        ).action_confirm()
        self.assertEqual(ticket.state, "resolved")

        self.env["it.helpdesk.reopen.wizard"].with_user(self.requester).create(
            {
                "ticket_id": ticket.id,
                "reason": "문제가 다시 발생했습니다.",
            }
        ).action_confirm()
        ticket.with_user(self.agent).action_start_reopen()
        self.env["it.helpdesk.resolution.wizard"].with_user(self.agent).create(
            {
                "ticket_id": ticket.id,
                "resolution_method": "onsite",
                "resolution": "현장 점검 후 문제를 해결했습니다.",
            }
        ).action_confirm()
        self.env["it.helpdesk.close.wizard"].with_user(self.requester).create(
            {"ticket_id": ticket.id}
        ).action_confirm()

        self.assertEqual(ticket.state, "closed")
        self.assertEqual(ticket.reopen_count, 1)
        self.assertTrue(ticket.history_ids.filtered(lambda item: item.change_type == "state"))
        self.assertTrue(
            ticket.history_ids.filtered(lambda item: item.change_type == "resolution")
        )
        ticket.with_user(self.agent).write({"active": False})
        ticket.with_context(active_test=False).with_user(self.agent).write(
            {"active": True}
        )
        self.assertTrue(ticket.active)

    def test_direct_message_attachment_bypass_is_blocked(self):
        ticket = self._create_ticket(suffix="메시지 우회")
        pending = self.env["ir.attachment"].with_user(self.requester).create(
            {
                "name": "pending.txt",
                "raw": b"pending attachment",
                "res_model": "mail.compose.message",
                "res_id": 0,
            }
        )
        with self.assertRaises(AccessError):
            self.env["mail.message"].with_user(self.requester).sudo().create(
                {
                    "model": ticket._name,
                    "res_id": ticket.id,
                    "message_type": "comment",
                    "body": "직접 생성 우회 시도",
                    "attachment_ids": [(4, pending.id)],
                }
            )
