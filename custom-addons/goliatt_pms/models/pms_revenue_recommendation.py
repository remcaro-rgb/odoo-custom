from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PmsRevenueRecommendation(models.Model):
    _name = 'pms.revenue.recommendation'
    _description = 'Revenue Recommendation'
    _order = 'date, property_id, room_type_id'

    property_id = fields.Many2one(
        'pms.property',
        required=True,
        string='Property',
        ondelete='cascade',
    )
    room_type_id = fields.Many2one(
        'pms.room.type',
        required=True,
        string='Room Type',
        ondelete='cascade',
    )
    date = fields.Date(required=True, string='Date')
    current_rate = fields.Float(string='Current Rate')
    recommended_rate = fields.Float(string='Recommended Rate')
    adjustment_pct = fields.Float(
        compute='_compute_adjustment_pct',
        string='Adjustment %',
        store=True,
    )
    occupancy_forecast = fields.Float(string='Occupancy Forecast (%)')
    demand_level = fields.Selection(
        [
            ('low', 'Low'),
            ('moderate', 'Moderate'),
            ('high', 'High'),
            ('peak', 'Peak'),
            ('critical', 'Critical'),
        ],
        string='Demand Level',
    )
    rules_applied = fields.Text(string='Rules Applied')
    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('accepted', 'Accepted'),
            ('rejected', 'Rejected'),
            ('auto_applied', 'Auto Applied'),
        ],
        default='pending',
        string='Status',
    )
    applied_by = fields.Many2one('res.users', string='Applied By')
    applied_date = fields.Datetime(string='Applied Date')

    _sql_constraints = [
        (
            'unique_recommendation',
            'unique(property_id, room_type_id, date)',
            'Only one recommendation per property, room type, and date.',
        ),
    ]

    @api.depends('current_rate', 'recommended_rate')
    def _compute_adjustment_pct(self):
        for rec in self:
            if rec.current_rate:
                rec.adjustment_pct = (
                    (rec.recommended_rate - rec.current_rate) / rec.current_rate
                ) * 100
            else:
                rec.adjustment_pct = 0.0

    def action_accept(self):
        """Accept recommendation and update the availability rate."""
        for rec in self:
            if rec.status != 'pending':
                raise UserError(_('Only pending recommendations can be accepted.'))
            Availability = self.env['pms.availability']
            avail = Availability.search([
                ('property_id', '=', rec.property_id.id),
                ('room_type_id', '=', rec.room_type_id.id),
                ('date', '=', rec.date),
            ], limit=1)
            old_rate = avail.rate if avail else rec.current_rate
            if avail:
                avail.rate = rec.recommended_rate
            else:
                Availability.create({
                    'property_id': rec.property_id.id,
                    'room_type_id': rec.room_type_id.id,
                    'date': rec.date,
                    'total_inventory': rec.room_type_id.room_count,
                    'rate': rec.recommended_rate,
                })
            # Log the change
            self.env['pms.revenue.log'].create({
                'property_id': rec.property_id.id,
                'room_type_id': rec.room_type_id.id,
                'date': rec.date,
                'old_rate': old_rate,
                'new_rate': rec.recommended_rate,
                'reason': 'RMS recommendation accepted: %s' % (rec.rules_applied or ''),
                'changed_by': self.env.uid,
            })
            rec.write({
                'status': 'accepted',
                'applied_by': self.env.uid,
                'applied_date': fields.Datetime.now(),
            })

    def action_reject(self):
        """Reject the recommendation."""
        for rec in self:
            if rec.status != 'pending':
                raise UserError(_('Only pending recommendations can be rejected.'))
            rec.write({
                'status': 'rejected',
                'applied_by': self.env.uid,
                'applied_date': fields.Datetime.now(),
            })

    def action_accept_all(self):
        """Batch accept all selected pending recommendations."""
        pending = self.filtered(lambda r: r.status == 'pending')
        pending.action_accept()
