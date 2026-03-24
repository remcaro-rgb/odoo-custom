from odoo import fields, models


class ClubTennisCaddie(models.Model):
    _name = 'club.tennis.caddie'
    _inherit = 'club.caddie.mixin'
    _description = 'Tennis Caddie'

    availability_ids = fields.One2many(
        'club.tennis.caddie.availability', 'caddie_id',
        string='Availability',
    )
    booking_ids = fields.One2many(
        'club.tennis.booking', 'caddie_id', string='Bookings',
    )


class ClubTennisCaddieAvailability(models.Model):
    _name = 'club.tennis.caddie.availability'
    _description = 'Tennis Caddie Availability'

    caddie_id = fields.Many2one(
        'club.tennis.caddie', required=True, ondelete='cascade',
        string='Caddie',
    )
    day_of_week = fields.Selection(
        [
            ('0', 'Monday'),
            ('1', 'Tuesday'),
            ('2', 'Wednesday'),
            ('3', 'Thursday'),
            ('4', 'Friday'),
            ('5', 'Saturday'),
            ('6', 'Sunday'),
        ],
        string='Day of Week',
        required=True,
    )
    time_from = fields.Float(string='Available From')
    time_to = fields.Float(string='Available Until')
