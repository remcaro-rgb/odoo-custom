from odoo import fields, models


class ClubFaqItem(models.Model):
    _name = 'club.faq.item'
    _description = 'FAQ Item'
    _order = 'sequence, id'

    category_id = fields.Many2one(
        'club.faq.category', string='Category', required=True,
        ondelete='cascade',
    )
    question = fields.Char(string='Question', required=True, translate=True)
    answer = fields.Html(string='Answer', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    is_published = fields.Boolean(string='Published', default=True)
    author_id = fields.Many2one(
        'res.users', string='Author', default=lambda self: self.env.user,
    )
    helpful_count = fields.Integer(string='Helpful Count', default=0)
