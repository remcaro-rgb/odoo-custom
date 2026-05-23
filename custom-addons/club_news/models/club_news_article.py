from odoo import _, api, fields, models


class ClubNewsArticle(models.Model):
    _name = 'club.news.article'
    _inherit = ['mail.thread']
    _description = 'News Article'
    _order = 'is_pinned desc, publish_date desc, id desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    title = fields.Char(required=True, tracking=True)
    category_id = fields.Many2one(
        'club.news.category',
        string='Category',
        tracking=True,
    )
    author_id = fields.Many2one(
        'res.users',
        string='Author',
        default=lambda self: self.env.user,
        tracking=True,
    )
    content = fields.Html(required=True, string='Content')
    summary = fields.Text(string='Summary')
    cover_image = fields.Binary(string='Cover Image')
    publish_date = fields.Date(string='Publish Date', tracking=True)
    expiry_date = fields.Date(string='Expiry Date')
    is_featured = fields.Boolean(string='Featured', default=False, tracking=True)
    is_pinned = fields.Boolean(string='Pinned', default=False)
    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('published', 'Published'),
            ('archived', 'Archived'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )
    target_audience = fields.Selection(
        [
            ('all', 'All'),
            ('members_only', 'Members Only'),
            ('staff_only', 'Staff Only'),
        ],
        default='all',
        required=True,
        string='Target Audience',
    )
    tag_ids = fields.Many2many(
        'club.news.tag',
        string='Tags',
    )
    view_count = fields.Integer(string='Views', default=0, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.news.article'
                ) or _('New')
        return super().create(vals_list)

    def action_publish(self):
        for record in self:
            record.write({
                'status': 'published',
                'publish_date': fields.Date.context_today(self),
            })

    def action_archive_article(self):
        for record in self:
            record.write({'status': 'archived'})

    def action_draft(self):
        for record in self:
            record.write({'status': 'draft'})
