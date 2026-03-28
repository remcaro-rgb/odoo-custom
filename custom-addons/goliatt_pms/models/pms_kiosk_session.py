from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PmsKioskSession(models.Model):
    _name = 'pms.kiosk.session'
    _description = 'Kiosk Session'
    _order = 'start_time desc'

    name = fields.Char(
        string='Session No.',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    property_id = fields.Many2one(
        'pms.property',
        required=True,
        string='Property',
        ondelete='cascade',
    )
    reservation_id = fields.Many2one(
        'pms.reservation',
        string='Reservation',
    )
    guest_id = fields.Many2one(
        'res.partner',
        string='Guest',
    )
    session_type = fields.Selection(
        [
            ('checkin', 'Check-In'),
            ('checkout', 'Check-Out'),
        ],
        required=True,
        string='Type',
    )
    status = fields.Selection(
        [
            ('started', 'Started'),
            ('id_scanned', 'ID Scanned'),
            ('confirmed', 'Confirmed'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('abandoned', 'Abandoned'),
        ],
        default='started',
        string='Status',
    )
    id_scan_data = fields.Text(string='ID Scan Data')
    id_document_type = fields.Char(string='ID Document Type')
    id_document_number = fields.Char(string='ID Document Number')
    guest_signature = fields.Binary(string='Guest Signature')
    start_time = fields.Datetime(
        string='Start Time',
        default=fields.Datetime.now,
    )
    end_time = fields.Datetime(string='End Time')
    room_assigned = fields.Char(string='Room Assigned')
    key_issued = fields.Boolean(string='Key Issued', default=False)
    error_message = fields.Char(string='Error Message')
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pms.kiosk.session'
                ) or _('New')
        return super().create(vals_list)

    def action_scan_id(self):
        """Simulate ID scanning -- in production would connect to hardware.
        For prototype: copies guest's ID data to the session."""
        self.ensure_one()
        if self.reservation_id and self.reservation_id.guest_id:
            guest = self.reservation_id.guest_id
            self.write({
                'id_document_type': guest.guest_id_type or '',
                'id_document_number': guest.guest_id_number or '',
                'id_scan_data': 'Scanned: %s %s' % (
                    guest.guest_id_type or '', guest.guest_id_number or '',
                ),
                'status': 'id_scanned',
            })

    def action_confirm_checkin(self):
        """Guest confirms their details and signs."""
        self.ensure_one()
        self.status = 'confirmed'

    def action_complete_checkin(self):
        """Complete the kiosk check-in: assign room, update reservation."""
        self.ensure_one()
        res = self.reservation_id
        if not res:
            self.write({
                'status': 'failed',
                'error_message': _('No reservation linked'),
            })
            return

        # Auto-assign room if not assigned
        if not res.room_id:
            available_room = self.env['pms.room'].search([
                ('room_type_id', '=', res.room_type_id.id),
                ('status', '=', 'available'),
                ('housekeeping_status', 'in', ['clean', 'inspected']),
            ], limit=1)
            if available_room:
                res.room_id = available_room
            else:
                self.write({
                    'status': 'failed',
                    'error_message': _('No clean rooms available'),
                })
                return

        # Perform check-in
        try:
            res.action_checkin()
            self.write({
                'status': 'completed',
                'room_assigned': res.room_id.name,
                'key_issued': True,
                'end_time': fields.Datetime.now(),
            })
        except Exception as e:
            self.write({
                'status': 'failed',
                'error_message': str(e)[:200],
            })
