from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubTennisBooking(models.Model):
    _name = 'club.tennis.booking'
    _description = 'Tennis Court Booking'
    _rec_name = 'display_name'

    court_id = fields.Many2one(
        'club.tennis.court', required=True, string='Court',
        ondelete='restrict',
    )
    affiliate_ids = fields.Many2many(
        'club.affiliate', string='Players',
    )
    date = fields.Date(string='Booking Date', required=True)
    time_slot = fields.Float(string='Start Time', required=True)
    duration = fields.Float(string='Duration (hours)', required=True, default=1.0)
    caddie_id = fields.Many2one(
        'club.tennis.caddie', string='Caddie',
        ondelete='set null',
    )
    status = fields.Selection(
        [
            ('booked', 'Booked'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='booked',
        required=True,
    )
    match_ids = fields.One2many(
        'club.tennis.match', 'booking_id', string='Matches',
    )

    @api.depends('court_id', 'date', 'time_slot')
    def _compute_display_name(self):
        for rec in self:
            court_name = rec.court_id.name or _('No Court')
            date_str = rec.date or _('No Date')
            hours = int(rec.time_slot)
            minutes = int((rec.time_slot - hours) * 60)
            rec.display_name = "%s - %s %02d:%02d" % (
                court_name, date_str, hours, minutes,
            )

    @api.constrains('duration')
    def _check_duration(self):
        for rec in self:
            if rec.duration not in (1.0, 2.0):
                raise ValidationError(
                    _('Booking duration must be 1 or 2 hours.')
                )

    @api.constrains('affiliate_ids')
    def _check_max_affiliates(self):
        for rec in self:
            if len(rec.affiliate_ids) > 4:
                raise ValidationError(
                    _('A tennis booking allows a maximum of 4 players.')
                )

    @api.constrains('court_id', 'date', 'time_slot', 'duration')
    def _check_court_overlap(self):
        for rec in self:
            if rec.status == 'cancelled':
                continue
            domain = [
                ('id', '!=', rec.id),
                ('court_id', '=', rec.court_id.id),
                ('date', '=', rec.date),
                ('status', '!=', 'cancelled'),
            ]
            overlapping = self.search(domain)
            start = rec.time_slot
            end = rec.time_slot + rec.duration
            for other in overlapping:
                other_start = other.time_slot
                other_end = other.time_slot + other.duration
                if start < other_end and end > other_start:
                    raise ValidationError(
                        _('Court "%s" already has a booking that overlaps '
                          'with the selected time on %s.')
                        % (rec.court_id.name, rec.date)
                    )

    @api.constrains('date', 'time_slot', 'caddie_id')
    def _check_caddie_overlap(self):
        for rec in self:
            if rec.status == 'cancelled' or not rec.caddie_id:
                continue
            domain = [
                ('id', '!=', rec.id),
                ('caddie_id', '=', rec.caddie_id.id),
                ('date', '=', rec.date),
                ('status', '!=', 'cancelled'),
            ]
            overlapping = self.search(domain)
            start = rec.time_slot
            end = rec.time_slot + rec.duration
            for other in overlapping:
                other_start = other.time_slot
                other_end = other.time_slot + other.duration
                if start < other_end and end > other_start:
                    raise ValidationError(
                        _('Caddie "%s" is already assigned to another '
                          'booking at that time on %s.')
                        % (rec.caddie_id.partner_id.name, rec.date)
                    )
