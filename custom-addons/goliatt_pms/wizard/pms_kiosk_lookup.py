from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PmsKioskLookup(models.TransientModel):
    _name = 'pms.kiosk.lookup'
    _description = 'Kiosk Reservation Lookup'

    lookup_type = fields.Selection(
        [
            ('confirmation_number', 'Confirmation Number'),
            ('id_document', 'ID Document'),
            ('qr_code', 'QR Code'),
        ],
        string='Lookup Type',
        default='confirmation_number',
        required=True,
    )
    lookup_value = fields.Char(
        string='Search Value',
        help='Enter confirmation number, ID document number, or scan QR code.',
    )
    result_reservation_id = fields.Many2one(
        'pms.reservation',
        string='Found Reservation',
        readonly=True,
    )
    message = fields.Char(string='Message', readonly=True)

    def action_search(self):
        """Search for a reservation by confirmation number or guest ID."""
        self.ensure_one()
        if not self.lookup_value:
            self.message = _('Please enter a search value.')
            return self._reload_wizard()

        Reservation = self.env['pms.reservation']
        reservation = False

        if self.lookup_type == 'confirmation_number':
            reservation = Reservation.search([
                ('name', '=', self.lookup_value.strip()),
                ('state', 'in', ('confirmed', 'guaranteed')),
            ], limit=1)
        elif self.lookup_type in ('id_document', 'qr_code'):
            guest = self.env['res.partner'].search([
                ('guest_id_number', '=', self.lookup_value.strip()),
                ('is_hotel_guest', '=', True),
            ], limit=1)
            if guest:
                reservation = Reservation.search([
                    ('guest_id', '=', guest.id),
                    ('state', 'in', ('confirmed', 'guaranteed')),
                    ('checkin_date', '<=', fields.Date.today()),
                    ('checkout_date', '>', fields.Date.today()),
                ], limit=1)

        if reservation:
            self.write({
                'result_reservation_id': reservation.id,
                'message': _('Reservation found: %s - %s') % (
                    reservation.name, reservation.guest_id.name,
                ),
            })
        else:
            self.write({
                'result_reservation_id': False,
                'message': _('No matching reservation found.'),
            })

        return self._reload_wizard()

    def action_proceed(self):
        """Proceed to kiosk check-in for the found reservation."""
        self.ensure_one()
        if not self.result_reservation_id:
            raise UserError(_('No reservation found. Please search first.'))
        return self.result_reservation_id.action_kiosk_checkin()

    def _reload_wizard(self):
        """Return action to reload the wizard with current data."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Self Check-In'),
            'res_model': 'pms.kiosk.lookup',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
