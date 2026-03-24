from odoo import api, fields, models, _


class ClubHorse(models.Model):
    _name = 'club.horse'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Club Horse'
    _rec_name = 'name'

    name = fields.Char(
        string='Horse Name',
        required=True,
        tracking=True,
    )
    breed = fields.Char(string='Breed', tracking=True)
    color = fields.Char(string='Coat Color')
    birth_date = fields.Date(string='Date of Birth')
    owner_id = fields.Many2one(
        'club.affiliate',
        string='Owner',
        required=True,
        tracking=True,
        domain="[('membership_status', '=', 'active')]",
    )
    registration_number = fields.Char(
        string='Registration Number',
        readonly=True,
        copy=False,
        index=True,
    )
    stall_id = fields.Many2one(
        'club.stall',
        string='Stall',
        tracking=True,
    )
    photo = fields.Binary(string='Photo', attachment=True)

    # -- Relational for notebook pages --
    feeding_ids = fields.One2many(
        'club.horse.feeding', 'horse_id', string='Feeding Schedules'
    )
    vet_record_ids = fields.One2many(
        'club.vet.record', 'horse_id', string='Vet Records'
    )
    booking_ids = fields.One2many(
        'club.equestrian.booking', 'horse_id', string='Bookings'
    )

    _sql_constraints = [
        ('registration_number_uniq', 'unique(registration_number)',
         'Registration number must be unique.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('registration_number'):
                vals['registration_number'] = self.env['ir.sequence'].next_by_code(
                    'club.horse'
                )
        return super().create(vals_list)
