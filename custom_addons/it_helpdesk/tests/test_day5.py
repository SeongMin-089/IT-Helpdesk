import io
import zipfile

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "it_helpdesk_day5")
class TestHelpdeskDay5(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = new_test_user(
            cls.env,
            login="helpdesk_day5_requester",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.other_requester = new_test_user(
            cls.env,
            login="helpdesk_day5_other",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.agent = new_test_user(
            cls.env,
            login="helpdesk_day5_agent",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.category = cls.env.ref("it_helpdesk.category_etc")

    def _create_ticket(self, user=None, suffix="기본"):
        return self.env["it.helpdesk.ticket"].with_user(
            user or self.requester
        ).create(
            {
                "name": f"Day 5 테스트 문의 {suffix}",
                "description": "Day 5 안정화 검증을 위한 충분히 긴 내용입니다.",
                "category_id": self.category.id,
                "priority": "normal",
                "location": "테스트 부서",
            }
        )

    def _create_attachment(self, ticket, user=None, name="test.txt", raw=b"text"):
        return self.env["ir.attachment"].with_user(
            user or self.requester
        ).create(
            {
                "name": name,
                "raw": raw,
                "res_model": ticket._name,
                "res_id": ticket.id,
            }
        )

    @staticmethod
    def _office_file(prefix, filename):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types />")
            archive.writestr(f"{prefix}/{filename}", "document")
        return stream.getvalue()

    def test_reference_database_unique_constraint(self):
        self.cr.execute(
            """
            SELECT COUNT(*)
              FROM pg_constraint constraint_record
              JOIN pg_class table_record
                ON table_record.oid = constraint_record.conrelid
             WHERE table_record.relname = 'it_helpdesk_ticket'
               AND constraint_record.contype = 'u'
               AND pg_get_constraintdef(constraint_record.oid)
                   = 'UNIQUE (reference)'
            """
        )
        if not self.cr.fetchone()[0]:
            self.skipTest(
                "기존 중복 문의 번호 때문에 DB UNIQUE 제약이 아직 생성되지 않았습니다."
            )

        first = self._create_ticket(suffix="DB 고유성 1")
        second = self._create_ticket(suffix="DB 고유성 2")
        first.with_user(self.agent).write({"active": False})
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.cr.execute(
                "UPDATE it_helpdesk_ticket SET reference = %s WHERE id = %s",
                [first.reference, second.id],
            )

    def test_message_update_and_delete_security(self):
        ticket = self._create_ticket(suffix="댓글 권한")
        requester_message = ticket.with_user(self.requester).message_post(
            body="요청자 댓글",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        agent_message = ticket.with_user(self.agent).message_post(
            body="담당자 댓글",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

        requester_message.with_user(self.requester).write(
            {"body": "요청자가 수정한 댓글"}
        )
        requester_message.with_user(self.agent).write(
            {"body": "담당자가 관리한 요청자 댓글"}
        )
        agent_message.with_user(self.agent).write(
            {"body": "담당자가 수정한 댓글"}
        )
        agent_message.with_user(self.agent).unlink()

        requester_message_to_delete = ticket.with_user(self.requester).message_post(
            body="담당자가 삭제할 요청자 댓글",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        requester_message_to_delete.with_user(self.agent).unlink()

        another_agent_message = ticket.with_user(self.agent).message_post(
            body="담당자 두 번째 댓글",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        with self.assertRaises(AccessError):
            another_agent_message.with_user(self.requester).sudo().write(
                {"body": "타인 댓글 수정 우회"}
            )
        with self.assertRaises(AccessError):
            another_agent_message.with_user(self.requester).sudo().unlink()
        with self.assertRaises(AccessError):
            requester_message.with_user(self.other_requester).sudo().write(
                {"body": "타인 문의 댓글 수정 우회"}
            )

        ticket.sudo()._write_workflow({"state": "closed"})
        for user in (self.requester, self.agent):
            with self.assertRaises(UserError):
                requester_message.with_user(user).sudo().write(
                    {"body": "종료 댓글 수정"}
                )
            with self.assertRaises(UserError):
                requester_message.with_user(user).sudo().unlink()

    def test_attachment_update_delete_and_relink_security(self):
        own_ticket = self._create_ticket(suffix="첨부 권한")
        other_ticket = self._create_ticket(self.other_requester, "타인 첨부 권한")
        attachment = self._create_attachment(own_ticket)
        other_attachment = self._create_attachment(
            other_ticket,
            self.other_requester,
            "other.txt",
            b"other text",
        )

        with self.assertRaises(AccessError):
            attachment.with_user(self.other_requester).sudo().write(
                {"name": "blocked.txt"}
            )
        with self.assertRaises(AccessError):
            attachment.with_user(self.other_requester).sudo().unlink()
        with self.assertRaises(AccessError):
            other_attachment.with_user(self.requester).sudo().write(
                {"res_id": own_ticket.id}
            )
        with self.assertRaises(AccessError):
            attachment.with_user(self.requester).sudo().write(
                {"res_id": other_ticket.id}
            )

        attachment.with_user(self.agent).write({"name": "agent-updated.txt"})
        self.assertEqual(attachment.name, "agent-updated.txt")
        agent_managed_attachment = self._create_attachment(
            own_ticket,
            name="agent-delete.txt",
            raw=b"agent delete",
        )
        agent_managed_attachment.with_user(self.agent).unlink()
        self.assertFalse(agent_managed_attachment.exists())

        own_ticket.sudo()._write_workflow({"state": "closed"})
        for user in (self.requester, self.agent):
            with self.assertRaises(AccessError):
                attachment.with_user(user).sudo().write({"res_id": 0})
            with self.assertRaises(AccessError):
                attachment.with_user(user).sudo().unlink()

    def test_archive_restore_preserves_related_records(self):
        employee_ticket = self._create_ticket(suffix="직원 보관")
        employee_ticket.with_user(self.requester).write({"active": False})
        self.assertFalse(employee_ticket.active)
        with self.assertRaises(AccessError):
            employee_ticket.with_context(active_test=False).with_user(
                self.requester
            ).write({"active": True})

        assigned_ticket = self._create_ticket(suffix="배정 후 직원 보관 차단")
        assigned_ticket.with_user(self.agent).action_assign_to(self.agent.id)
        with self.assertRaises(UserError):
            assigned_ticket.with_user(self.requester).write({"active": False})

        ticket = self._create_ticket(suffix="관계 보존")
        message = ticket.with_user(self.requester).message_post(body="보존할 댓글")
        attachment = self._create_attachment(ticket, name="preserve.txt")
        history = self.env["it.helpdesk.history"].sudo().create(
            {
                "ticket_id": ticket.id,
                "change_type": "state",
                "old_value": "접수",
                "new_value": "종료",
                "description": "보관·복원 관계 보존 테스트",
            }
        )
        resolved_date = fields.Datetime.now()
        ticket.sudo()._write_workflow(
            {
                "state": "closed",
                "resolution_method": "remote",
                "resolution": "보존할 해결 정보입니다.",
                "resolved_date": resolved_date,
                "closed_date": resolved_date,
            }
        )
        expected_values = (
            ticket.state,
            ticket.resolution_method,
            ticket.resolution,
            ticket.resolved_date,
            ticket.closed_date,
        )

        ticket.with_user(self.agent).write({"active": False})
        self.assertFalse(ticket.active)
        self.assertTrue(message.exists())
        self.assertTrue(attachment.exists())
        self.assertTrue(history.exists())
        with self.assertRaises(AccessError):
            attachment.with_user(self.agent).unlink()

        ticket.with_context(active_test=False).with_user(self.agent).write(
            {"active": True}
        )
        self.assertTrue(ticket.active)
        self.assertEqual(
            (
                ticket.state,
                ticket.resolution_method,
                ticket.resolution,
                ticket.resolved_date,
                ticket.closed_date,
            ),
            expected_values,
        )
        self.assertTrue(message.exists())
        self.assertTrue(attachment.exists())
        self.assertTrue(history.exists())

    def test_all_allowed_attachment_formats_and_mismatches(self):
        valid_files = {
            "image.jpg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00image",
            "image.jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00image",
            "image.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            "document.pdf": b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF",
            "document.docx": self._office_file("word", "document.xml"),
            "workbook.xlsx": self._office_file("xl", "workbook.xml"),
            "korean.txt": "한글 UTF-8\r\n두 번째 줄".encode("utf-8"),
            "bom.txt": b"\xef\xbb\xbf" + "BOM 한글".encode("utf-8"),
        }
        for index, (name, raw) in enumerate(valid_files.items()):
            ticket = self._create_ticket(suffix=f"정상 형식 {index}")
            self.assertTrue(self._create_attachment(ticket, name=name, raw=raw))

        mismatches = {
            "fake.jpg": b"%PDF-1.4\nnot a jpeg",
            "fake.png": b"%PDF-1.4\nnot a png",
            "fake.pdf": b"\x89PNG\r\n\x1a\nnot a pdf",
            "fake.docx": self._office_file("xl", "workbook.xml"),
            "fake.xlsx": self._office_file("word", "document.xml"),
            "fake.txt": b"\x89PNG\r\n\x1a\nnot text",
        }
        for index, (name, raw) in enumerate(mismatches.items()):
            ticket = self._create_ticket(suffix=f"불일치 형식 {index}")
            with self.assertRaises(ValidationError):
                self._create_attachment(ticket, name=name, raw=raw)

    def test_attachment_size_count_and_chatter_regression(self):
        size_ticket = self._create_ticket(suffix="크기 제한")
        with self.assertRaises(ValidationError):
            self._create_attachment(
                size_ticket,
                name="oversized.txt",
                raw=b"x" * (10 * 1024 * 1024 + 1),
            )

        count_ticket = self._create_ticket(suffix="개수 제한")
        for index in range(5):
            self._create_attachment(
                count_ticket,
                name=f"allowed-{index}.txt",
                raw=f"attachment {index}".encode(),
            )
        with self.assertRaises(ValidationError):
            self._create_attachment(count_ticket, name="sixth.txt")

        chatter_ticket = self._create_ticket(suffix="Chatter 첨부")
        pending = self.env["ir.attachment"].with_user(self.requester).create(
            {
                "name": "chatter.txt",
                "raw": "정상 Chatter 첨부\r\n".encode("utf-8"),
                "res_model": "mail.compose.message",
                "res_id": 0,
            }
        )
        message = chatter_ticket.with_user(self.requester).message_post(
            body="첨부파일을 포함한 정상 댓글",
            attachment_ids=pending.ids,
        )
        self.assertEqual(pending.res_model, chatter_ticket._name)
        self.assertEqual(pending.res_id, chatter_ticket.id)
        self.assertIn(pending, message.attachment_ids)
