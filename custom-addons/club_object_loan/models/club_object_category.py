from odoo import fields, models


class ClubObjectCategory(models.Model):
    _name = 'club.object.category'
    _description = 'Object Loan Category'

    name = fields.Char(required=True, string='Category Name')
    max_loan_days = fields.Integer(
        default=7, string='Max Loan Days',
        help='Maximum number of days an item in this category can be loaned.',
    )
    item_ids = fields.One2many(
        'club.object.item', 'category_id', string='Items',
    )
