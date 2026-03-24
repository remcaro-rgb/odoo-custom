from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubGolfTeeTime(models.Model):
    _name = 'club.golf.tee.time'
    _description = 'Golf Tee Time'
    _order = 'date desc, time_slot'

    date = fields.Date(string='Date', required=True)
    time_slot = fields.Float(string='Start Time', required=True)
    course_id = fields.Many2one(
        'club.golf.course', required=True, string='Course',
    )
    affiliate_ids = fields.Many2many(
        'club.affiliate', 'club_golf_tee_time_affiliate_rel',
        'tee_time_id', 'affiliate_id',
        string='Affiliates',
    )
    guest_count = fields.Integer(string='Guest Count', default=0)
    caddie_id = fields.Many2one(
        'club.golf.caddie', string='Caddie',
    )
    cart_id = fields.Many2one(
        'club.golf.cart', string='Cart',
    )
    bag_ids = fields.Many2many(
        'club.golf.bag', 'club_golf_tee_time_bag_rel',
        'tee_time_id', 'bag_id',
        string='Bags',
    )
    status = fields.Selection(
        [
            ('available', 'Available'),
            ('booked', 'Booked'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        default='available',
        required=True,
        string='Status',
    )

    @api.constrains('date', 'time_slot', 'course_id')
    def _check_unique_tee_time(self):
        for rec in self:
            domain = [
                ('date', '=', rec.date),
                ('time_slot', '=', rec.time_slot),
                ('course_id', '=', rec.course_id.id),
                ('id', '!=', rec.id),
                ('status', 'not in', ['cancelled']),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _('A tee time already exists for this course, date and time slot.')
                )

    @api.constrains('date', 'time_slot', 'caddie_id')
    def _check_caddie_not_double_booked(self):
        for rec in self:
            if not rec.caddie_id:
                continue
            domain = [
                ('date', '=', rec.date),
                ('time_slot', '=', rec.time_slot),
                ('caddie_id', '=', rec.caddie_id.id),
                ('id', '!=', rec.id),
                ('status', 'not in', ['cancelled']),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _('This caddie is already booked for another tee time at the same date and time.')
                )

    @api.constrains('date', 'time_slot', 'cart_id')
    def _check_cart_not_double_assigned(self):
        for rec in self:
            if not rec.cart_id:
                continue
            domain = [
                ('date', '=', rec.date),
                ('time_slot', '=', rec.time_slot),
                ('cart_id', '=', rec.cart_id.id),
                ('id', '!=', rec.id),
                ('status', 'not in', ['cancelled']),
            ]
            if rec.cart_id.cart_type == 'rental':
                # Rental carts cannot be double-assigned at all
                if self.search_count(domain):
                    raise ValidationError(
                        _('This rental cart is already assigned to another tee time at the same date and time.')
                    )
            else:
                # Owned carts only block if assigned to another affiliate
                conflicts = self.search(domain)
                for conflict in conflicts:
                    if conflict.affiliate_ids != rec.affiliate_ids:
                        raise ValidationError(
                            _('This owned cart is already assigned to another affiliate at the same date and time.')
                        )

    @api.constrains('affiliate_ids')
    def _check_max_affiliates(self):
        for rec in self:
            if len(rec.affiliate_ids) > 4:
                raise ValidationError(
                    _('A tee time can have a maximum of 4 affiliates.')
                )
