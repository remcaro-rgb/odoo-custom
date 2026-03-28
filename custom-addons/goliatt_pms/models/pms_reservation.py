from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PmsReservation(models.Model):
    _name = 'pms.reservation'
    _description = 'Reservation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'checkin_date desc, name desc'

    name = fields.Char(
        string='Reservation No.',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    property_id = fields.Many2one(
        'pms.property',
        required=True,
        string='Property',
        tracking=True,
    )
    guest_id = fields.Many2one(
        'res.partner',
        required=True,
        string='Guest',
        tracking=True,
    )
    company_guest_id = fields.Many2one(
        'res.partner',
        string='Billing Company',
    )
    checkin_date = fields.Date(
        required=True,
        string='Check-in',
        tracking=True,
    )
    checkout_date = fields.Date(
        required=True,
        string='Check-out',
        tracking=True,
    )
    nights = fields.Integer(
        compute='_compute_nights',
        string='Nights',
        store=True,
    )
    room_type_id = fields.Many2one(
        'pms.room.type',
        required=True,
        string='Room Type',
        tracking=True,
    )
    room_id = fields.Many2one(
        'pms.room',
        string='Room',
        tracking=True,
    )
    adults = fields.Integer(default=1, string='Adults')
    children = fields.Integer(default=0, string='Children')
    rate_plan_id = fields.Many2one(
        'pms.rate.plan',
        string='Rate Plan',
    )
    daily_rate = fields.Float(string='Daily Rate')
    total_amount = fields.Float(
        compute='_compute_total_amount',
        string='Total Amount',
        store=True,
    )
    state = fields.Selection(
        [
            ('confirmed', 'Confirmed'),
            ('guaranteed', 'Guaranteed'),
            ('checked_in', 'Checked In'),
            ('checked_out', 'Checked Out'),
            ('cancelled', 'Cancelled'),
            ('no_show', 'No Show'),
        ],
        default='confirmed',
        string='State',
        tracking=True,
    )
    guarantee_type = fields.Selection(
        [
            ('credit_card', 'Credit Card'),
            ('deposit', 'Deposit'),
            ('company', 'Company'),
            ('none', 'None'),
        ],
        string='Guarantee Type',
        default='none',
    )
    source = fields.Selection(
        [
            ('direct', 'Direct'),
            ('booking_com', 'Booking.com'),
            ('expedia', 'Expedia'),
            ('airbnb', 'Airbnb'),
            ('despegar', 'Despegar'),
            ('phone', 'Phone'),
            ('walk_in', 'Walk-in'),
            ('other', 'Other'),
        ],
        string='Source / Channel',
        default='direct',
    )
    channel_reservation_id = fields.Char(
        string='Channel Confirmation',
        help='External OTA confirmation code.',
    )
    special_requests = fields.Text(string='Special Requests')
    folio_ids = fields.One2many(
        'pms.folio',
        'reservation_id',
        string='Folios',
    )
    folio_balance = fields.Float(
        compute='_compute_folio_balance',
        string='Folio Balance',
    )
    cancellation_reason = fields.Text(string='Cancellation Reason')
    cancellation_date = fields.Datetime(string='Cancellation Date')

    _sql_constraints = [
        (
            'name_uniq',
            'unique(name)',
            'Reservation number must be unique.',
        ),
    ]

    @api.constrains('checkin_date', 'checkout_date')
    def _check_dates(self):
        for rec in self:
            if rec.checkin_date and rec.checkout_date:
                if rec.checkout_date <= rec.checkin_date:
                    raise ValidationError(
                        _('Check-out date must be after check-in date.')
                    )

    @api.constrains('adults', 'room_type_id')
    def _check_occupancy(self):
        for rec in self:
            if rec.room_type_id and rec.adults > rec.room_type_id.max_adults:
                raise ValidationError(
                    _(
                        'Number of adults (%s) exceeds the maximum '
                        'for room type %s (%s).',
                        rec.adults,
                        rec.room_type_id.name,
                        rec.room_type_id.max_adults,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pms.reservation'
                ) or _('New')
        records = super().create(vals_list)
        for rec in records:
            if rec.guest_id and not rec.guest_id.is_hotel_guest:
                rec.guest_id.is_hotel_guest = True
        return records

    @api.depends('checkin_date', 'checkout_date')
    def _compute_nights(self):
        for rec in self:
            if rec.checkin_date and rec.checkout_date:
                delta = rec.checkout_date - rec.checkin_date
                rec.nights = delta.days if delta.days > 0 else 0
            else:
                rec.nights = 0

    @api.depends('daily_rate', 'nights')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = rec.daily_rate * rec.nights

    def _compute_folio_balance(self):
        for rec in self:
            rec.folio_balance = sum(rec.folio_ids.mapped('balance'))

    @api.onchange('room_type_id')
    def _onchange_room_type_id(self):
        if self.room_type_id:
            self.daily_rate = self.room_type_id.base_rate

    # ---- Actions -------------------------------------------------------

    def action_confirm(self):
        for rec in self:
            rec.state = 'confirmed'

    def action_checkin(self):
        for rec in self:
            if not rec.room_id:
                raise UserError(
                    _('Please assign a room before checking in.')
                )
            if rec.state not in ('confirmed', 'guaranteed'):
                raise UserError(
                    _('Only confirmed or guaranteed reservations can be checked in.')
                )
            rec.state = 'checked_in'
            rec.room_id.write({
                'status': 'occupied',
                'housekeeping_status': 'dirty',
                'current_reservation_id': rec.id,
            })

    def action_checkout(self):
        for rec in self:
            if rec.state != 'checked_in':
                raise UserError(
                    _('Only checked-in reservations can be checked out.')
                )
            rec.state = 'checked_out'
            if rec.room_id:
                rec.room_id.write({
                    'status': 'available',
                    'housekeeping_status': 'dirty',
                    'current_reservation_id': False,
                })
                # Create housekeeping task
                self.env['pms.housekeeping.task'].create({
                    'room_id': rec.room_id.id,
                    'task_type': 'checkout_clean',
                    'priority': 'vip' if rec.guest_id.vip_level not in (False, 'none') else 'normal',
                })

    def action_cancel(self):
        for rec in self:
            if rec.state in ('checked_in', 'checked_out'):
                raise UserError(
                    _('Cannot cancel a reservation that is already checked in or out.')
                )
            rec.state = 'cancelled'
            rec.cancellation_date = fields.Datetime.now()

    def action_no_show(self):
        for rec in self:
            if rec.state not in ('confirmed', 'guaranteed'):
                raise UserError(
                    _('Only confirmed / guaranteed reservations can be marked as no-show.')
                )
            rec.state = 'no_show'

    def action_view_folios(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Folios'),
            'res_model': 'pms.folio',
            'view_mode': 'list,form',
            'domain': [('reservation_id', '=', self.id)],
            'context': {'default_reservation_id': self.id},
        }

    # ---- Kiosk actions -----------------------------------------------------

    def action_kiosk_checkin(self):
        """Initiate kiosk self-check-in for this reservation."""
        self.ensure_one()
        if self.state not in ('confirmed', 'guaranteed'):
            raise UserError(
                _('Only confirmed reservations can use kiosk check-in.')
            )
        session = self.env['pms.kiosk.session'].create({
            'property_id': self.property_id.id,
            'reservation_id': self.id,
            'guest_id': self.guest_id.id,
            'session_type': 'checkin',
            'status': 'started',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Kiosk Check-In'),
            'res_model': 'pms.kiosk.session',
            'res_id': session.id,
            'view_mode': 'form',
            'views': [[
                self.env.ref(
                    'goliatt_pms.view_pms_kiosk_session_form_kiosk'
                ).id,
                'form',
            ]],
            'target': 'new',
        }
