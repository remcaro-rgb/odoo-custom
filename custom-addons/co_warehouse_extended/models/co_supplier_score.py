from odoo import api, fields, models, _


class CoSupplierScore(models.Model):
    _name = 'co.supplier.score'
    _description = 'Supplier Score'
    _order = 'total_score desc'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner', string='Supplier', required=True,
        domain="[('supplier_rank', '>', 0)]")
    product_category_id = fields.Many2one(
        'product.category', string='Product Category')
    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company)
    score_price = fields.Float(string='Price Score (0-100)', default=50.0)
    score_delivery = fields.Float(string='Delivery Score (0-100)', default=50.0)
    score_quality = fields.Float(string='Quality Score (0-100)', default=50.0)
    score_compliance = fields.Float(string='Compliance Score (0-100)', default=50.0)
    weight_price = fields.Float(string='Price Weight')
    weight_delivery = fields.Float(string='Delivery Weight')
    weight_quality = fields.Float(string='Quality Weight')
    weight_compliance = fields.Float(string='Compliance Weight')
    total_score = fields.Float(
        string='Total Score', compute='_compute_total_score', store=True)
    last_updated = fields.Datetime(string='Last Recalculated')

    @api.depends('score_price', 'score_delivery', 'score_quality',
                 'score_compliance', 'weight_price', 'weight_delivery',
                 'weight_quality', 'weight_compliance')
    def _compute_total_score(self):
        for rec in self:
            total_weight = (rec.weight_price + rec.weight_delivery +
                            rec.weight_quality + rec.weight_compliance)
            if total_weight:
                rec.total_score = (
                    rec.score_price * rec.weight_price +
                    rec.score_delivery * rec.weight_delivery +
                    rec.score_quality * rec.weight_quality +
                    rec.score_compliance * rec.weight_compliance
                ) / total_weight
            else:
                rec.total_score = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._apply_default_weights(vals)
        return super().create(vals_list)

    def _apply_default_weights(self, vals):
        company = self.env['res.company'].browse(
            vals.get('company_id', self.env.company.id))
        for field, default_field in [
            ('weight_price', 'supplier_weight_price'),
            ('weight_delivery', 'supplier_weight_delivery'),
            ('weight_quality', 'supplier_weight_quality'),
            ('weight_compliance', 'supplier_weight_compliance'),
        ]:
            if not vals.get(field):
                vals[field] = getattr(company, default_field)

    def action_recalculate(self):
        for rec in self:
            rec._compute_price_score()
            rec._compute_delivery_score()
            rec._compute_quality_score()
            rec._compute_compliance_score()
            rec.last_updated = fields.Datetime.now()

    def _compute_price_score(self):
        self.ensure_one()
        domain = [
            ('order_id.partner_id', '=', self.partner_id.id),
            ('order_id.state', '=', 'purchase'),
            ('order_id.company_id', '=', self.company_id.id),
        ]
        if self.product_category_id:
            domain.append(
                ('product_id.categ_id', '=', self.product_category_id.id))
        lines = self.env['purchase.order.line'].search(domain, limit=100)
        if not lines:
            return
        avg_price = sum(lines.mapped('price_unit')) / len(lines)
        all_domain = [
            ('order_id.state', '=', 'purchase'),
            ('order_id.company_id', '=', self.company_id.id),
            ('product_id', 'in', lines.mapped('product_id').ids),
        ]
        all_lines = self.env['purchase.order.line'].search(
            all_domain, limit=500)
        if not all_lines:
            return
        market_avg = sum(all_lines.mapped('price_unit')) / len(all_lines)
        if market_avg:
            ratio = avg_price / market_avg
            self.score_price = max(0, min(100, (2 - ratio) * 50))

    def _compute_delivery_score(self):
        self.ensure_one()
        pickings = self.env['stock.picking'].search([
            ('partner_id', '=', self.partner_id.id),
            ('picking_type_code', '=', 'incoming'),
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
        ], limit=100)
        if not pickings:
            return
        on_time = sum(
            1 for p in pickings
            if p.date_done and p.scheduled_date and
            p.date_done <= p.scheduled_date)
        self.score_delivery = (on_time / len(pickings)) * 100

    def _compute_quality_score(self):
        self.ensure_one()
        pickings = self.env['stock.picking'].search([
            ('partner_id', '=', self.partner_id.id),
            ('picking_type_code', '=', 'incoming'),
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
        ], limit=100)
        if not pickings:
            return
        passed = sum(1 for p in pickings if p.quality_check_passed)
        self.score_quality = (passed / len(pickings)) * 100

    def _compute_compliance_score(self):
        self.ensure_one()
        orders = self.env['purchase.order'].search([
            ('partner_id', '=', self.partner_id.id),
            ('state', '=', 'purchase'),
            ('company_id', '=', self.company_id.id),
        ], limit=50)
        if not orders:
            return
        total_ordered = sum(orders.mapped('order_line.product_qty'))
        total_received = sum(orders.mapped('order_line.qty_received'))
        if total_ordered:
            self.score_compliance = min(
                100, (total_received / total_ordered) * 100)
