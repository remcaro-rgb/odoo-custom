from odoo import fields, models


class ClubGuestPolicy(models.Model):
    _name = 'club.guest.policy'
    _description = 'Guest Policy'
    _rec_name = 'name'

    name = fields.Char(string='Policy Name', required=True)
    max_guests_per_visit = fields.Integer(
        string='Max Guests per Visit',
        default=4,
        help='Maximum number of guests an affiliate can bring in a single day.',
    )
    max_visits_per_month = fields.Integer(
        string='Max Visits per Month',
        default=8,
        help='Maximum number of guest visits allowed per affiliate per month.',
    )
    requires_advance_registration = fields.Boolean(
        string='Requires Advance Registration',
        default=True,
        help='If enabled, guests must be pre-registered before the visit date.',
    )
    guest_fee = fields.Float(
        string='Guest Fee',
        help='Fee charged per guest per visit.',
    )
