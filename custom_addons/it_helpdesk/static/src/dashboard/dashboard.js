/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";


export class HelpdeskDashboard extends Component {
    static template = "it_helpdesk.Dashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            error: false,
            data: null,
        });
        onWillStart(() => this.loadDashboard());
    }

    get isAgent() {
        return this.state.data?.role === "agent";
    }

    get title() {
        return this.isAgent ? _t("IT 담당자 대시보드") : _t("내 문의 대시보드");
    }

    get subtitle() {
        return this.isAgent
            ? _t("전체 활성 문의의 처리 현황을 확인하세요.")
            : _t("내가 등록한 활성 문의의 진행 상황을 확인하세요.");
    }

    async loadDashboard() {
        this.state.loading = true;
        this.state.error = false;
        try {
            this.state.data = await this.orm.call(
                "it.helpdesk.ticket",
                "get_dashboard_data",
                []
            );
        } catch (error) {
            this.state.error = _t("대시보드 데이터를 불러오지 못했습니다.");
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    get listActionXmlId() {
        return this.isAgent
            ? "it_helpdesk.action_it_helpdesk_ticket"
            : "it_helpdesk.action_it_helpdesk_my_tickets";
    }

    async openTickets(domain = []) {
        const loadedAction = await this.actionService.loadAction(this.listActionXmlId);
        const action = { ...loadedAction };
        action.domain = [
            ...(Array.isArray(loadedAction.domain) ? loadedAction.domain : []),
            ["active", "=", true],
            ...domain,
        ];
        return this.actionService.doAction(action);
    }

    async openTicket(ticketId) {
        const loadedAction = await this.actionService.loadAction(this.listActionXmlId);
        const action = { ...loadedAction };
        action.views = [[false, "form"]];
        action.res_id = ticketId;
        return this.actionService.doAction(action);
    }

    async createTicket() {
        const loadedAction = await this.actionService.loadAction(
            "it_helpdesk.action_it_helpdesk_my_tickets"
        );
        const action = { ...loadedAction };
        action.views = [[false, "form"]];
        action.res_id = false;
        return this.actionService.doAction(action);
    }

    openUnassignedTickets() {
        return this.actionService.doAction(
            "it_helpdesk.action_it_helpdesk_unassigned_tickets"
        );
    }

    async openPublicFaq(faqId) {
        const action = await this.orm.call(
            "it.helpdesk.faq",
            "open_public_faq",
            [faqId]
        );
        return this.actionService.doAction(action);
    }

    openPublicFaqList() {
        return this.actionService.doAction(
            "it_helpdesk.action_it_helpdesk_faq_public"
        );
    }

    openFaqManagement() {
        return this.actionService.doAction(
            "it_helpdesk.action_it_helpdesk_faq_management"
        );
    }

    async openFaqKpi(kpi) {
        const loadedAction = await this.actionService.loadAction(
            "it_helpdesk.action_it_helpdesk_faq_management"
        );
        const action = { ...loadedAction };
        action.domain = kpi.domain;
        action.context = {
            ...(loadedAction.context || {}),
            ...kpi.context,
        };
        return this.actionService.doAction(action);
    }

    faqIcon(key) {
        return {
            total: "fa-files-o",
            published: "fa-eye",
            private: "fa-eye-slash",
            archived: "fa-archive",
        }[key] || "fa-question-circle";
    }

    formatCreatedAt(value) {
        return value ? formatDateTime(deserializeDateTime(value)) : "";
    }

    distributionPercent(item, total) {
        return total ? Math.round((item.count / total) * 100) : 0;
    }

    priorityClass(priority) {
        return `o_it_helpdesk_priority_${priority}`;
    }
}

registry.category("actions").add("it_helpdesk.dashboard", HelpdeskDashboard);
