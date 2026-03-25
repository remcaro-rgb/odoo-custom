from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubSailingBooking(models.Model):
    _name = 'club.sailing.booking'
    _description = 'Sailing Booking'
    _order = 'date desc, time_slot'

    affiliate_id = fields.Many2one(
        'club.affiliate', required=True, string='Affiliate',
    )
    boat_id = fields.Many2one(
        'club.sailing.boat', required=True, string='Boat',
    )
    dock_id = fields.Many2one(
        'club.sailing.dock', string='Dock',
    )
    date = fields.Date(string='Date', required=True)
    time_slot = fields.Float(string='Start Time', required=True)
    duration = fields.Float(string='Duration (hours)', default=1.0)
    passenger_count = fields.Integer(string='Passenger Count', default=1)
    status = fields.Selection(
        [
            ('booked', 'Booked'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        default='booked',
        required=True,
        string='Status',
    )
    notes = fields.Text(string='Notes')

    @api.constrains('date', 'time_slot', 'duration', 'boat_id', 'status')
    def _check_boat_not_double_booked(self):
        for rec in self:
            if rec.status == 'cancelled':
                continue
            start = rec.time_slot
            end = rec.time_slot + rec.duration
            domain = [
                ('boat_id', '=', rec.boat_id.id),
                ('date', '=', rec.date),
                ('id', '!=', rec.id),
                ('status', '!=', 'cancelled'),
            ]
            overlapping = self.search(domain)
            for other in overlapping:
                other_start = other.time_slot
                other_end = other.time_slot + other.duration
                if start < other_end and end > other_start:
                    raise ValidationError(
                        _('This boat is already booked for an overlapping time slot on this date.')
                    )

    @api.constrains('passenger_count', 'boat_id')
    def _check_passenger_capacity(self):
        for rec in self:
            if rec.passenger_count > rec.boat_id.capacity:
                raise ValidationError(
                    _('Passenger count (%d) exceeds boat capacity (%d).')
                    % (rec.passenger_count, rec.boat_id.capacity)
                )

    @api.constrains('duration')
    def _check_max_duration(self):
        for rec in self:
            if rec.duration > 8:
                raise ValidationError(
                    _('Booking duration cannot exceed 8 hours.')
                )
