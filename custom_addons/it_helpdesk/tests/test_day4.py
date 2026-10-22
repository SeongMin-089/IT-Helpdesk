import ast

from psycopg2 import IntegrityError
from lxml import etree

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval


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

    def test_ticket_category_selector_is_restricted(self):
        view = self.env.ref("it_helpdesk.view_it_helpdesk_ticket_form")
        arch = etree.fromstring(view.arch_db.encode())
        category_fields = arch.xpath("//field[@name='category_id']")
        self.assertEqual(len(category_fields), 2)
        for field_node in category_fields:
            self.assertEqual(field_node.get("domain"), "[('active', '=', True)]")
            options = ast.literal_eval(field_node.get("options"))
            self.assertTrue(options["no_create"])
            self.assertTrue(options["no_create_edit"])
            self.assertTrue(options["no_open"])

        inactive_category = self.env["it.helpdesk.category"].with_user(
            self.agent
        ).create(
            {
                "name": "비활성 유형 테스트",
                "code": "INACTIVE_TEST",
                "active": False,
            }
        )
        values = self._ticket_values("비활성 유형 차단")
        values["category_id"] = inactive_category.id
        with self.assertRaises(ValidationError):
            self.env["it.helpdesk.ticket"].with_user(self.requester).create(values)

        with self.assertRaises(AccessError):
            inactive_category.with_user(self.requester).write(
                {"name": "직원 수정 시도"}
            )

        alternate_category = self.env["it.helpdesk.category"].with_user(
            self.agent
        ).create(
            {
                "name": "변경 가능 유형",
                "code": "CHANGE_TEST",
            }
        )
        alternate_category.with_user(self.agent).write(
            {"description": "설정 화면 관리 권한 회귀 테스트"}
        )
        ticket = self._create_ticket(suffix="유형 변경 권한")
        ticket.with_user(self.requester).write(
            {"category_id": alternate_category.id}
        )
        self.assertEqual(ticket.category_id, alternate_category)

        ticket.with_user(self.agent).action_assign_to(self.agent.id)
        with self.assertRaises(UserError):
            ticket.with_user(self.requester).write(
                {"category_id": self.category.id}
            )
        with self.assertRaises(AccessError):
            ticket.with_user(self.agent).write({"category_id": self.category.id})
        with self.assertRaises(ValidationError):
            ticket.sudo()._write_workflow({"category_id": inactive_category.id})

    def test_ticket_search_views_and_menu_actions(self):
        def get_search_arch(user, view):
            view_data = self.env["it.helpdesk.ticket"].with_user(user).get_view(
                view.id,
                "search",
            )
            return etree.fromstring(view_data["arch"].encode())

        state_filters = {
            "received",
            "assigned",
            "in_progress",
            "reopen_requested",
            "reopened_in_progress",
            "resolved",
            "closed",
        }
        priority_filters = {
            "priority_low",
            "priority_normal",
            "priority_high",
            "urgent",
        }

        my_search = self.env.ref("it_helpdesk.view_it_helpdesk_my_ticket_search")
        my_source_arch = etree.fromstring(my_search.arch_db.encode())
        self.assertEqual(
            {
                (node.tag, node.get("name"), node.get("groups"))
                for node in my_source_arch.xpath("//*[@groups]")
            },
            {
                (
                    "field",
                    "requester_id",
                    "it_helpdesk.group_it_helpdesk_agent",
                ),
                (
                    "filter",
                    "my_assigned",
                    "it_helpdesk.group_it_helpdesk_agent",
                ),
                (
                    "filter",
                    "unassigned",
                    "it_helpdesk.group_it_helpdesk_agent",
                ),
                (
                    "filter",
                    "group_by_assigned_user",
                    "it_helpdesk.group_it_helpdesk_agent",
                ),
            },
        )

        requester_my_arch = get_search_arch(self.requester, my_search)
        self.assertEqual(
            set(requester_my_arch.xpath("/search/field/@name")),
            {
                "reference",
                "name",
                "category_id",
                "state",
                "priority",
                "assigned_user_id",
            },
        )
        self.assertEqual(
            set(requester_my_arch.xpath("/search/filter/@name")),
            state_filters | priority_filters,
        )
        self.assertEqual(
            set(requester_my_arch.xpath("/search/group/filter/@name")),
            {"group_by_category", "group_by_state", "group_by_priority"},
        )

        agent_my_arch = get_search_arch(self.agent, my_search)
        self.assertEqual(
            set(agent_my_arch.xpath("/search/field/@name")),
            {
                "reference",
                "name",
                "requester_id",
                "category_id",
                "state",
                "priority",
                "assigned_user_id",
            },
        )
        self.assertEqual(
            set(agent_my_arch.xpath("/search/filter/@name")),
            state_filters | priority_filters | {"my_assigned", "unassigned"},
        )
        self.assertEqual(
            set(agent_my_arch.xpath("/search/group/filter/@name")),
            {
                "group_by_category",
                "group_by_state",
                "group_by_priority",
                "group_by_assigned_user",
            },
        )

        management_search = self.env.ref(
            "it_helpdesk.view_it_helpdesk_ticket_search"
        )
        management_arch = get_search_arch(self.agent, management_search)
        self.assertEqual(
            set(management_arch.xpath("/search/field/@name")),
            {
                "reference",
                "name",
                "requester_id",
                "category_id",
                "state",
                "priority",
                "assigned_user_id",
            },
        )
        self.assertEqual(
            set(management_arch.xpath("/search/filter/@name")),
            state_filters | priority_filters | {"my_assigned", "unassigned"},
        )
        self.assertEqual(
            set(management_arch.xpath("/search/group/filter/@name")),
            {
                "group_by_category",
                "group_by_state",
                "group_by_priority",
                "group_by_assigned_user",
            },
        )

        my_action = self.env.ref("it_helpdesk.action_it_helpdesk_my_tickets")
        self.assertEqual(my_action.search_view_id, my_search)
        for action_xmlid in (
            "it_helpdesk.action_it_helpdesk_ticket",
            "it_helpdesk.action_it_helpdesk_unassigned_tickets",
            "it_helpdesk.action_it_helpdesk_archived_tickets",
        ):
            self.assertEqual(
                self.env.ref(action_xmlid).search_view_id,
                management_search,
            )

        my_menu = self.env.ref("it_helpdesk.menu_it_helpdesk_my_tickets")
        user_group = self.env.ref("it_helpdesk.group_it_helpdesk_user")
        self.assertIn(user_group, my_menu.group_ids)
        self.assertTrue(
            self.requester.has_group("it_helpdesk.group_it_helpdesk_user")
        )
        self.assertTrue(
            self.agent.has_group("it_helpdesk.group_it_helpdesk_user")
        )

        requester_ticket = self._create_ticket(self.requester, "직원 내 문의")
        agent_ticket = self._create_ticket(self.agent, "담당자 내 문의")
        other_ticket = self._create_ticket(self.other_requester, "다른 직원 문의")
        for user, own_ticket in (
            (self.requester, requester_ticket),
            (self.agent, agent_ticket),
        ):
            action_domain = safe_eval(my_action.domain, {"uid": user.id})
            visible_tickets = self.env["it.helpdesk.ticket"].with_user(user).search(
                action_domain
            )
            self.assertIn(own_ticket, visible_tickets)
            self.assertNotIn(other_ticket, visible_tickets)
            self.assertTrue(
                all(ticket.requester_id == user for ticket in visible_tickets)
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

    def test_txt_utf8_bom_and_line_endings(self):
        ticket = self._create_ticket(suffix="TXT 인코딩")
        Attachment = self.env["ir.attachment"].with_user(self.requester)
        text_files = {
            "ascii.txt": b"plain ASCII text",
            "korean.txt": "한글 텍스트 첨부파일입니다.".encode("utf-8"),
            "bom.txt": b"\xef\xbb\xbf" + "BOM이 포함된 한글입니다.".encode("utf-8"),
            "crlf.txt": "첫 번째 줄\r\n두 번째 줄\r\n".encode("utf-8"),
        }
        for name, raw in text_files.items():
            attachment = Attachment.create(
                {
                    "name": name,
                    "raw": raw,
                    "res_model": ticket._name,
                    "res_id": ticket.id,
                }
            )
            self.assertTrue(attachment)

        pending = Attachment.create(
            {
                "name": "chatter-korean.txt",
                "raw": "Chatter 한글 TXT입니다.\r\n두 번째 줄입니다.".encode("utf-8"),
                "res_model": "mail.compose.message",
                "res_id": 0,
            }
        )
        message = ticket.with_user(self.requester).message_post(
            body="한글 TXT 첨부",
            attachment_ids=pending.ids,
        )
        self.assertEqual(pending.res_model, ticket._name)
        self.assertIn(pending, message.attachment_ids)

        binary_ticket = self._create_ticket(suffix="TXT 바이너리 차단")
        with self.assertRaises(ValidationError):
            Attachment.create(
                {
                    "name": "renamed-binary.txt",
                    "raw": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
                    "res_model": binary_ticket._name,
                    "res_id": binary_ticket.id,
                }
            )
        with self.assertRaises(ValidationError):
            Attachment.create(
                {
                    "name": "null-byte.txt",
                    "raw": b"text-looking-prefix\x00binary-content",
                    "res_model": binary_ticket._name,
                    "res_id": binary_ticket.id,
                }
            )
        with self.assertRaises(ValidationError):
            Attachment.create(
                {
                    "name": "invalid-utf8.txt",
                    "raw": b"invalid UTF-8: \xff\xfe\xfa",
                    "res_model": binary_ticket._name,
                    "res_id": binary_ticket.id,
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
