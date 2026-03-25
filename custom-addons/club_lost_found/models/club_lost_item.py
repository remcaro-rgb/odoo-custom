from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ClubLostItem(models.Model):
    _name = 'club.lost.item'
    _inherit = ['mail.thread']
    _description = 'Club Lost Item'
    _order = 'date_reported desc, id desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    reporter_id = fields.Many2one(
        'club.affiliate',
        string='Reported By',
        required=True,
        tracking=True,
    )
    description = fields.Text(
        string='Description',
        required=True,
    )
    location_lost = fields.Char(
        string='Location Lost',
    )
    date_lost = fields.Date(
        string='Date Lost',
    )
    date_reported = fields.Date(
        string='Date Reported',
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
    photo = fields.Binary(
        string='Photo',
        attachment=True,
    )
    status = fields.Selection(
        [
            ('reported', 'Reported'),
            ('matched', 'Matched'),
            ('claimed', 'Claimed'),
            ('closed', 'Closed'),
        ],
        string='Status',
        default='reported',
        required=True,
        tracking=True,
    )
    matched_found_id = fields.Many2one(
        'club.found.item',
        string='Matched Found Item',
        tracking=True,
    )
    notes = fields.Text(
        string='Notes',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.lost.item'
                ) or _('New')
        return super().create(vals_list)

    def action_match(self, found_item_id):
        """Link this lost item to a found item and set both to 'matched'."""
        self.ensure_one()
        found_item = self.env['club.found.item'].browse(found_item_id)
        if not found_item.exists():
            raise UserError(_('The selected found item does not exist.'))
        if self.status != 'reported':
            raise UserError(_('Only items with status "Reported" can be matched.'))
        if found_item.status != 'registered':
            raise UserError(_('Only found items with status "Registered" can be matched.'))
        self.write({
            'matched_found_id': found_item.id,
            'status': 'matched',
        })
        found_item.write({
            'status': 'matched',
        })
        return True

    def action_match_wizard(self):
        """Open a dialog to select a found item and match it."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Select Found Item to Match'),
            'res_model': 'club.found.item',
            'view_mode': 'list,form',
            'domain': [('status', '=', 'registered'), ('category', '=', self.category)],
            'target': 'new',
            'context': {
                'lost_item_id': self.id,
                'default_status': 'registered',
            },
        }

    def action_close(self):
        """Close this lost item report."""
        self.ensure_one()
        self.write({'status': 'closed'})
        return True
