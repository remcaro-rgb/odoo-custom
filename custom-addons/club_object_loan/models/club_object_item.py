from odoo import api, fields, models


class ClubObjectItem(models.Model):
    _name = 'club.object.item'
    _description = 'Loanable Object / Item'
    _rec_name = 'name'

    name = fields.Char(required=True, string='Item Name')
    category_id = fields.Many2one(
        'club.object.category', required=True, string='Category',
        ondelete='restrict',
    )
    code = fields.Char(
        string='Code / Barcode', readonly=True, copy=False, index=True,
    )
    description = fields.Text(string='Description')
    status = fields.Selection(
        [
            ('available', 'Available'),
            ('loaned', 'Loaned'),
            ('maintenance', 'Maintenance'),
            ('retired', 'Retired'),
        ],
        default='available',
        required=True,
        string='Status',
    )
    photo = fields.Binary(string='Photo', attachment=True)
    quantity_total = fields.Integer(default=1, string='Total Quantity')
    quantity_available = fields.Integer(
        compute='_compute_quantity_available',
        store=True,
        string='Available Quantity',
    )
    loan_ids = fields.One2many(
        'club.object.loan', 'item_id', string='Loans',
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Item code must be unique.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'club.object.item'
                )
        return super().create(vals_list)

    @api.depends('quantity_total', 'loan_ids', 'loan_ids.status', 'loan_ids.quantity')
    def _compute_quantity_available(self):
        for item in self:
            active_qty = sum(
                item.loan_ids.filtered(
                    lambda l: l.status in ('active', 'overdue')
                ).mapped('quantity')
            )
            item.quantity_available = item.quantity_total - active_qty
