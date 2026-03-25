from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubAffiliateEmployee(models.Model):
    _name = 'club.affiliate.employee'
    _description = 'Club Affiliate Employee'
    _order = 'name'

    name = fields.Char(string='Full Name', required=True)
    affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Employer (Affiliate)',
        required=True,
        ondelete='cascade',
    )
    employee_type_id = fields.Many2one(
        'club.employee.type',
        string='Employee Type',
        required=True,
    )
    identification_type = fields.Selection(
        [
            ('cc', 'CC - Cedula de Ciudadania'),
            ('ce', 'CE - Cedula de Extranjeria'),
            ('passport', 'Passport'),
            ('other', 'Other'),
        ],
        string='Identification Type',
        default='cc',
    )
    identification_number = fields.Char(
        string='Identification Number',
        required=True,
    )
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    photo = fields.Binary(string='Photo', attachment=True)
    access_card_number = fields.Char(
        string='Access Card Number',
        copy=False,
        index=True,
    )
    status = fields.Selection(
        [
            ('active', 'Active'),
            ('suspended', 'Suspended'),
            ('inactive', 'Inactive'),
        ],
        string='Status',
        default='active',
        required=True,
    )
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    schedule_ids = fields.One2many(
        'club.affiliate.employee.schedule',
        'employee_id',
        string='Schedule',
    )
    emergency_contact = fields.Char(string='Emergency Contact')
    emergency_phone = fields.Char(string='Emergency Phone')
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        (
            'access_card_number_uniq',
            'UNIQUE(access_card_number)',
            'Access card number must be unique.',
        ),
    ]

    @api.constrains('identification_number')
    def _check_identification_number(self):
        for record in self:
            if not record.identification_number or not record.identification_number.strip():
                raise ValidationError(
                    _('Identification number is required for employee "%s".', record.name)
                )
