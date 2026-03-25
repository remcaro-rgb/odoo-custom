from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ClubFoundItem(models.Model):
    _name = 'club.found.item'
    _inherit = ['mail.thread']
    _description = 'Club Found Item'
    _order = 'date_found desc, id desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    found_by = fields.Char(
        string='Found By',
    )
    found_by_affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Found By (Affiliate)',
    )
    description = fields.Text(
        string='Description',
        required=True,
    )
    location_found = fields.Char(
        string='Location Found',
    )
    date_found = fields.Date(
        string='Date Found',
        default=fields.Date.context_today,
        required=True,
    )
    category = fields.Selection(
        [
            ('electronics', 'Electronics'),
            ('clothing', 'Clothing'),
            ('jewelry', 'Jewelry'),
            ('documents', 'Documents'),
            ('sports_equipment', 'Sports Equipment'),
            ('other', 'Other'),
        ],
        string='Category',
        required=True,
        default='other',
        tracking=True,
    )
    storage_location = fields.Char(
        string='Storage Location',
    )
    photo = fields.Binary(
        string='Photo',
        attachment=True,
    )
    status = fields.Selection(
        [
            ('registered', 'Registered'),
            ('matched', 'Matched'),
            ('claimed', 'Claimed'),
            ('disposed', 'Disposed'),
        ],
        string='Status',
        default='registered',
        required=True,
        tracking=True,
    )
    claimed_by_id = fields.Many2one(
        'club.affiliate',
        string='Claimed By',
        tracking=True,
    )
    claim_date = fields.Date(
        string='Claim Date',
    )
    notes = fields.Text(
        string='Notes',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.found.item'
                ) or _('New')
        return super().create(vals_list)

    def action_claim(self, affiliate_id=None):
        """Mark this found item as claimed by an affiliate."""
        self.ensure_one()
        if self.status not in ('registered', 'matched'):
            raise UserError(
                _('Only items with status "Registered" or "Matched" can be claimed.')
            )
        vals = {
            'status': 'claimed',
            'claim_date': fields.Date.context_today(self),
        }
        if affiliate_id:
            vals['claimed_by_id'] = affiliate_id
        self.write(vals)
        return True

    def action_claim_wizard(self):
        """Claim action callable from form button — uses claimed_by_id if set."""
        self.ensure_one()
        return self.action_claim(affiliate_id=self.claimed_by_id.id if self.claimed_by_id else None)

    def action_dispose(self):
        """Mark this found item as disposed (unclaimed for too long)."""
        self.ensure_one()
        if self.status not in ('registered', 'matched'):
            raise UserError(
                _('Only items with status "Registered" or "Matched" can be disposed.')
            )
        self.write({'status': 'disposed'})
        return True
