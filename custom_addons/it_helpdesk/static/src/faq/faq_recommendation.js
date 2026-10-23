/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { onWillUnmount, useEffect, useState } from "@odoo/owl";


export class HelpdeskFaqRecommendationField extends CharField {
    static template = "it_helpdesk.FaqRecommendationField";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.recommendationState = useState({
            loading: false,
            searched: false,
            error: false,
            items: [],
        });
        this.searchTimer = null;
        this.requestSequence = 0;
        this.isDestroyed = false;

        useEffect(
            () => {
                this.scheduleSearch();
                return () => this.clearSearchTimer();
            },
            () => [
                this.props.record.data[this.props.name] || "",
                this.categoryId,
                this.props.record.isNew,
                this.props.readonly,
            ]
        );
        onWillUnmount(() => {
            this.isDestroyed = true;
            this.requestSequence += 1;
            this.clearSearchTimer();
        });
    }

    get categoryId() {
        const category = this.props.record.data.category_id;
        if (!category) {
            return false;
        }
        if (Array.isArray(category)) {
            return category[0] || false;
        }
        return category.id || category.resId || false;
    }

    get shouldShowRecommendations() {
        return this.props.record.isNew && !this.props.readonly;
    }

    clearSearchTimer() {
        if (this.searchTimer) {
            clearTimeout(this.searchTimer);
            this.searchTimer = null;
        }
    }

    scheduleSearch() {
        this.clearSearchTimer();
        const query = (this.props.record.data[this.props.name] || "").trim();
        const sequence = ++this.requestSequence;
        this.recommendationState.loading = false;
        this.recommendationState.error = false;
        this.recommendationState.searched = false;
        this.recommendationState.items = [];

        if (!this.shouldShowRecommendations || query.length < 2) {
            return;
        }
        this.searchTimer = setTimeout(
            () => this.loadRecommendations(query, this.categoryId, sequence),
            400
        );
    }

    async loadRecommendations(query, categoryId, sequence) {
        this.searchTimer = null;
        if (this.isDestroyed || sequence !== this.requestSequence) {
            return;
        }
        this.recommendationState.loading = true;
        try {
            const items = await this.orm.call(
                "it.helpdesk.faq",
                "search_recommendations",
                [query, categoryId || false]
            );
            if (this.isDestroyed || sequence !== this.requestSequence) {
                return;
            }
            this.recommendationState.items = items;
            this.recommendationState.searched = true;
        } catch {
            if (!this.isDestroyed && sequence === this.requestSequence) {
                this.recommendationState.error = true;
                this.recommendationState.searched = true;
            }
        } finally {
            if (!this.isDestroyed && sequence === this.requestSequence) {
                this.recommendationState.loading = false;
            }
        }
    }

    async openFaq(faq) {
        try {
            const action = await this.orm.call(
                "it.helpdesk.faq",
                "open_public_faq",
                [faq.id]
            );
            await this.actionService.doAction(action);
        } catch {
            this.recommendationState.error = true;
        }
    }
}

export const helpdeskFaqRecommendationField = {
    ...charField,
    component: HelpdeskFaqRecommendationField,
};

registry
    .category("fields")
    .add("it_helpdesk_faq_recommendation", helpdeskFaqRecommendationField);
