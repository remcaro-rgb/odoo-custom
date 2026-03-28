from odoo import api, fields, models, _


class PmsRevenueRule(models.Model):
    _name = 'pms.revenue.rule'
    _description = 'Revenue Management Rule'
    _order = 'priority, name'

    name = fields.Char(required=True, string='Rule Name')
    property_id = fields.Many2one(
        'pms.property',
        required=True,
        string='Property',
        ondelete='cascade',
    )
    rule_type = fields.Selection(
        [
            ('occupancy_based', 'Occupancy Based'),
            ('lead_time', 'Lead Time'),
            ('day_of_week', 'Day of Week'),
            ('season', 'Seasonal'),
            ('demand_surge', 'Demand Surge'),
            ('last_minute', 'Last Minute'),
            ('competitor', 'Competitor'),
        ],
        required=True,
        string='Rule Type',
    )
    room_type_ids = fields.Many2many(
        'pms.room.type',
        'pms_revenue_rule_room_type_rel',
        'rule_id',
        'room_type_id',
        string='Room Types',
        help='Applies to these room types. Leave empty to apply to all.',
    )
    priority = fields.Integer(
        string='Priority',
        default=10,
        help='Lower number = runs first.',
    )
    is_active = fields.Boolean(string='Active', default=True)

    # -- Conditions ----------------------------------------------------------
    occupancy_min = fields.Float(
        string='Occupancy Min (%)',
        help='Rule fires when occupancy >= this value.',
    )
    occupancy_max = fields.Float(
        string='Occupancy Max (%)',
        default=100,
        help='Rule fires when occupancy <= this value.',
    )
    lead_time_min = fields.Integer(
        string='Lead Time Min (days)',
        help='Minimum days before arrival.',
    )
    lead_time_max = fields.Integer(
        string='Lead Time Max (days)',
        default=365,
        help='Maximum days before arrival.',
    )
    day_of_week_ids = fields.Char(
        string='Days of Week',
        help='Comma-separated day numbers: 0=Mon, 1=Tue, ..., 6=Sun. E.g. "4,5" for Fri/Sat.',
    )
    date_from = fields.Date(string='Season Start')
    date_to = fields.Date(string='Season End')

    # -- Actions -------------------------------------------------------------
    action_type = fields.Selection(
        [
            ('multiplier', 'Multiplier'),
            ('fixed_adjustment', 'Fixed Adjustment'),
            ('set_min_rate', 'Set Minimum Rate'),
            ('set_max_rate', 'Set Maximum Rate'),
            ('close_rate', 'Close Rate'),
            ('open_rate', 'Open Rate'),
        ],
        required=True,
        string='Action Type',
    )
    multiplier = fields.Float(
        string='Multiplier',
        default=1.0,
        help='E.g. 1.20 = +20%, 0.85 = -15%.',
    )
    fixed_amount = fields.Float(
        string='Fixed Amount',
        help='Amount to add (or subtract if negative).',
    )
    min_rate = fields.Float(string='Minimum Rate (floor)')
    max_rate = fields.Float(string='Maximum Rate (ceiling)')
    notes = fields.Text(string='Notes')
