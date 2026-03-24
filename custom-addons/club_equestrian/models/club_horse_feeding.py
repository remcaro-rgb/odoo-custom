from odoo import api, fields, models, _


class ClubHorseFeeding(models.Model):
    _name = 'club.horse.feeding'
    _description = 'Horse Feeding Schedule'
    _rec_name = 'horse_id'

    horse_id = fields.Many2one(
        'club.horse',
        string='Horse',
        required=True,
        ondelete='cascade',
    )
    feed_type = fields.Char(string='Feed Type', required=True)
    quantity = fields.Float(string='Quantity', required=True)
    unit = fields.Selection(
        [
            ('kg', 'Kg'),
            ('lbs', 'Lbs'),
            ('flakes', 'Flakes'),
        ],
        string='Unit',
        required=True,
        default='kg',
    )
    schedule = fields.Selection(
        [
            ('morning', 'Morning'),
            ('afternoon', 'Afternoon'),
            ('evening', 'Evening'),
        ],
        string='Schedule',
        required=True,
        default='morning',
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.uid,
    )
    notes = fields.Text(string='Notes')
