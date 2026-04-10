from odoo import fields, models


class CoPurchaseApprovalLevel(models.Model):
    _name = 'co.purchase.approval.level'
    _description = 'Purchase Approval Level'
    _order = 'company_id, department_id, sequence'

    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company)
    department_id = fields.Many2one(
        'hr.department', string='Department',
        help='Leave empty for company-wide fallback levels.')
    sequence = fields.Integer(string='Approval Order', default=10)
    name = fields.Char(string='Level Name', required=True)
    min_amount = fields.Float(string='Minimum Amount', required=True)
    max_amount = fields.Float(
        string='Maximum Amount',
        help='Set to 0 for unlimited.')
    currency_id = fields.Many2one(
        'res.currency', required=True,
        default=lambda self: self.env.company.currency_id)
    approver_ids = fields.Many2many(
        'res.users',
        'co_approval_level_users_rel',
        'level_id', 'user_id',
        string='Authorized Approvers')
