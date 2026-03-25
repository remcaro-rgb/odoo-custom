from odoo import api, fields, models


class ClubGuest(models.Model):
    _name = 'club.guest'
    _description = 'Club Guest'
    _rec_name = 'name'

    name = fields.Char(string='Guest Full Name', required=True)
    identification = fields.Char(string='ID Number')
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    relationship = fields.Selection(
        [
            ('family', 'Family'),
            ('friend', 'Friend'),
            ('business', 'Business'),
            ('other', 'Other'),
        ],
        string='Relationship',
    )
    photo = fields.Binary(string='Photo')
    visit_ids = fields.One2many(
        'club.guest.visit', 'guest_id', string='Visits',
    )
    visit_count = fields.Integer(
        string='Visit Count', compute='_compute_visit_count',
    )
    notes = fields.Text(string='Notes')

    @api.depends('visit_ids')
    def _compute_visit_count(self):
        for guest in self:
            guest.visit_count = len(guest.visit_ids)
