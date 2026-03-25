from odoo import fields, models


class ClubSwimmingLifeguard(models.Model):
    _name = 'club.swimming.lifeguard'
    _description = 'Swimming Lifeguard'
    _order = 'partner_id'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner', required=True, ondelete='cascade',
        string='Partner',
    )
    employee_number = fields.Char(string='Employee Number')
    certification = fields.Char(string='Certification')
    certification_expiry = fields.Date(string='Certification Expiry')
    active = fields.Boolean(string='Active', default=True)
