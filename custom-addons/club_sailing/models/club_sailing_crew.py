from odoo import fields, models


class ClubSailingCrew(models.Model):
    _name = 'club.sailing.crew'
    _description = 'Sailing Crew Member'
    _order = 'name'

    name = fields.Char(string='Crew Member Name', required=True)
    partner_id = fields.Many2one(
        'res.partner', string='Contact',
    )
    role = fields.Selection(
        [
            ('captain', 'Captain'),
            ('instructor', 'Instructor'),
            ('deckhand', 'Deckhand'),
        ],
        required=True,
        string='Role',
    )
    certification = fields.Char(string='Certification')
    active = fields.Boolean(string='Active', default=True)
