from odoo import fields, models


class CoPurchaseApprovalLine(models.Model):
    _name = 'co.purchase.approval.line'
    _description = 'Purchase Approval Line'
    _order = 'sequence, id'

    purchase_request_id = fields.Many2one(
        'co.purchase.request', required=True,
        ondelete='cascade', index=True)
    approval_level_id = fields.Many2one(
        'co.purchase.approval.level', string='Approval Level',
        required=True)
    sequence = fields.Integer(
        related='approval_level_id.sequence', store=True)
    approver_id = fields.Many2one(
        'res.users', string='Approved By', readonly=True)
    date = fields.Datetime(string='Date', readonly=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending', string='Status', readonly=True)
    notes = fields.Text(string='Notes')
