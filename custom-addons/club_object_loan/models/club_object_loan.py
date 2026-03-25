from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import timedelta


class ClubObjectLoan(models.Model):
    _name = 'club.object.loan'
    _description = 'Object Loan'
    _inherit = ['mail.thread']
    _order = 'loan_date desc, id desc'

    name = fields.Char(
        string='Loan Reference', readonly=True, copy=False, index=True,
    )
    item_id = fields.Many2one(
        'club.object.item', required=True, string='Item',
        ondelete='restrict', tracking=True,
    )
    affiliate_id = fields.Many2one(
        'club.affiliate', required=True, string='Affiliate',
        ondelete='restrict', tracking=True,
    )
    loan_date = fields.Date(
        default=fields.Date.context_today, required=True,
        string='Loan Date', tracking=True,
    )
    due_date = fields.Date(
        compute='_compute_due_date', store=True,
        string='Due Date',
    )
    return_date = fields.Date(string='Return Date', tracking=True)
    quantity = fields.Integer(default=1, required=True, string='Quantity')
    status = fields.Selection(
        [
            ('active', 'Active'),
            ('returned', 'Returned'),
            ('overdue', 'Overdue'),
            ('lost', 'Lost'),
        ],
        default='active',
        required=True,
        string='Status',
        tracking=True,
    )
    notes = fields.Text(string='Notes')
    is_overdue = fields.Boolean(
        compute='_compute_is_overdue', store=True, string='Is Overdue',
    )
    category_id = fields.Many2one(
        related='item_id.category_id', store=True, string='Category',
    )

    @api.depends('loan_date', 'item_id.category_id.max_loan_days')
    def _compute_due_date(self):
        for loan in self:
            if loan.loan_date and loan.item_id.category_id:
                loan.due_date = loan.loan_date + timedelta(
                    days=loan.item_id.category_id.max_loan_days
                )
            else:
                loan.due_date = False

    @api.depends('due_date', 'status')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for loan in self:
            loan.is_overdue = (
                loan.due_date
                and today > loan.due_date
                and loan.status == 'active'
            )

    @api.constrains('quantity', 'item_id')
    def _check_quantity_available(self):
        for loan in self:
            if loan.status not in ('active', 'overdue'):
                continue
            if loan.quantity <= 0:
                raise ValidationError(
                    _('Loan quantity must be at least 1.')
                )
            # Compute available excluding this loan's own contribution
            other_active = sum(
                loan.item_id.loan_ids.filtered(
                    lambda l: l.status in ('active', 'overdue') and l.id != loan.id
                ).mapped('quantity')
            )
            available = loan.item_id.quantity_total - other_active
            if loan.quantity > available:
                raise ValidationError(
                    _('Not enough items available. Requested: %(requested)s, '
                      'Available: %(available)s.',
                      requested=loan.quantity, available=available)
                )

    @api.constrains('item_id')
    def _check_item_status(self):
        for loan in self:
            if loan.status not in ('active', 'overdue'):
                continue
            if loan.item_id.status in ('maintenance', 'retired'):
                raise ValidationError(
                    _('Cannot loan item "%(item)s": it is currently %(status)s.',
                      item=loan.item_id.name,
                      status=loan.item_id.status)
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.object.loan'
                )
        return super().create(vals_list)

    def action_return(self):
        for loan in self:
            loan.write({
                'return_date': fields.Date.context_today(self),
                'status': 'returned',
            })

    def action_mark_lost(self):
        for loan in self:
            loan.write({
                'status': 'lost',
            })

    @api.model
    def _cron_check_overdue(self):
        """Mark active loans as overdue when past due date."""
        today = fields.Date.context_today(self)
        overdue_loans = self.search([
            ('status', '=', 'active'),
            ('due_date', '<', today),
        ])
        overdue_loans.write({'status': 'overdue'})
