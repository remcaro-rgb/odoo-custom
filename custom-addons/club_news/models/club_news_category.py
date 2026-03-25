from odoo import fields, models


class ClubNewsCategory(models.Model):
    _name = 'club.news.category'
    _description = 'News Category'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(string='Color')
