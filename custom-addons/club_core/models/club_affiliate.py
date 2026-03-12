from odoo import api, fields, models, _


class ClubAffiliate(models.Model):
    _name = 'club.affiliate'
    _inherits = {'res.partner': 'partner_id'}
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Club Affiliate'
    _rec_name = 'name'  # 'name' is inherited from res.partner

    partner_id = fields.Many2one(
        'res.partner',
        required=True,
        ondelete='cascade',
        string='Partner',
        auto_join=True,
    )
    membership_type = fields.Selection(
        [
            ('individual', 'Individual'),
            ('family_primary', 'Family - Primary'),
            ('family_dependent', 'Family - Dependent'),
            ('corporate_admin', 'Corporate - Admin'),
            ('corporate_employee', 'Corporate - Employee'),
        ],
        required=True,
        default='individual',
        string='Membership Type',
    )
    membership_ids = fields.One2many(
        'club.membership', 'affiliate_id', string='Memberships'
    )
    family_group_id = fields.Many2one(
        'club.family.group', string='Family Group'
    )
    corporate_group_id = fields.Many2one(
        'club.corporate.group', string='Corporate Group'
    )
    affiliate_number = fields.Char(
        string='Affiliate Number', readonly=True, copy=False, index=True
    )
    membership_status = fields.Selection(
        [
            ('none', 'No Membership'),
            ('active', 'Active'),
            ('suspended', 'Suspended'),
            ('expired', 'Expired'),
        ],
        compute='_compute_membership_status',
        store=True,
        string='Membership Status',
    )
    photo = fields.Binary(string='Photo', attachment=True)

    _sql_constraints = [
        ('affiliate_number_uniq', 'unique(affiliate_number)',
         'Affiliate number must be unique.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('affiliate_number'):
                vals['affiliate_number'] = self.env['ir.sequence'].next_by_code(
                    'club.affiliate'
                )
        return super().create(vals_list)

    @api.depends('membership_ids', 'membership_ids.status')
    def _compute_membership_status(self):
        for affiliate in self:
            statuses = affiliate.membership_ids.mapped('status')
            if 'active' in statuses:
                affiliate.membership_status = 'active'
            elif 'suspended' in statuses:
                affiliate.membership_status = 'suspended'
            elif statuses:
                affiliate.membership_status = 'expired'
            else:
                affiliate.membership_status = 'none'
