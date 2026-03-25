import hashlib
import json
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubGuestVisit(models.Model):
    _name = 'club.guest.visit'
    _description = 'Guest Visit'
    _rec_name = 'name'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Visit Number', readonly=True, copy=False, index=True,
        default=lambda self: _('New'),
    )
    qr_token = fields.Char(
        string='QR Token', readonly=True, copy=False, index=True,
        help='Unique token embedded in the QR code for gate scanning.',
    )
    qr_code = fields.Binary(
        string='QR Code', compute='_compute_qr_code',
        help='Scannable QR code containing visit data for gate access.',
    )
    affiliate_id = fields.Many2one(
        'club.affiliate', string='Host Affiliate', required=True,
        ondelete='restrict',
    )
    guest_id = fields.Many2one(
        'club.guest', string='Guest', required=True,
        ondelete='restrict',
    )
    date = fields.Date(string='Visit Date', required=True, default=fields.Date.context_today)
    check_in_time = fields.Float(string='Check-In Time')
    check_out_time = fields.Float(string='Check-Out Time')
    areas_accessed = fields.Selection(
        [
            ('pool', 'Pool'),
            ('golf', 'Golf'),
            ('tennis', 'Tennis'),
            ('restaurant', 'Restaurant'),
            ('social_area', 'Social Area'),
            ('gym', 'Gym'),
            ('general', 'General'),
        ],
        string='Area Accessed',
    )
    status = fields.Selection(
        [
            ('registered', 'Registered'),
            ('checked_in', 'Checked In'),
            ('checked_out', 'Checked Out'),
            ('cancelled', 'Cancelled'),
            ('no_show', 'No Show'),
        ],
        string='Status',
        default='registered',
        required=True,
    )
    policy_id = fields.Many2one(
        'club.guest.policy', string='Guest Policy',
    )
    allow_independent_access = fields.Boolean(
        string='Guest May Enter Without Affiliate',
        default=False,
        help='If checked, the guest and party members can access the club '
             'without the host affiliate being present.',
    )
    vehicle_plate = fields.Char(
        string='Vehicle Plate',
        help='Optional vehicle plate for the guest party.',
    )
    party_member_ids = fields.One2many(
        'club.guest.visit.party', 'visit_id',
        string='Party Members',
        help='Additional people accompanying this guest.',
    )
    party_count = fields.Integer(
        string='Party Size',
        compute='_compute_party_count',
        store=True,
    )
    notes = fields.Text(string='Notes')

    @api.depends('party_member_ids')
    def _compute_party_count(self):
        for visit in self:
            # +1 for the main guest
            visit.party_count = 1 + len(visit.party_member_ids)

    @api.depends('qr_token')
    def _compute_qr_code(self):
        try:
            import qrcode
            import io
            import base64
            has_qrcode = True
        except ImportError:
            has_qrcode = False

        for visit in self:
            if not visit.qr_token or not has_qrcode:
                visit.qr_code = False
                continue
            qr_data = visit._get_qr_payload()
            qr = qrcode.QRCode(version=1, box_size=6, border=2)
            qr.add_data(json.dumps(qr_data))
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            visit.qr_code = base64.b64encode(buf.getvalue())

    def _get_qr_payload(self):
        """Build the JSON payload embedded in the QR code."""
        self.ensure_one()
        return {
            'type': 'club_guest_visit',
            'token': self.qr_token,
            'visit': self.name,
            'guest': self.guest_id.name,
            'guest_id_number': self.guest_id.identification or '',
            'host': self.affiliate_id.name,
            'host_number': self.affiliate_id.affiliate_number or '',
            'date': str(self.date),
            'party_size': self.party_count,
            'independent': self.allow_independent_access,
            'vehicle': self.vehicle_plate or '',
        }

    def _generate_qr_token(self):
        """Generate a unique, hard-to-guess token for QR scanning."""
        self.ensure_one()
        raw = '%s-%s-%s' % (self.id, self.name, uuid.uuid4().hex[:8])
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.guest.visit'
                ) or _('New')
        records = super().create(vals_list)
        for visit in records:
            if not visit.qr_token:
                visit.qr_token = visit._generate_qr_token()
        return records

    @api.constrains('affiliate_id', 'date', 'policy_id')
    def _check_max_guests_per_visit(self):
        """Ensure the affiliate does not exceed the max guests per visit (per day)."""
        for visit in self:
            if visit.status == 'cancelled':
                continue
            policy = visit.policy_id
            if not policy:
                continue
            same_day_count = self.search_count([
                ('affiliate_id', '=', visit.affiliate_id.id),
                ('date', '=', visit.date),
                ('status', '!=', 'cancelled'),
            ])
            if same_day_count > policy.max_guests_per_visit:
                raise ValidationError(
                    _('Affiliate "%(affiliate)s" exceeds the maximum of %(max)d guests '
                      'per visit on %(date)s.',
                      affiliate=visit.affiliate_id.name,
                      max=policy.max_guests_per_visit,
                      date=visit.date)
                )

    @api.constrains('affiliate_id', 'date', 'policy_id')
    def _check_max_visits_per_month(self):
        """Ensure the affiliate does not exceed the max visits per month."""
        for visit in self:
            if visit.status == 'cancelled':
                continue
            policy = visit.policy_id
            if not policy:
                continue
            first_of_month = visit.date.replace(day=1)
            if visit.date.month == 12:
                last_of_month = visit.date.replace(year=visit.date.year + 1, month=1, day=1)
            else:
                last_of_month = visit.date.replace(month=visit.date.month + 1, day=1)
            month_count = self.search_count([
                ('affiliate_id', '=', visit.affiliate_id.id),
                ('date', '>=', first_of_month),
                ('date', '<', last_of_month),
                ('status', '!=', 'cancelled'),
            ])
            if month_count > policy.max_visits_per_month:
                raise ValidationError(
                    _('Affiliate "%(affiliate)s" exceeds the maximum of %(max)d guest '
                      'visits per month.',
                      affiliate=visit.affiliate_id.name,
                      max=policy.max_visits_per_month)
                )

    def action_send_qr_email(self):
        """Send the QR code to the guest via email using a mail template."""
        self.ensure_one()
        if not self.guest_id.email:
            raise ValidationError(
                _('Guest "%s" does not have an email address configured.') % self.guest_id.name
            )
        template = self.env.ref(
            'club_guests.mail_template_guest_visit_qr', raise_if_not_found=False
        )
        if template:
            template.send_mail(self.id, force_send=True)
        else:
            # Fallback: compose email manually
            body = _(
                '<p>Dear %(guest)s,</p>'
                '<p>You have been invited to visit <b>%(club)s</b> by %(host)s.</p>'
                '<p><b>Visit Date:</b> %(date)s<br/>'
                '<b>Visit Number:</b> %(visit)s<br/>'
                '<b>Party Size:</b> %(party)d</p>'
                '<p>Please present this QR code at the club entrance:</p>'
                '<p><img src="data:image/png;base64,%(qr)s" width="200"/></p>'
                '<p>We look forward to your visit!</p>',
                guest=self.guest_id.name,
                club=self.env.company.name,
                host=self.affiliate_id.name,
                date=self.date,
                visit=self.name,
                party=self.party_count,
                qr=self.qr_code.decode() if self.qr_code else '',
            )
            self.env['mail.mail'].create({
                'subject': _('Your Club Visit QR Code — %s') % self.name,
                'email_to': self.guest_id.email,
                'body_html': body,
            }).send()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Email Sent'),
                'message': _('QR code sent to %s') % self.guest_id.email,
                'type': 'success',
                'sticky': False,
            },
        }

    def action_share_qr_whatsapp(self):
        """Open WhatsApp with a pre-filled message containing visit details."""
        self.ensure_one()
        phone = self.guest_id.phone or ''
        # Strip non-numeric chars for WhatsApp URL
        phone_clean = ''.join(c for c in phone if c.isdigit() or c == '+')

        message = _(
            "Hello %(guest)s! You've been invited to visit the club by %(host)s.\n\n"
            "Visit Date: %(date)s\n"
            "Visit Number: %(visit)s\n"
            "Party Size: %(party)d\n\n"
            "Please present your QR code at the entrance. "
            "You can view it here: %(url)s",
            guest=self.guest_id.name,
            host=self.affiliate_id.name,
            date=self.date,
            visit=self.name,
            party=self.party_count,
            url='%s/my/guest-visit/%s' % (
                self.env['ir.config_parameter'].sudo().get_param('web.base.url', ''),
                self.id,
            ),
        )

        import urllib.parse
        wa_url = 'https://wa.me/%s?text=%s' % (
            phone_clean,
            urllib.parse.quote(message),
        )
        return {
            'type': 'ir.actions.act_url',
            'url': wa_url,
            'target': 'new',
        }

    def action_check_in(self):
        """Set check-in time to now and mark as checked in."""
        now = fields.Datetime.now()
        hour_float = now.hour + now.minute / 60.0
        for visit in self:
            visit.write({
                'check_in_time': hour_float,
                'status': 'checked_in',
            })

    def action_check_out(self):
        """Set check-out time to now and mark as checked out."""
        now = fields.Datetime.now()
        hour_float = now.hour + now.minute / 60.0
        for visit in self:
            visit.write({
                'check_out_time': hour_float,
                'status': 'checked_out',
            })
