/** @odoo-module **/

import { patch } from "@web/core/utils/patch"
import { WebClient } from "@web/webclient/webclient"
import { HelpdeskSidebar } from "./sidebar"

patch(WebClient, {
  components: {
    ...WebClient.components,
    HelpdeskSidebar,
  },
})
