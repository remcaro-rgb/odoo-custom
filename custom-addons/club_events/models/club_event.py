from odoo import _, api, fields, models


class ClubEvent(models.Model):
    _inherit = 'event.event'

    event_scope = fields.Selection(
        [
            ('internal', 'Internal'),
            ('external', 'External'),
        ],
        string='Event Scope',
        default='external',
    )
    sport_category = fields.Selection(
        [
            ('golf', 'Golf'),
            ('equestrian', 'Equestrian'),
            ('tennis', 'Tennis'),
            ('social', 'Social'),
            ('general', 'General'),
        ],
        string='Sport Category',
        default='general',
    )
    member_only = fields.Boolean(
        string='Members Only',
        default=False,
        help='Restrict visibility to active affiliates only.',
    )
    member_price = fields.Float(
        string='Member Price',
        digits='Product Price',
        default=0.0,
        help='Ticket price for club affiliates.',
    )
    public_price = fields.Float(
        string='Public Price',
        digits='Product Price',
        default=0.0,
        help='Ticket price for external attendees.',
    )
