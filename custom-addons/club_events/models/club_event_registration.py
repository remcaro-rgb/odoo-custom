from odoo import api, fields, models, _


class ClubEventRegistration(models.Model):
    _inherit = 'event.registration'

    affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Affiliate',
        help='Club affiliate linked to this registration.',
    )
    attendee_type = fields.Selection(
        [
            ('member', 'Member'),
            ('guest', 'Guest'),
            ('public', 'Public'),
        ],
        string='Attendee Type',
        default='public',
    )
    applied_price = fields.Float(
        string='Applied Price',
        digits='Product Price',
        readonly=True,
        help='Price applied at registration time based on attendee type.',
    )
    payment_move_id = fields.Many2one(
        'account.move',
        string='Payment Invoice',
        help='Invoice associated with this registration.',
    )
    payment_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('paid', 'Paid'),
            ('refunded', 'Refunded'),
        ],
        string='Payment Status',
        compute='_compute_payment_status',
        store=True,
    )

    @api.depends('payment_move_id', 'payment_move_id.payment_state')
    def _compute_payment_status(self):
        for registration in self:
            if not registration.payment_move_id:
                registration.payment_status = 'pending'
            elif registration.payment_move_id.payment_state in ('paid', 'in_payment'):
                registration.payment_status = 'paid'
            elif registration.payment_move_id.payment_state == 'reversed':
                registration.payment_status = 'refunded'
            else:
                registration.payment_status = 'pending'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            partner_id = vals.get('partner_id')
            if partner_id:
                affiliate = self.env['club.affiliate'].search([
                    ('partner_id', '=', partner_id),
                    ('membership_status', '=', 'active'),
                ], limit=1)
                if affiliate:
                    vals['attendee_type'] = 'member'
                    vals['affiliate_id'] = affiliate.id
                else:
                    vals.setdefault('attendee_type', 'public')
            else:
                vals.setdefault('attendee_type', 'public')

            # Apply the correct price based on attendee type
            event_id = vals.get('event_id')
            if event_id and 'applied_price' not in vals:
                event = self.env['event.event'].browse(event_id)
                if vals.get('attendee_type') == 'member':
                    vals['applied_price'] = event.member_price
                else:
                    vals['applied_price'] = event.public_price

        return super().create(vals_list)
