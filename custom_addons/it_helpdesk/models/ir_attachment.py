import base64
import io
import os
import unicodedata
import zipfile
from collections import defaultdict

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.mimetypes import guess_mimetype


class HelpdeskAttachment(models.Model):
    _inherit = "ir.attachment"

    _HELPDESK_MODEL = "it.helpdesk.ticket"
    _MAX_FILE_SIZE = 10 * 1024 * 1024
    _MAX_FILE_COUNT = 5
    _ALLOWED_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".pdf",
        ".docx",
        ".xlsx",
        ".txt",
    }
    _BINARY_SIGNATURES = (
        b"%PDF-",
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff",
        b"PK\x03\x04",
        b"GIF87a",
        b"GIF89a",
        b"MZ",
        b"\x7fELF",
        b"\x1f\x8b",
    )

    @api.model
    def _helpdesk_raw_from_values(self, vals, attachment=None):
        if "raw" in vals:
            raw = vals.get("raw") or b""
            return raw.encode() if isinstance(raw, str) else raw
        if "datas" in vals:
            try:
                return base64.b64decode(vals.get("datas") or b"", validate=True)
            except (ValueError, TypeError):
                raise ValidationError("첨부파일 데이터가 올바르지 않습니다.")
        return attachment.raw or b"" if attachment else b""

    @api.model
    def _validate_helpdesk_file(self, name, raw):
        extension = os.path.splitext(name or "")[1].lower()
        if extension not in self._ALLOWED_EXTENSIONS:
            raise ValidationError(
                "첨부파일은 JPG, PNG, PDF, DOCX, XLSX, TXT 형식만 "
                "업로드할 수 있습니다."
            )
        if len(raw) > self._MAX_FILE_SIZE:
            raise ValidationError("첨부파일은 파일당 10MB를 초과할 수 없습니다.")

        detected_type = guess_mimetype(raw) if raw else "application/octet-stream"
        if extension in (".jpg", ".jpeg") and detected_type != "image/jpeg":
            raise ValidationError("JPG 확장자와 실제 파일 형식이 일치하지 않습니다.")
        if extension == ".png" and detected_type != "image/png":
            raise ValidationError("PNG 확장자와 실제 파일 형식이 일치하지 않습니다.")
        if extension == ".pdf" and detected_type != "application/pdf":
            raise ValidationError("PDF 확장자와 실제 파일 형식이 일치하지 않습니다.")
        if extension == ".txt" and not self._is_valid_utf8_text(raw):
            raise ValidationError("TXT 확장자와 실제 파일 형식이 일치하지 않습니다.")
        if extension in (".docx", ".xlsx"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    names = set(archive.namelist())
            except (OSError, zipfile.BadZipFile):
                raise ValidationError(
                    "Office 문서 확장자와 실제 파일 형식이 일치하지 않습니다."
                )

            required_prefix = "word/" if extension == ".docx" else "xl/"
            if "[Content_Types].xml" not in names or not any(
                item.startswith(required_prefix) for item in names
            ):
                raise ValidationError(
                    "Office 문서 확장자와 실제 파일 형식이 일치하지 않습니다."
                )

    @api.model
    def _is_valid_utf8_text(self, raw):
        """Validate TXT content without relying on platform MIME detection."""
        if any(raw.startswith(signature) for signature in self._BINARY_SIGNATURES):
            return False
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return False

        allowed_controls = {"\t", "\n", "\r", "\f"}
        return not any(
            character not in allowed_controls
            and unicodedata.category(character) == "Cc"
            for character in text
        )

    @api.model
    def _helpdesk_check_ticket_access(self, ticket):
        if not ticket:
            raise ValidationError("첨부파일을 연결할 문의를 찾을 수 없습니다.")
        if self.env.uid != SUPERUSER_ID:
            if not (
                self.env.user.has_group("it_helpdesk.group_it_helpdesk_user")
                or self.env.user.has_group("it_helpdesk.group_it_helpdesk_agent")
            ):
                raise AccessError("문의 첨부파일 업로드 권한이 없습니다.")
            ticket.sudo(False).check_access("read")
        if ticket.state == "closed":
            raise AccessError("종료된 문의에는 첨부파일을 추가할 수 없습니다.")

    @api.model
    def _helpdesk_lock_and_check_count(self, ticket, incoming_count, exclude_ids=None):
        self.env.cr.execute(
            "SELECT id FROM it_helpdesk_ticket WHERE id = %s FOR UPDATE",
            [ticket.id],
        )
        domain = [
            ("res_model", "=", self._HELPDESK_MODEL),
            ("res_id", "=", ticket.id),
            ("res_field", "=", False),
        ]
        if exclude_ids:
            domain.append(("id", "not in", list(exclude_ids)))
        existing_count = self.sudo().search_count(domain)
        if existing_count + incoming_count > self._MAX_FILE_COUNT:
            raise ValidationError("문의당 첨부파일은 최대 5개까지 등록할 수 있습니다.")

    def _validate_helpdesk_records(self):
        for attachment in self:
            self._validate_helpdesk_file(attachment.name, attachment.raw or b"")
        return True

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        values_by_ticket = defaultdict(list)
        for vals in vals_list:
            if vals.get("res_model") == self._HELPDESK_MODEL and vals.get("res_id"):
                values_by_ticket[vals["res_id"]].append(vals)

        for ticket_id, ticket_values in values_by_ticket.items():
            ticket = (
                self.env["it.helpdesk.ticket"]
                .sudo()
                .with_context(active_test=False)
                .browse(ticket_id)
                .exists()
            )
            self._helpdesk_check_ticket_access(ticket)
            self._helpdesk_lock_and_check_count(ticket, len(ticket_values))
            for vals in ticket_values:
                if vals.get("type", "binary") != "binary":
                    raise ValidationError("문의에는 파일 첨부만 등록할 수 있습니다.")
                self._validate_helpdesk_file(
                    vals.get("name"),
                    self._helpdesk_raw_from_values(vals),
                )
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        final_by_ticket = defaultdict(lambda: self.env["ir.attachment"])
        touches_content = bool({"raw", "datas", "name", "mimetype"}.intersection(vals))

        for attachment in self:
            final_model = vals.get("res_model", attachment.res_model)
            final_res_id = vals.get("res_id", attachment.res_id)
            if final_model == self._HELPDESK_MODEL and final_res_id:
                final_by_ticket[final_res_id] |= attachment

        for ticket_id, attachments in final_by_ticket.items():
            ticket = (
                self.env["it.helpdesk.ticket"]
                .sudo()
                .with_context(active_test=False)
                .browse(ticket_id)
                .exists()
            )
            is_new_link = attachments.filtered(
                lambda record: record.res_model != self._HELPDESK_MODEL
                or record.res_id != ticket_id
            )
            if is_new_link or touches_content:
                self._helpdesk_check_ticket_access(ticket)
            if is_new_link:
                self._helpdesk_lock_and_check_count(
                    ticket,
                    len(attachments),
                    exclude_ids=attachments.ids,
                )
            if is_new_link or touches_content:
                for attachment in attachments:
                    if vals.get("type", attachment.type) != "binary":
                        raise ValidationError("문의에는 파일 첨부만 등록할 수 있습니다.")
                    self._validate_helpdesk_file(
                        vals.get("name", attachment.name),
                        self._helpdesk_raw_from_values(vals, attachment),
                    )
        return super().write(vals)
