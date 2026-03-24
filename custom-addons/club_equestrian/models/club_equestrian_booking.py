from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubEquestrianBooking(models.Model):
    _name = 'club.equestrian.booking'
    _description = 'Equestrian Arena Booking'
    _rec_name = 'arena_id'
    _order = 'date desc, time_slot asc'

    arena_id = fields.Many2one(
        'club.arena',
        string='Arena',
        required=True,
    )
    affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Affiliate',
        required=True,
    )
    horse_id = fields.Many2one(
        'club.horse',
        string='Horse',
        required=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
    )
    time_slot = fields.Float(string='Start Time', required=True)
    duration = fields.Float(string='Duration (hours)', required=True, default=1.0)
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

    @api.constrains('duration')
    def _check_duration(self):
        for booking in self:
            if booking.duration <= 0:
                raise ValidationError(
                    _("Duration must be greater than zero.")
                )
            if booking.duration > 2:
                raise ValidationError(
                    _("Maximum booking duration is 2 hours.")
                )

    @api.constrains('horse_id', 'affiliate_id')
    def _check_horse_owner(self):
        for booking in self:
            if booking.horse_id.owner_id != booking.affiliate_id:
                raise ValidationError(
                    _("The horse \"%(horse)s\" does not belong to affiliate \"%(affiliate)s\".",
                      horse=booking.horse_id.name,
                      affiliate=booking.affiliate_id.name)
                )

    @api.constrains('arena_id', 'date', 'time_slot', 'duration')
    def _check_no_overlap(self):
        for booking in self:
            if booking.status == 'cancelled':
                continue
            domain = [
                ('id', '!=', booking.id),
                ('arena_id', '=', booking.arena_id.id),
                ('date', '=', booking.date),
                ('status', '!=', 'cancelled'),
                ('time_slot', '<', booking.time_slot + booking.duration),
            ]
            overlapping = self.search(domain)
            for other in overlapping:
                if booking.time_slot < other.time_slot + other.duration:
                    raise ValidationError(
                        _("This booking overlaps with an existing booking "
                          "in arena \"%(arena)s\" on %(date)s.",
                          arena=booking.arena_id.name,
                          date=booking.date)
                    )
