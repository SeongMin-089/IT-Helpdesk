from lxml import etree

from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "it_helpdesk_day8")
class TestHelpdeskDay8(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = new_test_user(
            cls.env,
            login="helpdesk_day8_employee",
            groups="it_helpdesk.group_it_helpdesk_user",
        )
        cls.agent = new_test_user(
            cls.env,
            login="helpdesk_day8_agent",
            groups="it_helpdesk.group_it_helpdesk_agent",
        )
        cls.category = (
            cls.env["it.helpdesk.category"]
            .with_user(cls.agent)
            .create(
                {
                    "name": "Day 8 화면 검증",
                    "code": "DAY8_FORM_LAYOUT",
                }
            )
        )

    def test_description_uses_full_group_width_for_both_roles(self):
        form_view = self.env.ref("it_helpdesk.view_it_helpdesk_ticket_form")
        source_arch = etree.fromstring(form_view.arch_db.encode())
        description_group = source_arch.xpath(
            "//group[@string='장애 상세 내용']"
        )
        self.assertEqual(len(description_group), 1)
        source_fields = description_group[0].xpath(
            "./field[@name='description']"
        )
        self.assertEqual(len(source_fields), 2)
        self.assertTrue(
            all(
                field.get("nolabel") == "1" and field.get("colspan") == "2"
                for field in source_fields
            )
        )
        self.assertEqual(
            {field.get("groups") for field in source_fields},
            {
                "it_helpdesk.group_it_helpdesk_agent",
                "!it_helpdesk.group_it_helpdesk_agent",
            },
        )
        self.assertEqual(
            {
                field.get("groups"): field.get("readonly")
                for field in source_fields
            },
            {
                "it_helpdesk.group_it_helpdesk_agent": (
                    "id != False and (not active or requester_id != uid or "
                    "state not in ('received', 'assigned'))"
                ),
                "!it_helpdesk.group_it_helpdesk_agent": (
                    "id != False and (not active or "
                    "state not in ('received', 'assigned'))"
                ),
            },
        )

        for user in (self.employee, self.agent):
            rendered_view = (
                self.env["it.helpdesk.ticket"]
                .with_user(user)
                .get_view(form_view.id, "form")
            )
            rendered_arch = etree.fromstring(rendered_view["arch"].encode())
            rendered_fields = rendered_arch.xpath(
                "//group[@string='장애 상세 내용']"
                "/field[@name='description']"
            )
            self.assertEqual(len(rendered_fields), 1)
            self.assertEqual(rendered_fields[0].get("colspan"), "2")
            self.assertEqual(rendered_fields[0].get("nolabel"), "1")

    def test_multiline_description_crud_is_unchanged(self):
        description = (
            "사내 네트워크 연결이 간헐적으로 끊기며 긴 문장을 입력해도 "
            "사용 가능한 가로 영역에서 자연스럽게 줄바꿈되어야 합니다.\n"
            "두 번째 줄에는 재현 순서와 오류 메시지를 상세히 기록합니다.\n"
            "세 번째 줄에는 이미 시도한 조치와 발생 시간을 기록합니다."
        )
        ticket = (
            self.env["it.helpdesk.ticket"]
            .with_user(self.employee)
            .create(
                {
                    "name": "Day 8 장애 상세 입력창 검증",
                    "description": description,
                    "category_id": self.category.id,
                    "priority": "normal",
                    "location": "Day 8 테스트 부서",
                }
            )
        )
        self.assertEqual(ticket.description, description)
        self.assertEqual(ticket.state, "received")
        self.assertTrue(ticket.reference.startswith("HD-"))
        self.assertEqual(
            ticket.with_user(self.agent).read(["description"])[0][
                "description"
            ],
            description,
        )

    def test_faq_answer_uses_full_width_and_preserves_paragraphs(self):
        public_form = self.env.ref(
            "it_helpdesk.view_it_helpdesk_faq_public_form"
        )
        management_form = self.env.ref(
            "it_helpdesk.view_it_helpdesk_faq_management_form"
        )
        for form_view, user, expected_readonly in (
            (public_form, self.employee, "1"),
            (management_form, self.agent, None),
        ):
            source_arch = etree.fromstring(form_view.arch_db.encode())
            self.assertIn(
                "o_it_helpdesk_faq_form",
                (source_arch.get("class") or "").split(),
            )
            answer_fields = source_arch.xpath(
                "//group[@string='해결 방법']/field[@name='answer']"
            )
            self.assertEqual(len(answer_fields), 1)
            answer_field = answer_fields[0]
            self.assertEqual(answer_field.get("nolabel"), "1")
            self.assertEqual(answer_field.get("colspan"), "2")
            self.assertEqual(
                answer_field.get("class"),
                "o_it_helpdesk_faq_answer",
            )
            self.assertEqual(answer_field.get("readonly"), expected_readonly)

            rendered_view = (
                self.env["it.helpdesk.faq"]
                .with_user(user)
                .get_view(form_view.id, "form")
            )
            rendered_arch = etree.fromstring(rendered_view["arch"].encode())
            rendered_answer = rendered_arch.xpath(
                "//group[@string='해결 방법']/field[@name='answer']"
            )
            self.assertEqual(len(rendered_answer), 1)
            self.assertEqual(rendered_answer[0].get("colspan"), "2")

        answer = (
            "1. 네트워크 케이블과 무선 연결 상태를 확인합니다.\n\n"
            "2. 설정 화면에서 기존 연결을 삭제한 뒤 다시 연결합니다.\n"
            "3. 공백없는긴문자열도모달너비가좁을때내용이잘리지않아야합니다"
        )
        faq = (
            self.env["it.helpdesk.faq"]
            .with_user(self.agent)
            .create(
                {
                    "name": "Day 8 FAQ 상세 화면 검증",
                    "answer": answer,
                    "category_id": self.category.id,
                    "keywords": "day8 상세 모달",
                }
            )
        )
        faq.with_user(self.agent).action_publish()
        employee_faq = faq.with_user(self.employee)
        self.assertEqual(employee_faq.read(["answer"])[0]["answer"], answer)
        action = self.env["it.helpdesk.faq"].with_user(
            self.employee
        ).open_public_faq(faq.id)
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["res_id"], faq.id)
        self.assertEqual(action["views"], [(public_form.id, "form")])

    def test_sidebar_menu_visibility_reuses_odoo_permissions(self):
        menu_xmlids = {
            "root": "it_helpdesk.menu_it_helpdesk_root",
            "dashboard": "it_helpdesk.menu_it_helpdesk_dashboard",
            "tickets": "it_helpdesk.menu_it_helpdesk_tickets",
            "my_tickets": "it_helpdesk.menu_it_helpdesk_my_tickets",
            "all_tickets": "it_helpdesk.menu_it_helpdesk_ticket_list",
            "my_assigned": "it_helpdesk.menu_it_helpdesk_my_assigned_tickets",
            "unassigned": "it_helpdesk.menu_it_helpdesk_unassigned_tickets",
            "archived": "it_helpdesk.menu_it_helpdesk_archived_tickets",
            "faq_public": "it_helpdesk.menu_it_helpdesk_faq_public",
            "configuration": "it_helpdesk.menu_it_helpdesk_configuration",
            "categories": "it_helpdesk.menu_it_helpdesk_categories",
            "faq_management": "it_helpdesk.menu_it_helpdesk_faq_management",
        }
        menus = {
            key: self.env.ref(xmlid) for key, xmlid in menu_xmlids.items()
        }
        employee_visible = self.env["ir.ui.menu"].with_user(
            self.employee
        )._visible_menu_ids()
        agent_visible = self.env["ir.ui.menu"].with_user(
            self.agent
        )._visible_menu_ids()

        for key in ("root", "dashboard", "tickets", "my_tickets", "faq_public"):
            self.assertIn(menus[key].id, employee_visible)
            self.assertIn(menus[key].id, agent_visible)
        for key in (
            "all_tickets",
            "my_assigned",
            "unassigned",
            "archived",
            "configuration",
            "categories",
            "faq_management",
        ):
            self.assertNotIn(menus[key].id, employee_visible)
            self.assertIn(menus[key].id, agent_visible)

        self.assertEqual(
            menus["my_assigned"].action,
            self.env.ref("it_helpdesk.action_it_helpdesk_my_assigned_tickets"),
        )
        self.assertEqual(
            menus["faq_public"].action,
            self.env.ref("it_helpdesk.action_it_helpdesk_faq_public"),
        )
        self.assertEqual(
            menus["faq_management"].action,
            self.env.ref("it_helpdesk.action_it_helpdesk_faq_management"),
        )

    def test_sidebar_assets_are_registered_in_backend_bundle(self):
        files, _external = self.env["ir.qweb"]._get_asset_content(
            "web.assets_backend"
        )
        asset_paths = {asset["url"] for asset in files}
        for path in (
            "/it_helpdesk/static/src/sidebar/navbar_patch.js",
            "/it_helpdesk/static/src/sidebar/navbar_patch.xml",
            "/it_helpdesk/static/src/sidebar/sidebar.js",
            "/it_helpdesk/static/src/sidebar/sidebar.xml",
            "/it_helpdesk/static/src/sidebar/sidebar.scss",
        ):
            self.assertIn(path, asset_paths)

        asset_nodes = self.env["ir.qweb"]._get_asset_nodes(
            "web.assets_backend",
            css=True,
            js=True,
        )
        self.assertTrue(asset_nodes)
