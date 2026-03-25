from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubGuestVisit(models.Model):
    _name = 'club.guest.visit'
    _description = 'Guest Visit'
    _rec_name = 'name'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Visit Number', readonly=True, copy=False, index=True,
        default=lambda self: _('New'),
    )
    affiliate_id = fields.Many2one(
        'club.affiliate', string='Host Affiliate', required=True,
        ondelete='restrict',
    )
    guest_id = fields.Many2one(
        'club.guest', string='Guest', required=True,
        ondelete='restrict',
    )
    date = fields.Date(string='Visit Date', required=True, default=fields.Date.context_today)
    check_in_time = fields.Float(string='Check-In Time')
    check_out_time = fields.Float(string='Check-Out Time')
    areas_accessed = fields.Selection(
        [
            ('pool', 'Pool'),
            ('golf', 'Golf'),
            ('tennis', 'Tennis'),
            ('restaurant', 'Restaurant'),
            ('social_area', 'Social Area'),
            ('gym', 'Gym'),
            ('general', 'General'),
        ],
        string='Area Accessed',
    )
    status = fields.Selection(
        [
            ('registered', 'Registered'),
            ('checked_in', 'Checked In'),
            ('checked_out', 'Checked Out'),
            ('cancelled', 'Cancelled'),
            ('no_show', 'No Show'),
        ],
        string='Status',
        default='registered',
        required=True,
    )
    policy_id = fields.Many2one(
        'club.guest.policy', string='Guest Policy',
    )
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.guest.visit'
                ) or _('New')
        return super().create(vals_list)

    @api.constrains('affiliate_id', 'date', 'policy_id')
    def _check_max_guests_per_visit(self):
        """Ensure the affiliate does not exceed the max guests per visit (per day)."""
        for visit in self:
            if visit.status == 'cancelled':
                continue
            policy = visit.policy_id
            if not policy:
                continue
            same_day_count = self.search_count([
                ('affiliate_id', '=', visit.affiliate_id.id),
                ('date', '=', visit.date),
                ('status', '!=', 'cancelled'),
            ])
            if same_day_count > policy.max_guests_per_visit:
                raise ValidationError(
                    _('Affiliate "%(affiliate)s" exceeds the maximum of %(max)d guests '
                      'per visit on %(date)s.',
                      affiliate=visit.affiliate_id.name,
                      max=policy.max_guests_per_visit,
                      date=visit.date)
                )

    @api.constrains('affiliate_id', 'date', 'policy_id')
    def _check_max_visits_per_month(self):
        """Ensure the affiliate does not exceed the max visits per month."""
        for visit in self:
            if visit.status == 'cancelled':
                continue
            policy = visit.policy_id
            if not policy:
                continue
            first_of_month = visit.date.replace(day=1)
            if visit.date.month == 12:
                last_of_month = visit.date.replace(year=visit.date.year + 1, month=1, day=1)
            else:
                last_of_month = visit.date.replace(month=visit.date.month + 1, day=1)
            month_count = self.search_count([
                ('affiliate_id', '=', visit.affiliate_id.id),
                ('date', '>=', first_of_month),
                ('date', '<', last_of_month),
                ('status', '!=', 'cancelled'),
            ])
            if month_count > policy.max_visits_per_month:
                raise ValidationError(
                    _('Affiliate "%(affiliate)s" exceeds the maximum of %(max)d guest '
                      'visits per month.',
                      affiliate=visit.affiliate_id.name,
                      max=policy.max_visits_per_month)
                )

    def action_check_in(self):
        """Set check-in time to now and mark as checked in."""
        now = fields.Datetime.now()
        hour_float = now.hour + now.minute / 60.0
        for visit in self:
            visit.write({
                'check_in_time': hour_float,
                'status': 'checked_in',
            })

    def action_check_out(self):
        """Set check-out time to now and mark as checked out."""
        now = fields.Datetime.now()
        hour_float = now.hour + now.minute / 60.0
        for visit in self:
            visit.write({
                'check_out_time': hour_float,
                'status': 'checked_out',
            })
