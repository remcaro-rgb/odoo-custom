/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    /**
     * Override addNewPaymentLine to validate Cargo a Socio
     * requires an affiliate customer.
     */
    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.is_cargo_socio) {
            const order = this.pos.get_order();
            const partner = order.get_partner();
            if (!partner || !partner.is_club_affiliate) {
                this.notification.add(
                    this.env._t("Cargo a Socio requires an active club affiliate as customer."),
                    { type: "danger" }
                );
                return;
            }
            if (partner.club_membership_status !== "active") {
                this.notification.add(
                    this.env._t("The selected affiliate does not have an active membership."),
                    { type: "danger" }
                );
                return;
            }
        }
        return super.addNewPaymentLine(paymentMethod);
    },
});
