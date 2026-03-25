from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_club_affiliate = fields.Boolean(
        compute='_compute_is_club_affiliate',
        store=True,
        help='True if this partner is linked to an active club affiliate.',
    )
    club_affiliate_number = fields.Char(
        compute='_compute_is_club_affiliate',
        store=True,
    )
    club_membership_status = fields.Char(
        compute='_compute_is_club_affiliate',
        store=True,
    )

    @api.depends()  # Recomputed on demand
    def _compute_is_club_affiliate(self):
        Affiliate = self.env['club.affiliate']
        for partner in self:
            aff = Affiliate.search([('partner_id', '=', partner.id)], limit=1)
            partner.is_club_affiliate = bool(aff)
            partner.club_affiliate_number = aff.affiliate_number if aff else ''
            partner.club_membership_status = aff.membership_status if aff else ''

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        fields.extend([
            'is_club_affiliate',
            'club_affiliate_number',
            'club_membership_status',
        ])
        return fields

    @api.model
    def _load_pos_data_domain(self, data):
        domain = super()._load_pos_data_domain(data)
        # Ensure all active club affiliates are available in POS
        affiliate_partner_ids = self.env['club.affiliate'].search([
            ('membership_status', '=', 'active'),
        ]).mapped('partner_id').ids
        if affiliate_partner_ids:
            # domain is typically [('id', 'in', [...])] from the base
            # We need to OR with our affiliate partners
            domain = ['|'] + domain + [('id', 'in', affiliate_partner_ids)]
        return domain
