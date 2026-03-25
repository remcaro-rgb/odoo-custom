from odoo import fields, models


class ClubAffiliateEmployeeAccessLog(models.Model):
    _name = 'club.affiliate.employee.access.log'
    _description = 'Club Affiliate Employee Access Log'
    _order = 'date desc, check_in desc'

    employee_id = fields.Many2one(
        'club.affiliate.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
    )
    check_in = fields.Float(string='Check In')
    check_out = fields.Float(string='Check Out')
    area = fields.Char(string='Area')
    notes = fields.Text(string='Notes')
