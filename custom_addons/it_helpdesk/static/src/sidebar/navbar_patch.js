/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";


const HELPDESK_APP_XMLID = "it_helpdesk.menu_it_helpdesk_root";

patch(NavBar.prototype, {
    get isItHelpdeskApp() {
        return this.currentApp?.xmlid === HELPDESK_APP_XMLID;
    },
});
