/** @odoo-module **/

import { useBus, useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";


const HELPDESK_APP_XMLID = "it_helpdesk.menu_it_helpdesk_root";

export class HelpdeskSidebar extends Component {
    static template = "it_helpdesk.Sidebar";
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.state = useState({
            isHelpdeskApp: false,
            isMobileOpen: false,
            activeMenuId: false,
            expanded: {
                "it_helpdesk.menu_it_helpdesk_tickets": true,
                "it_helpdesk.menu_it_helpdesk_configuration": true,
            },
        });

        useBus(this.env.bus, "MENUS:APP-CHANGED", () => this.syncApp());
        useBus(this.env.bus, "ACTION_MANAGER:UPDATE", () => {
            this.syncActiveMenu();
        });
        onMounted(() => this.syncApp());
        onWillUnmount(() => this.clearBodyClasses());
    }

    get currentApp() {
        return this.menuService.getCurrentApp();
    }

    get sections() {
        if (!this.state.isHelpdeskApp || !this.currentApp) {
            return [];
        }
        return this.menuService.getMenuAsTree(this.currentApp.id).childrenTree;
    }

    syncApp() {
        this.state.isHelpdeskApp =
            this.currentApp?.xmlid === HELPDESK_APP_XMLID;
        if (!this.state.isHelpdeskApp) {
            this.state.isMobileOpen = false;
            this.state.activeMenuId = false;
        } else {
            this.syncActiveMenu();
        }
        this.syncBodyClasses();
    }

    syncActiveMenu() {
        if (!this.state.isHelpdeskApp) {
            return;
        }
        const actionId = this.actionService.currentController?.action?.id;
        const activeMenu = this.flattenMenus(this.sections).find(
            (menu) =>
                menu.actionID &&
                actionId &&
                String(menu.actionID) === String(actionId)
        );
        if (activeMenu) {
            this.state.activeMenuId = activeMenu.id;
            for (const section of this.sections) {
                if (this.hasActiveDescendant(section)) {
                    this.state.expanded[section.xmlid] = true;
                }
            }
        }
    }

    flattenMenus(menus) {
        return menus.flatMap((menu) => [
            menu,
            ...this.flattenMenus(menu.childrenTree || []),
        ]);
    }

    hasActiveDescendant(menu) {
        return (menu.childrenTree || []).some(
            (child) =>
                child.id === this.state.activeMenuId ||
                this.hasActiveDescendant(child)
        );
    }

    isActive(menu) {
        return (
            menu.id === this.state.activeMenuId ||
            this.hasActiveDescendant(menu)
        );
    }

    isExpanded(menu) {
        return Boolean(this.state.expanded[menu.xmlid]);
    }

    toggleGroup(menu) {
        this.state.expanded[menu.xmlid] = !this.isExpanded(menu);
    }

    toggleMobile() {
        this.state.isMobileOpen = !this.state.isMobileOpen;
    }

    closeMobile() {
        this.state.isMobileOpen = false;
    }

    async selectMenu(menu) {
        await this.menuService.selectMenu(menu);
        this.closeMobile();
        this.syncActiveMenu();
    }

    getMenuHref(menu) {
        return `/odoo/${menu.actionPath || "action-" + menu.actionID}`;
    }

    menuIcon(menu) {
        const icons = {
            "it_helpdesk.menu_it_helpdesk_dashboard": "fa-dashboard",
            "it_helpdesk.menu_it_helpdesk_tickets": "fa-ticket",
            "it_helpdesk.menu_it_helpdesk_my_tickets": "fa-user",
            "it_helpdesk.menu_it_helpdesk_ticket_list": "fa-list-alt",
            "it_helpdesk.menu_it_helpdesk_my_assigned_tickets": "fa-user-circle-o",
            "it_helpdesk.menu_it_helpdesk_unassigned_tickets": "fa-user-times",
            "it_helpdesk.menu_it_helpdesk_archived_tickets": "fa-archive",
            "it_helpdesk.menu_it_helpdesk_faq_public": "fa-question-circle",
            "it_helpdesk.menu_it_helpdesk_configuration": "fa-cog",
            "it_helpdesk.menu_it_helpdesk_categories": "fa-tags",
            "it_helpdesk.menu_it_helpdesk_faq_management": "fa-book",
        };
        return icons[menu.xmlid] || "fa-circle-o";
    }

    syncBodyClasses() {
        document.body.classList.toggle(
            "o_it_helpdesk_sidebar_active",
            this.state.isHelpdeskApp
        );
    }

    clearBodyClasses() {
        document.body.classList.remove("o_it_helpdesk_sidebar_active");
    }
}

