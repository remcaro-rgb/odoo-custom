from odoo import api, fields, models, _
from odoo.exceptions import UserError

PERSON_TYPE_SELECTION = [
    ('affiliate', 'Affiliate'),
    ('family_member', 'Family Member'),
    ('affiliate_employee', 'Affiliate Employee'),
    ('guest', 'Guest'),
    ('event_attendee', 'Event Attendee'),
    ('tournament_participant', 'Tournament Participant'),
    ('supplier_staff', 'Supplier Staff'),
]


class ClubAccessEntry(models.Model):
    _name = 'club.access.entry'
    _inherit = ['mail.thread']
    _description = 'Club Access Entry'
    _order = 'entry_datetime desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Entry Number',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    checkpoint_id = fields.Many2one(
        'club.access.checkpoint',
        string='Checkpoint',
        required=True,
    )
    entry_datetime = fields.Datetime(
        string='Entry Date/Time',
        required=True,
        default=fields.Datetime.now,
    )
    exit_datetime = fields.Datetime(
        string='Exit Date/Time',
        readonly=True,
    )
    person_type = fields.Selection(
        PERSON_TYPE_SELECTION,
        string='Person Type',
    )
    person_name = fields.Char(
        string='Person Name',
        compute='_compute_person_name',
        store=True,
        readonly=True,
    )
    person_photo = fields.Binary(
        string='Person Photo',
        compute='_compute_person_photo',
        readonly=True,
    )

    # -- Polymorphic person links --
    affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Affiliate',
    )
    employee_id = fields.Many2one(
        'club.affiliate.employee',
        string='Employee',
    )
    guest_id = fields.Many2one(
        'club.guest',
        string='Guest',
    )
    guest_visit_id = fields.Many2one(
        'club.guest.visit',
        string='Guest Visit',
    )
    event_registration_id = fields.Many2one(
        'event.registration',
        string='Event Registration',
    )
    tournament_participant_id = fields.Many2one(
        'club.tournament.participant',
        string='Tournament Participant',
    )
    supplier_staff_id = fields.Many2one(
        'club.access.supplier.staff',
        string='Supplier Staff',
    )

    # -- Identification fields --
    identification_method = fields.Selection(
        [
            ('membership_card', 'Membership Card'),
            ('access_card', 'Access Card'),
            ('gov_id', 'Government ID'),
            ('vehicle_plate', 'Vehicle Plate'),
            ('manual_lookup', 'Manual Lookup'),
        ],
        string='Identification Method',
        default='membership_card',
    )
    identification_value = fields.Char(
        string='Identifier',
        help='Scan or type the membership card, access card, ID number, or plate.',
    )
    vehicle_id = fields.Many2one(
        'club.access.vehicle',
        string='Vehicle',
    )

    # -- Access decision --
    access_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('granted', 'Granted'),
            ('denied', 'Denied'),
            ('exited', 'Exited'),
        ],
        string='Access Status',
        default='pending',
        required=True,
        tracking=True,
    )
    denial_reason = fields.Char(string='Denial Reason')
    authorized_by = fields.Many2one(
        'res.users',
        string='Authorized By',
        default=lambda self: self.env.user,
    )
    notes = fields.Text(string='Notes')

    # -- Computed / helper --
    is_active_entry = fields.Boolean(
        string='Active Entry',
        compute='_compute_is_active_entry',
        store=True,
    )
    duration_minutes = fields.Float(
        string='Duration (min)',
        compute='_compute_duration_minutes',
        store=True,
    )

    # ── Create with auto-sequence ────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.access.entry'
                ) or _('New')
        return super().create(vals_list)

    # ── Computed fields ──────────────────────────────────────────────────

    @api.depends(
        'person_type',
        'affiliate_id', 'affiliate_id.name',
        'employee_id', 'employee_id.name',
        'guest_id', 'guest_id.name',
        'event_registration_id', 'event_registration_id.partner_id',
        'tournament_participant_id', 'tournament_participant_id.affiliate_id',
        'supplier_staff_id', 'supplier_staff_id.name',
    )
    def _compute_person_name(self):
        for entry in self:
            name = False
            if entry.person_type in ('affiliate', 'family_member') and entry.affiliate_id:
                name = entry.affiliate_id.name
            elif entry.person_type == 'affiliate_employee' and entry.employee_id:
                name = entry.employee_id.name
            elif entry.person_type == 'guest' and entry.guest_id:
                name = entry.guest_id.name
            elif entry.person_type == 'event_attendee' and entry.event_registration_id:
                reg = entry.event_registration_id
                name = reg.partner_id.name if reg.partner_id else reg.name
            elif entry.person_type == 'tournament_participant' and entry.tournament_participant_id:
                name = entry.tournament_participant_id.affiliate_id.name
            elif entry.person_type == 'supplier_staff' and entry.supplier_staff_id:
                name = entry.supplier_staff_id.name
            entry.person_name = name or ''

    @api.depends(
        'person_type',
        'affiliate_id', 'employee_id', 'guest_id', 'supplier_staff_id',
    )
    def _compute_person_photo(self):
        for entry in self:
            photo = False
            if entry.person_type in ('affiliate', 'family_member') and entry.affiliate_id:
                photo = entry.affiliate_id.image_128
            elif entry.person_type == 'affiliate_employee' and entry.employee_id:
                photo = entry.employee_id.photo
            elif entry.person_type == 'guest' and entry.guest_id:
                photo = entry.guest_id.photo
            elif entry.person_type == 'supplier_staff' and entry.supplier_staff_id:
                photo = entry.supplier_staff_id.photo
            entry.person_photo = photo

    @api.depends('access_status', 'exit_datetime')
    def _compute_is_active_entry(self):
        for entry in self:
            entry.is_active_entry = (
                entry.access_status == 'granted' and not entry.exit_datetime
            )

    @api.depends('entry_datetime', 'exit_datetime')
    def _compute_duration_minutes(self):
        for entry in self:
            if entry.entry_datetime and entry.exit_datetime:
                delta = entry.exit_datetime - entry.entry_datetime
                entry.duration_minutes = delta.total_seconds() / 60.0
            else:
                entry.duration_minutes = 0.0

    # ── Actions ──────────────────────────────────────────────────────────

    def action_lookup(self):
        """Resolve the scanned/typed identifier to a person and make access decision."""
        self.ensure_one()
        val = (self.identification_value or '').strip()
        if not val:
            raise UserError(_('Please enter or scan an identifier.'))

        method = self.identification_method
        result = False

        if method == 'membership_card':
            result = self._lookup_by_membership_card(val)
        elif method == 'access_card':
            result = self._lookup_by_access_card(val)
        elif method == 'vehicle_plate':
            result = self._lookup_by_vehicle_plate(val)
        elif method == 'gov_id':
            result = self._lookup_by_gov_id(val)
        elif method == 'manual_lookup':
            return self._lookup_by_name(val)

        if not result:
            self.write({
                'access_status': 'denied',
                'denial_reason': _('No matching person found for identifier: %s') % val,
            })
            return

        # result is a dict with keys: person_type, person_field, person_id,
        # access_allowed, reason, and optionally vehicle_id
        vals = {
            'person_type': result['person_type'],
            result['person_field']: result['person_id'],
        }
        if result.get('vehicle_id'):
            vals['vehicle_id'] = result['vehicle_id']
        if result.get('guest_visit_id'):
            vals['guest_visit_id'] = result['guest_visit_id']

        if result['access_allowed']:
            vals['access_status'] = 'granted'
        else:
            vals['access_status'] = 'denied'
            vals['denial_reason'] = result.get('reason', '')

        self.write(vals)

    def action_exit(self):
        """Register exit: set exit_datetime and status to exited."""
        for entry in self:
            if entry.access_status != 'granted':
                raise UserError(
                    _('Only entries with granted access can be exited.')
                )
            entry.write({
                'exit_datetime': fields.Datetime.now(),
                'access_status': 'exited',
            })

    def action_grant(self):
        """Manually grant access."""
        for entry in self:
            if entry.access_status != 'pending':
                raise UserError(
                    _('Only pending entries can be manually granted.')
                )
            entry.write({'access_status': 'granted'})

    def action_deny_wizard(self):
        """Open a simple wizard to enter a denial reason."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deny Access'),
            'res_model': 'club.access.deny.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_entry_id': self.id},
        }

    def action_deny(self, reason=''):
        """Deny access with a reason."""
        for entry in self:
            if entry.access_status not in ('pending',):
                raise UserError(
                    _('Only pending entries can be denied.')
                )
            entry.write({
                'access_status': 'denied',
                'denial_reason': reason or _('Manually denied'),
            })

    # ── Lookup Methods ───────────────────────────────────────────────────

    def _lookup_by_membership_card(self, val):
        """Search club.affiliate by affiliate_number."""
        affiliate = self.env['club.affiliate'].search(
            [('affiliate_number', '=', val)], limit=1,
        )
        if not affiliate:
            return False

        access_allowed = affiliate.membership_status == 'active'
        reason = ''
        if not access_allowed:
            reason = _('Membership is not active (status: %s)') % (
                affiliate.membership_status or 'none'
            )

        person_type = 'affiliate'
        if affiliate.membership_type == 'family_dependent':
            person_type = 'family_member'

        return {
            'person_type': person_type,
            'person_field': 'affiliate_id',
            'person_id': affiliate.id,
            'access_allowed': access_allowed,
            'reason': reason,
        }

    def _lookup_by_access_card(self, val):
        """Search club.affiliate.employee by access_card_number."""
        employee = self.env['club.affiliate.employee'].search(
            [('access_card_number', '=', val)], limit=1,
        )
        if not employee:
            return False

        # Check employee is active
        if employee.status != 'active':
            return {
                'person_type': 'affiliate_employee',
                'person_field': 'employee_id',
                'person_id': employee.id,
                'access_allowed': False,
                'reason': _('Employee is not active (status: %s)') % employee.status,
            }

        # Check employer affiliate has active membership
        affiliate = employee.affiliate_id
        if affiliate.membership_status != 'active':
            return {
                'person_type': 'affiliate_employee',
                'person_field': 'employee_id',
                'person_id': employee.id,
                'access_allowed': False,
                'reason': _(
                    'Employer affiliate "%s" does not have an active membership'
                ) % affiliate.name,
            }

        return {
            'person_type': 'affiliate_employee',
            'person_field': 'employee_id',
            'person_id': employee.id,
            'access_allowed': True,
            'reason': '',
        }

    def _lookup_by_vehicle_plate(self, val):
        """Search club.access.vehicle by plate_number."""
        vehicle = self.env['club.access.vehicle'].search(
            [('plate_number', '=ilike', val), ('active', '=', True)], limit=1,
        )
        if not vehicle:
            return False

        affiliate = vehicle.affiliate_id
        access_allowed = affiliate.membership_status == 'active'
        reason = ''
        if not access_allowed:
            reason = _('Affiliate "%s" membership is not active (status: %s)') % (
                affiliate.name, affiliate.membership_status or 'none',
            )

        person_type = 'affiliate'
        if affiliate.membership_type == 'family_dependent':
            person_type = 'family_member'

        return {
            'person_type': person_type,
            'person_field': 'affiliate_id',
            'person_id': affiliate.id,
            'vehicle_id': vehicle.id,
            'access_allowed': access_allowed,
            'reason': reason,
        }

    def _lookup_by_gov_id(self, val):
        """Search by government ID across multiple models in priority order."""
        # 1. Affiliate via partner vat
        affiliate = self.env['club.affiliate'].search(
            [('vat', '=', val)], limit=1,
        )
        if affiliate:
            access_allowed = affiliate.membership_status == 'active'
            reason = ''
            if not access_allowed:
                reason = _('Membership is not active (status: %s)') % (
                    affiliate.membership_status or 'none'
                )
            person_type = 'affiliate'
            if affiliate.membership_type == 'family_dependent':
                person_type = 'family_member'
            return {
                'person_type': person_type,
                'person_field': 'affiliate_id',
                'person_id': affiliate.id,
                'access_allowed': access_allowed,
                'reason': reason,
            }

        # 2. Affiliate employee by identification_number
        employee = self.env['club.affiliate.employee'].search(
            [('identification_number', '=', val)], limit=1,
        )
        if employee:
            emp_active = employee.status == 'active'
            aff_active = employee.affiliate_id.membership_status == 'active'
            access_allowed = emp_active and aff_active
            reason = ''
            if not emp_active:
                reason = _('Employee is not active (status: %s)') % employee.status
            elif not aff_active:
                reason = _(
                    'Employer affiliate "%s" does not have an active membership'
                ) % employee.affiliate_id.name
            return {
                'person_type': 'affiliate_employee',
                'person_field': 'employee_id',
                'person_id': employee.id,
                'access_allowed': access_allowed,
                'reason': reason,
            }

        # 3. Guest by identification, check for today's visit
        guest = self.env['club.guest'].search(
            [('identification', '=', val)], limit=1,
        )
        if guest:
            today = fields.Date.context_today(self)
            visit = self.env['club.guest.visit'].search([
                ('guest_id', '=', guest.id),
                ('date', '=', today),
                ('status', 'in', ('registered', 'checked_in')),
            ], limit=1)
            result = {
                'person_type': 'guest',
                'person_field': 'guest_id',
                'person_id': guest.id,
                'access_allowed': bool(visit),
                'reason': '' if visit else _(
                    'No visit registered for today for guest "%s"'
                ) % guest.name,
            }
            if visit:
                result['guest_visit_id'] = visit.id
            return result

        # 4. Supplier staff by identification_number
        staff = self.env['club.access.supplier.staff'].search(
            [('identification_number', '=', val)], limit=1,
        )
        if staff:
            access_allowed = staff.status == 'active'
            reason = ''
            if not access_allowed:
                reason = _('Supplier staff is not active (status: %s)') % staff.status
            return {
                'person_type': 'supplier_staff',
                'person_field': 'supplier_staff_id',
                'person_id': staff.id,
                'access_allowed': access_allowed,
                'reason': reason,
            }

        # 5. Event registration by partner vat for today's event
        today = fields.Date.context_today(self)
        registration = self.env['event.registration'].search([
            ('partner_id.vat', '=', val),
            ('event_id.date_begin', '<=', fields.Datetime.now()),
            ('event_id.date_end', '>=', fields.Datetime.now()),
            ('state', '!=', 'cancel'),
        ], limit=1)
        if registration:
            return {
                'person_type': 'event_attendee',
                'person_field': 'event_registration_id',
                'person_id': registration.id,
                'access_allowed': True,
                'reason': '',
            }

        return False

    def _lookup_by_name(self, val):
        """Search by name across models, open wizard for guard to choose."""
        self.ensure_one()
        wizard = self.env['club.access.lookup.wizard'].create({
            'entry_id': self.id,
            'search_term': val,
        })
        wizard._do_search()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lookup Results'),
            'res_model': 'club.access.lookup.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }


class ClubAccessDenyWizard(models.TransientModel):
    _name = 'club.access.deny.wizard'
    _description = 'Deny Access Wizard'

    entry_id = fields.Many2one(
        'club.access.entry',
        string='Entry',
        required=True,
    )
    reason = fields.Char(string='Denial Reason', required=True)

    def action_confirm(self):
        self.ensure_one()
        self.entry_id.action_deny(self.reason)
        return {'type': 'ir.actions.act_window_close'}
