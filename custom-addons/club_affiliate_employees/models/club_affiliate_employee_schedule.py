from odoo import fields, models


class ClubAffiliateEmployeeSchedule(models.Model):
    _name = 'club.affiliate.employee.schedule'
    _description = 'Club Affiliate Employee Schedule'
    _order = 'day_of_week, time_from'

    employee_id = fields.Many2one(
        'club.affiliate.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
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
    time_from = fields.Float(string='From')
    time_to = fields.Float(string='To')
    notes = fields.Char(string='Notes')
