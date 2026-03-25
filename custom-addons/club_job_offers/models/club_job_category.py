from odoo import fields, models


class ClubJobCategory(models.Model):
    _name = 'club.job.category'
    _description = 'Job Offer Category'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
