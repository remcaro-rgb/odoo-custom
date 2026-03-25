from odoo import fields, models


class ClubNewsTag(models.Model):
    _name = 'club.news.tag'
    _description = 'News Tag'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(string='Color')
