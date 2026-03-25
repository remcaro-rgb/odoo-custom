from odoo import fields, models


class ClubPqrCategory(models.Model):
    _name = 'club.pqr.category'
    _description = 'PQR Category'
    _order = 'name'

    name = fields.Char(required=True, string='Category Name')
    description = fields.Text(string='Description')
    responsible_id = fields.Many2one(
        'res.users',
        string='Default Handler',
    )
    sla_days = fields.Integer(
        string='SLA Days',
        default=15,
        help='Expected number of days to resolve requests in this category.',
    )
