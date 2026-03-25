from odoo import api, fields, models


class ClubAccessSupplier(models.Model):
    _name = 'club.access.supplier'
    _description = 'Club Access Supplier'
    _order = 'name'
    _rec_name = 'name'

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        ondelete='restrict',
    )
    name = fields.Char(
        string='Name',
        related='partner_id.name',
        store=True,
        readonly=True,
    )
    contract_reference = fields.Char(string='Contract Reference')
    active = fields.Boolean(string='Active', default=True)
    staff_ids = fields.One2many(
        'club.access.supplier.staff',
        'supplier_id',
        string='Staff Members',
    )
    staff_count = fields.Integer(
        string='Staff Count',
        compute='_compute_staff_count',
    )
    notes = fields.Text(string='Notes')

    @api.depends('staff_ids')
    def _compute_staff_count(self):
        for supplier in self:
            supplier.staff_count = len(supplier.staff_ids)
