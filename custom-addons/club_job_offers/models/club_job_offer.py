from odoo import api, fields, models, _


class ClubJobOffer(models.Model):
    _name = 'club.job.offer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Job Offer'
    _order = 'publish_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        index=True,
    )
    title = fields.Char(required=True, tracking=True)
    affiliate_id = fields.Many2one(
        'club.affiliate',
        required=True,
        string='Posted By',
        tracking=True,
    )
    category_id = fields.Many2one(
        'club.job.category',
        string='Category',
        tracking=True,
    )
    description = fields.Html(string='Detailed Requirements')
    job_type = fields.Selection(
        [
            ('full_time', 'Full Time'),
            ('part_time', 'Part Time'),
            ('temporary', 'Temporary'),
            ('project', 'Project'),
        ],
        string='Job Type',
        tracking=True,
    )
    salary_range = fields.Char(string='Salary Range')
    location = fields.Char()
    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('published', 'Published'),
            ('filled', 'Filled'),
            ('closed', 'Closed'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )
    publish_date = fields.Date(string='Publish Date', readonly=True)
    expiry_date = fields.Date(string='Expiry Date')
    application_ids = fields.One2many(
        'club.job.application',
        'offer_id',
        string='Applications',
    )
    application_count = fields.Integer(
        compute='_compute_application_count',
        string='Applications Count',
        store=True,
    )

    @api.depends('application_ids')
    def _compute_application_count(self):
        for offer in self:
            offer.application_count = len(offer.application_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.job.offer'
                ) or _('New')
        return super().create(vals_list)

    def action_publish(self):
        for offer in self:
            offer.write({
                'status': 'published',
                'publish_date': fields.Date.context_today(self),
            })

    def action_fill(self):
        for offer in self:
            offer.write({'status': 'filled'})

    def action_close(self):
        for offer in self:
            offer.write({'status': 'closed'})
