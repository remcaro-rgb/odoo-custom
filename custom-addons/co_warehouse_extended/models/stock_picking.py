from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    quality_check_notes = fields.Html(
        string='Quality Check Notes',
        help='Notes from quality inspection during goods receipt.',
    )
    quality_check_passed = fields.Boolean(
        string='Quality Check Passed',
        default=True,
    )
    co_invoice_id = fields.Many2one(
        'account.move',
        string='Linked Invoice',
        domain="[('move_type', 'in', ['in_invoice', 'in_refund'])]",
        help='Vendor invoice linked to this receipt.',
        copy=False,
    )
    co_auto_invoice = fields.Boolean(
        string='Auto-Create Invoice',
        help='Automatically create a vendor bill when this receipt is validated.',
    )

    def button_validate(self):
        res = super().button_validate()
        for picking in self:
            if picking.state != 'done':
                continue
            if picking.picking_type_code != 'incoming':
                continue
            if not picking.purchase_id:
                continue
            journal_mode = picking.company_id.purchase_journal_mode
            if journal_mode == 'auto_entry':
                picking._create_receipt_journal_entry()
            elif picking.co_auto_invoice and not picking.co_invoice_id:
                picking._create_vendor_bill()
        return res

    def _create_receipt_journal_entry(self):
        """Create journal entry for goods receipt: debit inventory, credit payable."""
        self.ensure_one()
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            return

        move_lines = []
        for move in self.move_ids.filtered(lambda m: m.state == 'done'):
            product = move.product_id
            qty = move.quantity
            price = product.standard_price
            amount = qty * price

            if amount == 0:
                continue

            # Inventory account (debit)
            stock_account = (
                product.categ_id.property_stock_valuation_account_id or
                product.categ_id.property_stock_account_input_categ_id)
            # Payable account (credit)
            payable_account = self.partner_id.property_account_payable_id

            if not stock_account or not payable_account:
                continue

            move_lines.append((0, 0, {
                'name': _('%s - Receipt', product.display_name),
                'account_id': stock_account.id,
                'debit': amount,
                'credit': 0.0,
                'product_id': product.id,
                'quantity': qty,
            }))
            move_lines.append((0, 0, {
                'name': _('%s - Payable', product.display_name),
                'account_id': payable_account.id,
                'debit': 0.0,
                'credit': amount,
                'partner_id': self.partner_id.id,
            }))

            # Tax lines
            if product.supplier_taxes_id:
                taxes = product.supplier_taxes_id.compute_all(
                    price, currency=self.company_id.currency_id,
                    quantity=qty, product=product, partner=self.partner_id)
                for tax_line in taxes.get('taxes', []):
                    tax_amount = tax_line['amount']
                    if tax_amount:
                        tax_account = tax_line.get('account_id')
                        if tax_account:
                            move_lines.append((0, 0, {
                                'name': tax_line['name'],
                                'account_id': tax_account,
                                'debit': abs(tax_amount) if tax_amount > 0 else 0,
                                'credit': abs(tax_amount) if tax_amount < 0 else 0,
                            }))
                            move_lines.append((0, 0, {
                                'name': _('Tax payable - %s', tax_line['name']),
                                'account_id': payable_account.id,
                                'debit': 0.0,
                                'credit': abs(tax_amount) if tax_amount > 0 else 0,
                            }))

        if not move_lines:
            return

        account_move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'ref': _('Receipt: %s', self.name),
            'move_type': 'entry',
            'line_ids': move_lines,
        })
        account_move.action_post()
        self.co_invoice_id = account_move.id

    def _create_vendor_bill(self):
        """Create a vendor bill from the receipt linked to a purchase order."""
        self.ensure_one()
        po = self.purchase_id
        if not po:
            raise UserError(_('No purchase order linked to this receipt.'))

        # Use Odoo's standard PO action to create invoice
        po.action_create_invoice()

        # Link the last created invoice back
        invoices = po.invoice_ids.filtered(lambda m: m.state == 'draft')
        if invoices:
            self.co_invoice_id = invoices[-1].id

    def action_view_invoice(self):
        """Open the linked vendor bill."""
        self.ensure_one()
        if not self.co_invoice_id:
            raise UserError(_('No invoice linked to this receipt.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.co_invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    co_purchase_request_id = fields.Many2one(
        'co.purchase.request',
        string='Purchase Request',
        readonly=True,
        copy=False,
    )
    co_comparison_id = fields.Many2one(
        'co.quotation.comparison', string='Quotation Comparison',
        readonly=True, copy=False)

    co_fulfillment_pct = fields.Float(
        string='Fulfillment %',
        compute='_compute_fulfillment', store=True)
    co_fulfillment_state = fields.Selection([
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('complete', 'Complete'),
    ], string='Fulfillment Status',
        compute='_compute_fulfillment', store=True)

    @api.depends('order_line.product_qty', 'order_line.qty_received')
    def _compute_fulfillment(self):
        for order in self:
            total_qty = sum(order.order_line.mapped('product_qty'))
            received_qty = sum(order.order_line.mapped('qty_received'))
            if total_qty:
                order.co_fulfillment_pct = (received_qty / total_qty) * 100
            else:
                order.co_fulfillment_pct = 0.0
            if received_qty == 0:
                order.co_fulfillment_state = 'pending'
            elif received_qty >= total_qty:
                order.co_fulfillment_state = 'complete'
            else:
                order.co_fulfillment_state = 'partial'

    # Supplier payment tracking: show related invoices and payments
    co_payment_state_summary = fields.Text(
        string='Payment Summary',
        compute='_compute_payment_state_summary',
    )

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.amount_residual')
    def _compute_payment_state_summary(self):
        for po in self:
            lines = []
            for inv in po.invoice_ids:
                state_label = dict(
                    inv._fields['payment_state'].selection
                ).get(inv.payment_state, inv.payment_state or '')
                lines.append(
                    '%s: %s (Residual: %s %s)' % (
                        inv.name or _('Draft'),
                        state_label,
                        '{:,.2f}'.format(inv.amount_residual),
                        inv.currency_id.name,
                    )
                )
            po.co_payment_state_summary = '\n'.join(lines) if lines else _('No invoices')
