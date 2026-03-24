from odoo import fields, models


class ClubGolfBag(models.Model):
    _name = 'club.golf.bag'
    _description = 'Golf Bag'
    _rec_name = 'tag_number'

    tag_number = fields.Char(string='Tag Number', required=True, index=True)
    owner_id = fields.Many2one(
        'club.affiliate', required=True, string='Owner',
    )
    locker_number = fields.Char(string='Locker Number')
    status = fields.Selection(
        [
            ('stored', 'Stored'),
            ('with_member', 'With Member'),
        ],
        default='stored',
        required=True,
        string='Status',
    )
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('tag_number_uniq', 'unique(tag_number)',
         'Bag tag number must be unique.'),
    ]
