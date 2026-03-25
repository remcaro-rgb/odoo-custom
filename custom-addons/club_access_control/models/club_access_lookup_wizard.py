from odoo import api, fields, models, _


class ClubAccessLookupWizard(models.TransientModel):
    _name = 'club.access.lookup.wizard'
    _description = 'Access Lookup Wizard'

    entry_id = fields.Many2one(
        'club.access.entry',
        string='Entry',
        required=True,
    )
    search_term = fields.Char(string='Search Term')
    result_ids = fields.One2many(
        'club.access.lookup.result',
        'wizard_id',
        string='Results',
    )

    def _do_search(self):
        """Populate result_ids by searching across multiple models."""
        self.ensure_one()
        term = (self.search_term or '').strip()
        if not term:
            return

        results = []

        # Search affiliates
        affiliates = self.env['club.affiliate'].search(
            [('name', 'ilike', term)], limit=10,
        )
        for aff in affiliates:
            ptype = 'affiliate'
            if aff.membership_type == 'family_dependent':
                ptype = 'family_member'
            results.append({
                'wizard_id': self.id,
                'display_name': aff.name,
                'person_type': ptype,
                'person_ref': 'club.affiliate,%d' % aff.id,
                'identification': aff.affiliate_number or '',
                'photo': aff.image_128,
            })

        # Search affiliate employees
        employees = self.env['club.affiliate.employee'].search(
            [('name', 'ilike', term)], limit=10,
        )
        for emp in employees:
            results.append({
                'wizard_id': self.id,
                'display_name': '%s (%s)' % (emp.name, emp.affiliate_id.name),
                'person_type': 'affiliate_employee',
                'person_ref': 'club.affiliate.employee,%d' % emp.id,
                'identification': emp.identification_number or '',
                'photo': emp.photo,
            })

        # Search guests
        guests = self.env['club.guest'].search(
            [('name', 'ilike', term)], limit=10,
        )
        for guest in guests:
            results.append({
                'wizard_id': self.id,
                'display_name': guest.name,
                'person_type': 'guest',
                'person_ref': 'club.guest,%d' % guest.id,
                'identification': guest.identification or '',
                'photo': guest.photo,
            })

        # Search supplier staff
        staff_members = self.env['club.access.supplier.staff'].search(
            [('name', 'ilike', term)], limit=10,
        )
        for staff in staff_members:
            results.append({
                'wizard_id': self.id,
                'display_name': '%s (%s)' % (staff.name, staff.supplier_id.name),
                'person_type': 'supplier_staff',
                'person_ref': 'club.access.supplier.staff,%d' % staff.id,
                'identification': staff.identification_number or '',
                'photo': staff.photo,
            })

        if results:
            self.env['club.access.lookup.result'].create(results)

    def action_done(self):
        """Close wizard without selecting."""
        return {'type': 'ir.actions.act_window_close'}


class ClubAccessLookupResult(models.TransientModel):
    _name = 'club.access.lookup.result'
    _description = 'Access Lookup Result'

    wizard_id = fields.Many2one(
        'club.access.lookup.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    display_name = fields.Char(string='Name')
    person_type = fields.Selection(
        [
            ('affiliate', 'Affiliate'),
            ('family_member', 'Family Member'),
            ('affiliate_employee', 'Affiliate Employee'),
            ('guest', 'Guest'),
            ('event_attendee', 'Event Attendee'),
            ('tournament_participant', 'Tournament Participant'),
            ('supplier_staff', 'Supplier Staff'),
        ],
        string='Person Type',
    )
    person_ref = fields.Char(string='Person Reference')
    identification = fields.Char(string='Identification')
    photo = fields.Binary(string='Photo')

    def action_select(self):
        """Select this result and apply it to the entry."""
        self.ensure_one()
        entry = self.wizard_id.entry_id
        if not entry:
            return {'type': 'ir.actions.act_window_close'}

        # Parse person_ref: "model,id"
        if not self.person_ref:
            return {'type': 'ir.actions.act_window_close'}

        model_name, res_id_str = self.person_ref.split(',', 1)
        res_id = int(res_id_str)

        vals = {'person_type': self.person_type}

        field_map = {
            'club.affiliate': 'affiliate_id',
            'club.affiliate.employee': 'employee_id',
            'club.guest': 'guest_id',
            'club.access.supplier.staff': 'supplier_staff_id',
        }
        person_field = field_map.get(model_name)
        if person_field:
            vals[person_field] = res_id

        # Determine access allowed
        record = self.env[model_name].browse(res_id)
        access_allowed = True
        reason = ''

        if model_name == 'club.affiliate':
            access_allowed = record.membership_status == 'active'
            if not access_allowed:
                reason = _('Membership is not active (status: %s)') % (
                    record.membership_status or 'none'
                )
        elif model_name == 'club.affiliate.employee':
            if record.status != 'active':
                access_allowed = False
                reason = _('Employee is not active (status: %s)') % record.status
            elif record.affiliate_id.membership_status != 'active':
                access_allowed = False
                reason = _(
                    'Employer affiliate "%s" does not have an active membership'
                ) % record.affiliate_id.name
        elif model_name == 'club.guest':
            today = fields.Date.context_today(self)
            visit = self.env['club.guest.visit'].search([
                ('guest_id', '=', res_id),
                ('date', '=', today),
                ('status', 'in', ('registered', 'checked_in')),
            ], limit=1)
            if visit:
                vals['guest_visit_id'] = visit.id
            else:
                access_allowed = False
                reason = _('No visit registered for today for guest "%s"') % record.name
        elif model_name == 'club.access.supplier.staff':
            if record.status != 'active':
                access_allowed = False
                reason = _('Supplier staff is not active (status: %s)') % record.status

        if access_allowed:
            vals['access_status'] = 'granted'
        else:
            vals['access_status'] = 'denied'
            vals['denial_reason'] = reason

        entry.write(vals)
        return {'type': 'ir.actions.act_window_close'}
