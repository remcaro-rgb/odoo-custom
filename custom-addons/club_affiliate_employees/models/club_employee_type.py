from odoo import fields, models


class ClubEmployeeType(models.Model):
    _name = 'club.employee.type'
    _description = 'Club Employee Type'
    _order = 'name'

    name = fields.Char(string='Name', required=True, translate=True)
