from datetime import timedelta

from odoo import api, fields, models, _


class PmsProperty(models.Model):
    _name = 'pms.property'
    _description = 'Hotel / Property'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(
        string='Short Code',
        help='Short unique code, e.g. HTL01',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Address / Contact',
        help='Contact record representing the property address.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Currency',
        store=True,
    )
    property_type = fields.Selection(
        [
            ('hotel', 'Hotel'),
            ('resort', 'Resort'),
            ('hostel', 'Hostel'),
            ('apartment', 'Apartment'),
            ('boutique', 'Boutique'),
            ('villa', 'Villa'),
        ],
        string='Property Type',
        default='hotel',
    )
    star_rating = fields.Selection(
        [
            ('1', '1 Star'),
            ('2', '2 Stars'),
            ('3', '3 Stars'),
            ('4', '4 Stars'),
            ('5', '5 Stars'),
        ],
        string='Star Rating',
    )
    check_in_time = fields.Float(
        string='Check-in Time',
        default=15.0,
        help='Default check-in time (24h float, e.g. 15.0 = 3 PM)',
    )
    check_out_time = fields.Float(
        string='Check-out Time',
        default=11.0,
        help='Default check-out time (24h float, e.g. 11.0 = 11 AM)',
    )
    timezone = fields.Char(
        string='Timezone',
        default='UTC',
    )
    room_type_ids = fields.One2many(
        'pms.room.type',
        'property_id',
        string='Room Types',
    )
    room_ids = fields.One2many(
        'pms.room',
        'property_id',
        string='Rooms',
    )
    total_rooms = fields.Integer(
        compute='_compute_total_rooms',
        string='Total Rooms',
        store=True,
    )
    active = fields.Boolean(default=True)
    image = fields.Binary(string='Image', attachment=True)
    notes = fields.Html(string='Notes')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Property code must be unique.'),
    ]

    @api.depends('room_ids')
    def _compute_total_rooms(self):
        for prop in self:
            prop.total_rooms = len(prop.room_ids)

    # ---- Revenue Management ------------------------------------------------

    def action_run_rms(self):
        """Run the Revenue Management engine for the next 90 days.

        For each date and room type:
        1. Calculate current occupancy forecast
        2. Evaluate all active revenue rules in priority order
        3. Apply multipliers/adjustments to base rate
        4. Generate pms.revenue.recommendation records
        """
        self.ensure_one()
        today = fields.Date.today()
        Recommendation = self.env['pms.revenue.recommendation']
        Rule = self.env['pms.revenue.rule']

        rules = Rule.search([
            ('property_id', '=', self.id),
            ('is_active', '=', True),
        ], order='priority')

        for room_type in self.room_type_ids:
            total_rooms = room_type.room_count
            if not total_rooms:
                continue
            base_rate = room_type.base_rate

            for day_offset in range(90):
                target_date = today + timedelta(days=day_offset)
                target_dow = target_date.weekday()  # 0=Monday
                lead_time = day_offset

                # Calculate occupancy for this date
                reservations = self.env['pms.reservation'].search_count([
                    ('property_id', '=', self.id),
                    ('room_type_id', '=', room_type.id),
                    ('checkin_date', '<=', target_date),
                    ('checkout_date', '>', target_date),
                    ('state', 'not in', ['cancelled', 'no_show']),
                ])
                occupancy = (reservations / total_rooms) * 100

                # Determine demand level
                if occupancy >= 90:
                    demand = 'critical'
                elif occupancy >= 75:
                    demand = 'peak'
                elif occupancy >= 55:
                    demand = 'high'
                elif occupancy >= 35:
                    demand = 'moderate'
                else:
                    demand = 'low'

                # Apply rules
                adjusted_rate = base_rate
                rules_applied = []

                for rule in rules:
                    if rule.room_type_ids and room_type not in rule.room_type_ids:
                        continue

                    fires = False

                    if rule.rule_type == 'occupancy_based':
                        fires = (
                            rule.occupancy_min <= occupancy <= rule.occupancy_max
                        )
                    elif rule.rule_type == 'lead_time':
                        fires = (
                            rule.lead_time_min <= lead_time <= rule.lead_time_max
                        )
                    elif rule.rule_type == 'day_of_week':
                        dow_list = [
                            int(x.strip())
                            for x in (rule.day_of_week_ids or '').split(',')
                            if x.strip()
                        ]
                        fires = target_dow in dow_list
                    elif rule.rule_type == 'season':
                        fires = (
                            rule.date_from
                            and rule.date_to
                            and rule.date_from <= target_date <= rule.date_to
                        )
                    elif rule.rule_type == 'demand_surge':
                        fires = demand in ('peak', 'critical')
                    elif rule.rule_type == 'last_minute':
                        fires = (lead_time <= 2 and occupancy < 50)
                    elif rule.rule_type == 'competitor':
                        fires = True  # always applies if active

                    if not fires:
                        continue

                    if rule.action_type == 'multiplier':
                        adjusted_rate *= rule.multiplier
                    elif rule.action_type == 'fixed_adjustment':
                        adjusted_rate += rule.fixed_amount
                    elif rule.action_type == 'set_min_rate':
                        adjusted_rate = max(adjusted_rate, rule.min_rate)
                    elif rule.action_type == 'set_max_rate':
                        adjusted_rate = min(adjusted_rate, rule.max_rate)

                    rules_applied.append(rule.name)

                adjusted_rate = round(adjusted_rate, -3)  # round to nearest 1000

                # Create or update recommendation
                existing = Recommendation.search([
                    ('property_id', '=', self.id),
                    ('room_type_id', '=', room_type.id),
                    ('date', '=', target_date),
                    ('status', '=', 'pending'),
                ], limit=1)

                vals = {
                    'property_id': self.id,
                    'room_type_id': room_type.id,
                    'date': target_date,
                    'current_rate': base_rate,
                    'recommended_rate': adjusted_rate,
                    'occupancy_forecast': occupancy,
                    'demand_level': demand,
                    'rules_applied': (
                        ', '.join(rules_applied) if rules_applied
                        else 'No rules fired'
                    ),
                    'status': 'pending',
                }

                if existing:
                    existing.write(vals)
                else:
                    Recommendation.create(vals)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RMS Engine'),
                'message': _(
                    'Revenue recommendations generated for the next 90 days.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }
