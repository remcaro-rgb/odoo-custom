import logging
from datetime import datetime, time

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ClubAffiliateBillingRun(models.Model):
    _name = 'club.affiliate.billing.run'
    _inherit = ['mail.thread']
    _description = 'Affiliate Billing Run'
    _order = 'period_start desc, id desc'

    name = fields.Char(
        string='Name',
        readonly=True,
        copy=False,
        default='/',
    )
    period_start = fields.Date(
        string='Period Start',
        required=True,
        help='First day of the billing period.',
    )
    period_end = fields.Date(
        string='Period End',
        required=True,
        help='Last day of the billing period.',
    )
    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        tracking=True,
        string='Status',
    )
    run_date = fields.Date(
        string='Run Date',
        readonly=True,
        help='Date when the billing run was executed.',
    )
    invoice_ids = fields.One2many(
        'club.affiliate.billing.invoice',
        'billing_run_id',
        string='Billing Invoices',
    )
    invoice_count = fields.Integer(
        compute='_compute_invoice_count',
        string='Invoice Count',
    )
    total_amount = fields.Float(
        compute='_compute_total_amount',
        string='Total Amount',
    )
    notes = fields.Text(string='Notes')

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    @api.depends('invoice_ids', 'invoice_ids.total_amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.invoice_ids.mapped('total_amount'))

    # ------------------------------------------------------------------
    # CRUD overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.affiliate.billing.run'
                ) or '/'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_generate(self):
        """Generate billing invoice records from POS Cargo a Socio orders."""
        self.ensure_one()
        if self.status != 'draft':
            raise UserError(
                _('Only draft billing runs can be generated.')
            )
        self.status = 'processing'

        # Build datetime boundaries for the period
        dt_start = datetime.combine(self.period_start, time.min)
        dt_end = datetime.combine(self.period_end, time.max)

        # Find all POS orders with Cargo a Socio payments in the period
        orders = self.env['pos.order'].search([
            ('date_order', '>=', fields.Datetime.to_string(dt_start)),
            ('date_order', '<=', fields.Datetime.to_string(dt_end)),
            ('payment_ids.payment_method_id.is_cargo_socio', '=', True),
            ('cargo_socio_billed', '=', False),
            ('state', 'in', ['paid', 'done', 'invoiced']),
        ])

        # Group by partner, collecting cargo-socio payment amounts
        partner_orders = {}
        for order in orders:
            cargo_payments = order.payment_ids.filtered(
                lambda p: p.payment_method_id.is_cargo_socio
            )
            if not cargo_payments:
                continue
            partner = order.partner_id
            if not partner:
                continue
            if partner not in partner_orders:
                partner_orders[partner] = []
            partner_orders[partner].append(
                (order, sum(cargo_payments.mapped('amount')))
            )

        # Create billing invoice records per affiliate
        BillingInvoice = self.env['club.affiliate.billing.invoice']
        BillingLine = self.env['club.affiliate.billing.line']

        for partner, order_data in partner_orders.items():
            affiliate = self.env['club.affiliate'].search([
                ('partner_id', '=', partner.id),
            ], limit=1)
            if not affiliate:
                continue

            billing_inv = BillingInvoice.create({
                'billing_run_id': self.id,
                'affiliate_id': affiliate.id,
            })

            for order, amount in order_data:
                order_date_str = order.date_order.strftime('%d/%m/%Y') if order.date_order else ''
                BillingLine.create({
                    'billing_invoice_id': billing_inv.id,
                    'pos_order_id': order.id,
                    'amount': amount,
                    'description': _('POS %s — %s') % (
                        order.name or order.pos_reference or '',
                        order_date_str,
                    ),
                })
                order.cargo_socio_billed = True
                order.cargo_socio_billing_invoice_id = billing_inv.id

        self.run_date = fields.Date.today()
        self.status = 'completed'

    def action_create_invoices(self):
        """Create actual account.move invoices for each billing invoice."""
        self.ensure_one()
        pending = self.invoice_ids.filtered(
            lambda i: i.invoice_status == 'pending'
        )
        for billing_inv in pending:
            try:
                invoice_lines = []
                for line in billing_inv.line_ids:
                    invoice_lines.append((0, 0, {
                        'name': line.description or _('Cargo a Socio'),
                        'quantity': 1.0,
                        'price_unit': line.amount,
                    }))

                if not invoice_lines:
                    continue

                invoice = self.env['account.move'].create({
                    'move_type': 'out_invoice',
                    'partner_id': billing_inv.partner_id.id,
                    'invoice_date': fields.Date.today(),
                    'ref': '%s — %s' % (
                        self.name,
                        billing_inv.affiliate_id.affiliate_number or '',
                    ),
                    'invoice_line_ids': invoice_lines,
                })
                billing_inv.invoice_id = invoice.id
                billing_inv.invoice_status = 'invoiced'
            except Exception as e:
                billing_inv.invoice_status = 'error'
                billing_inv.error_message = str(e)
                _logger.exception(
                    'Error creating invoice for billing invoice %s: %s',
                    billing_inv.id, e,
                )

    def action_cancel(self):
        """Cancel the billing run."""
        self.ensure_one()
        if self.status not in ('draft', 'processing'):
            raise UserError(
                _('Only draft or processing billing runs can be cancelled.')
            )
        # Unmark any billed orders
        for billing_inv in self.invoice_ids:
            for line in billing_inv.line_ids:
                if line.pos_order_id:
                    line.pos_order_id.cargo_socio_billed = False
                    line.pos_order_id.cargo_socio_billing_invoice_id = False
        self.status = 'cancelled'

    def action_draft(self):
        """Reset a cancelled billing run back to draft."""
        self.ensure_one()
        if self.status != 'cancelled':
            raise UserError(
                _('Only cancelled billing runs can be reset to draft.')
            )
        self.status = 'draft'

    def action_view_invoices(self):
        """Open the account.move invoices linked to this billing run."""
        self.ensure_one()
        invoice_ids = self.invoice_ids.mapped('invoice_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoice_ids)],
        }

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------

    @api.model
    def _cron_monthly_billing(self):
        """Automatic monthly billing: runs on the 1st, bills previous month."""
        today = fields.Date.today()
        # Previous month boundaries
        first_of_current = today.replace(day=1)
        last_of_previous = first_of_current - relativedelta(days=1)
        first_of_previous = last_of_previous.replace(day=1)

        # Check if a billing run already exists for this period
        existing = self.search([
            ('period_start', '=', first_of_previous),
            ('period_end', '=', last_of_previous),
            ('status', '!=', 'cancelled'),
        ], limit=1)
        if existing:
            _logger.info(
                'Monthly billing run already exists for %s to %s (ID %s). Skipping.',
                first_of_previous, last_of_previous, existing.id,
            )
            return

        billing_run = self.create({
            'period_start': first_of_previous,
            'period_end': last_of_previous,
            'notes': _('Auto-generated monthly billing run.'),
        })
        billing_run.action_generate()
        billing_run.action_create_invoices()
        _logger.info(
            'Monthly billing run %s completed: %d invoices, total %.2f',
            billing_run.name, billing_run.invoice_count, billing_run.total_amount,
        )
