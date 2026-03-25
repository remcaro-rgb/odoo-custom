from odoo import fields, models


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
            ('proxy', 'Proxy'),
        ],
        string='Status',
        default='invited',
    )
    proxy_for_id = fields.Many2one(
        'club.affiliate',
        string='Proxy For',
        help='If attending as proxy for another member.',
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
