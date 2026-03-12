from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ClubMembership(models.Model):
    _name = 'club.membership'
    _description = 'Club Membership'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc'

    affiliate_id = fields.Many2one(
        'club.affiliate',
        required=True,
        string='Affiliate',
        ondelete='cascade',
    )
    plan_id = fields.Many2one(
        'club.membership.plan', required=True, string='Plan'
    )
    start_date = fields.Date(required=True, string='Start Date')
    end_date = fields.Date(
        compute='_compute_end_date',
        store=True,
        string='End Date',
    )
    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('suspended', 'Suspended'),
            ('expired', 'Expired'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        tracking=True,
        string='Status',
    )
    invoice_ids = fields.Many2many(
        'account.move',
        'club_membership_account_move_rel',
        'membership_id',
        'move_id',
        string='Invoices',
        copy=False,
    )
    invoice_count = fields.Integer(
        compute='_compute_invoice_count', string='Invoice Count'
    )
    notes = fields.Text(string='Notes')

    # ── Computed fields ──────────────────────────────────────────────────

    @api.depends('start_date', 'plan_id', 'plan_id.billing_period')
    def _compute_end_date(self):
        for rec in self:
            if rec.start_date and rec.plan_id:
                if rec.plan_id.billing_period == 'monthly':
                    rec.end_date = rec.start_date + relativedelta(months=1)
                else:
                    rec.end_date = rec.start_date + relativedelta(years=1)
            else:
                rec.end_date = False

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    # ── Actions ──────────────────────────────────────────────────────────

    def action_activate(self):
        """Activate membership and generate first invoice."""
        for rec in self:
            if rec.status != 'draft':
                raise UserError(
                    _('Only draft memberships can be activated.')
                )
            rec.status = 'active'
            rec._generate_membership_invoice()

    def action_suspend(self):
        for rec in self:
            rec.status = 'suspended'

    def action_cancel(self):
        for rec in self:
            rec.status = 'cancelled'

    def action_view_invoices(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
        }

    # ── Invoice generation ────────────────────────────────────────────────

    def _get_invoice_partner(self):
        """Return the partner to invoice. For family groups, use billing_affiliate."""
        self.ensure_one()
        if self.affiliate_id.family_group_id:
            billing = self.affiliate_id.family_group_id.billing_affiliate_id
            if billing:
                return billing.partner_id
        if self.affiliate_id.corporate_group_id:
            admin = self.affiliate_id.corporate_group_id.admin_id
            if admin:
                return admin.partner_id
        return self.affiliate_id.partner_id

    def _generate_membership_invoice(self):
        self.ensure_one()
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self._get_invoice_partner().id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.plan_id.product_id.id,
                'quantity': 1.0,
                'price_unit': self.plan_id.fee,
                'name': self.plan_id.name,
            })],
        })
        self.invoice_ids = [(4, invoice.id)]
        return invoice

    def _generate_late_fee_invoice(self):
        self.ensure_one()
        if not self.plan_id.late_fee_product_id or not self.plan_id.late_fee_amount:
            return False
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self._get_invoice_partner().id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.plan_id.late_fee_product_id.id,
                'quantity': 1.0,
                'price_unit': self.plan_id.late_fee_amount,
                'name': _('Late Fee — %s') % self.plan_id.name,
            })],
        })
        self.invoice_ids = [(4, invoice.id)]
        return invoice

    # ── Cron jobs ─────────────────────────────────────────────────────────

    @api.model
    def _cron_check_renewals(self):
        """Generate renewal invoice for memberships expiring within 7 days.
        Skips memberships that already received a renewal invoice today.
        """
        today = fields.Date.today()
        soon = today + relativedelta(days=7)
        expiring = self.search([
            ('status', '=', 'active'),
            ('end_date', '<=', soon),
            ('end_date', '>=', today),
        ])
        for membership in expiring:
            # Avoid duplicate: skip if a renewal invoice was already created today
            already_invoiced = membership.invoice_ids.filtered(
                lambda inv: inv.create_date and inv.create_date.date() >= today
            )
            if not already_invoiced:
                membership._generate_membership_invoice()

    @api.model
    def _cron_apply_late_fees(self):
        """Suspend memberships past grace period with unpaid invoices."""
        today = fields.Date.today()
        candidates = self.search([
            ('status', 'in', ['active', 'suspended']),
            ('end_date', '!=', False),
        ])
        for membership in candidates:
            grace_end = membership.end_date + relativedelta(
                days=membership.plan_id.grace_period_days
            )
            if today <= grace_end:
                continue
            unpaid = membership.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice'
                and inv.state == 'posted'
                and inv.payment_state not in ('paid', 'in_payment', 'reversed')
            )
            if unpaid and membership.status != 'suspended':
                membership._generate_late_fee_invoice()
                membership.status = 'suspended'
