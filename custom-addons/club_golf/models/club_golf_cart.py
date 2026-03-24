from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubGolfCart(models.Model):
    _name = 'club.golf.cart'
    _description = 'Golf Cart'
    _rec_name = 'name'

    name = fields.Char(string='Cart Number', required=True)
    cart_type = fields.Selection(
        [
            ('rental', 'Rental'),
            ('owned', 'Owned'),
        ],
        required=True,
        default='rental',
        string='Cart Type',
    )
    owner_id = fields.Many2one(
        'club.affiliate', string='Owner',
    )
    status = fields.Selection(
        [
            ('available', 'Available'),
            ('in_use', 'In Use'),
            ('maintenance', 'Maintenance'),
        ],
        default='available',
        required=True,
        string='Status',
    )
    battery_level = fields.Integer(string='Battery Level (%)', default=100)
    maintenance_log = fields.Text(string='Maintenance Log')
    tee_time_ids = fields.One2many(
        'club.golf.tee.time', 'cart_id',
        string='Tee Times',
    )

    @api.constrains('cart_type', 'owner_id')
    def _check_owner_required_if_owned(self):
        for cart in self:
            if cart.cart_type == 'owned' and not cart.owner_id:
                raise ValidationError(
                    _('An owned cart must have an owner assigned.')
                )
