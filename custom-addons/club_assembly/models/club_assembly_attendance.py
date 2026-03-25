from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubAssemblyAttendance(models.Model):
    _name = 'club.assembly.attendance'
    _description = 'Assembly Attendance'
    _order = 'assembly_id, affiliate_id'

    assembly_id = fields.Many2one(
        'club.assembly',
        string='Assembly',
        required=True,
        ondelete='cascade',
    )
    affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Affiliate',
        required=True,
    )
    status = fields.Selection(
        [
            ('invited', 'Invited'),
            ('present', 'Present'),
            ('absent', 'Absent'),
            ('excused', 'Excused'),
            ('proxy', 'By Proxy'),
        ],
        string='Status',
        default='invited',
    )
    # --- Proxy / Poder fields ---
    proxy_for_id = fields.Many2one(
        'club.affiliate',
        string='Proxy For',
        help='If this affiliate is attending as proxy (apoderado) for another member.',
    )
    proxy_holder_id = fields.Many2one(
        'club.affiliate',
        string='Represented By',
        help='The affiliate who holds the power of attorney (poder) to vote '
             'on behalf of this member.',
    )
    proxy_document = fields.Binary(
        string='Authorization Letter (Poder)',
        help='Scanned or photographed power of attorney document.',
    )
    proxy_document_name = fields.Char(
        string='Document Filename',
    )
    check_in_time = fields.Datetime(
        string='Check-in Time',
    )
    notes = fields.Char(
        string='Notes',
    )

    _sql_constraints = [
        (
            'unique_assembly_affiliate',
            'UNIQUE(assembly_id, affiliate_id)',
            'Each affiliate can only have one attendance record per assembly.',
        ),
    ]

    @api.constrains('status', 'proxy_holder_id')
    def _check_proxy_holder(self):
        for rec in self:
            if rec.status == 'proxy' and not rec.proxy_holder_id:
                raise ValidationError(
                    _('When status is "By Proxy", you must specify who '
                      'represents this member (Represented By).')
                )
            if rec.proxy_holder_id and rec.proxy_holder_id == rec.affiliate_id:
                raise ValidationError(
                    _('An affiliate cannot be their own proxy representative.')
                )

    @api.onchange('status')
    def _onchange_status_proxy(self):
        if self.status != 'proxy':
            self.proxy_holder_id = False
            self.proxy_document = False
            self.proxy_document_name = False
