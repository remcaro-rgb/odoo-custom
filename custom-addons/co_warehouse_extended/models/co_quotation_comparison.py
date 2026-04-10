from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoQuotationComparison(models.Model):
    _name = 'co.quotation.comparison'
    _description = 'Quotation Comparison'
    _order = 'create_date desc'

    purchase_request_id = fields.Many2one(
        'co.purchase.request', string='Purchase Request',
        required=True, ondelete='cascade')
    rfq_ids = fields.One2many(
        'purchase.order', 'co_comparison_id', string='RFQs')
    recommended_rfq_id = fields.Many2one(
        'purchase.order', string='Recommended',
        compute='_compute_recommended', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('compared', 'Compared'),
        ('selected', 'Selected'),
    ], default='draft', string='Status')
    selected_rfq_id = fields.Many2one(
        'purchase.order', string='Selected RFQ', readonly=True)

    @api.depends('rfq_ids.amount_total', 'rfq_ids.partner_id')
    def _compute_recommended(self):
        for rec in self:
            if not rec.rfq_ids:
                rec.recommended_rfq_id = False
                continue
            best = None
            best_score = -1
            for rfq in rec.rfq_ids:
                supplier_score = self.env['co.supplier.score'].search([
                    ('partner_id', '=', rfq.partner_id.id),
                    ('company_id', '=', rfq.company_id.id),
                ], limit=1)
                score = supplier_score.total_score if supplier_score else 50.0
                max_total = max(r.amount_total for r in rec.rfq_ids) or 1
                price_score = (1 - rfq.amount_total / max_total) * 100 if max_total else 50
                combined = score * 0.6 + price_score * 0.4
                if combined > best_score:
                    best_score = combined
                    best = rfq
            rec.recommended_rfq_id = best

    def action_accept_recommendation(self):
        self.ensure_one()
        if not self.recommended_rfq_id:
            raise UserError(_('No recommendation available.'))
        self._select_rfq(self.recommended_rfq_id)

    def action_select_rfq(self):
        self.ensure_one()
        rfq_id = self.env.context.get('selected_rfq_id')
        if rfq_id:
            rfq = self.env['purchase.order'].browse(rfq_id)
            self._select_rfq(rfq)
        return True

    def _select_rfq(self, rfq):
        self.ensure_one()
        for other in self.rfq_ids - rfq:
            other.button_cancel()
        rfq.button_confirm()
        self.selected_rfq_id = rfq.id
        self.state = 'selected'
        self.purchase_request_id.write({
            'state': 'purchase',
        })
