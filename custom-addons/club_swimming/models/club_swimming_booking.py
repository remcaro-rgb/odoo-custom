from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubSwimmingBooking(models.Model):
    _name = 'club.swimming.booking'
    _description = 'Swimming Booking'
    _order = 'date desc, time_slot'

    affiliate_id = fields.Many2one(
        'club.affiliate', required=True, string='Affiliate',
    )
    pool_id = fields.Many2one(
        'club.swimming.pool', required=True, string='Pool',
    )
    lane_id = fields.Many2one(
        'club.swimming.lane', string='Lane',
        domain="[('pool_id', '=', pool_id)]",
    )
    date = fields.Date(string='Date', required=True)
    time_slot = fields.Float(string='Start Time', required=True)
    duration = fields.Float(string='Duration (hours)', required=True, default=1.0)
    guest_count = fields.Integer(string='Guest Count', default=0)
    status = fields.Selection(
        [
            ('booked', 'Booked'),
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        required=True,
        default='booked',
    )

    @api.constrains('duration')
    def _check_duration_max(self):
        for rec in self:
            if rec.duration > 3.0:
                raise ValidationError(
                    _('Booking duration cannot exceed 3 hours.')
                )

    @api.constrains('pool_id')
    def _check_pool_not_under_maintenance(self):
        for rec in self:
            if rec.pool_id.under_maintenance:
                raise ValidationError(
                    _('Cannot book a pool that is currently under maintenance.')
                )

    @api.constrains('lane_id', 'date', 'time_slot', 'duration')
    def _check_lane_not_double_booked(self):
        for rec in self:
            if not rec.lane_id:
                continue
            end_time = rec.time_slot + rec.duration
            domain = [
                ('lane_id', '=', rec.lane_id.id),
                ('date', '=', rec.date),
                ('id', '!=', rec.id),
                ('status', 'not in', ['cancelled']),
            ]
            overlapping = self.search(domain)
            for other in overlapping:
                other_end = other.time_slot + other.duration
                if rec.time_slot < other_end and end_time > other.time_slot:
                    raise ValidationError(
                        _('This lane is already booked for an overlapping time slot.')
                    )
