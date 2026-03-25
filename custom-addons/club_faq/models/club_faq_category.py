from odoo import api, fields, models


class ClubFaqCategory(models.Model):
    _name = 'club.faq.category'
    _description = 'FAQ Category'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    icon = fields.Char(string='Icon', help='Optional CSS icon class')
    faq_ids = fields.One2many(
        'club.faq.item', 'category_id', string='FAQ Items',
    )
    faq_count = fields.Integer(
        string='FAQ Count', compute='_compute_faq_count', store=True,
    )

    @api.depends('faq_ids')
    def _compute_faq_count(self):
        for category in self:
            category.faq_count = len(category.faq_ids)
