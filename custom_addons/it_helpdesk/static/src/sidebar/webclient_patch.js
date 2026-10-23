/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { HelpdeskSidebar } from "./sidebar";

// Render the sidebar next to ActionContainer, not inside MainComponentsContainer.
patch(WebClient, {
    components: {
        ...WebClient.components,
        HelpdeskSidebar,
    },
});
