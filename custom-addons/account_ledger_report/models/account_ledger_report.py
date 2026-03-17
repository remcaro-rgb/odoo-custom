from odoo import fields, models


class AccountLedgerReport(models.Model):
    _name = 'account.ledger.report'
    _description = 'Account Ledger Report'
    _auto = False
    _order = 'date desc, id desc'
    _rec_name = 'move_name'

    _depends = {
        'account.move': ['name', 'date', 'state'],
        'account.move.line': [
            'move_id', 'account_id', 'partner_id',
            'debit', 'credit', 'company_id', 'parent_state',
        ],
        'account.account': ['code_store'],  # code_store is the JSONB column backing the virtual `code` field
        'res.company': ['currency_id'],
    }

    date = fields.Date(string='Date', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    account_code = fields.Char(string='Code', readonly=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
    move_name = fields.Char(string='Reference', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    debit = fields.Monetary(string='Debit', readonly=True)
    credit = fields.Monetary(string='Credit', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    @property
    def _table_query(self):
        return """
            SELECT
                aml.id              AS id,
                am.date             AS date,
                aml.account_id      AS account_id,
                aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text) AS account_code,
                aml.move_id         AS move_id,
                am.name             AS move_name,
                aml.partner_id      AS partner_id,
                aml.debit           AS debit,
                aml.credit          AS credit,
                aml.company_id      AS company_id,
                rc.id               AS currency_id
            FROM account_move_line aml
            JOIN account_move    am  ON am.id  = aml.move_id
            JOIN account_account aa  ON aa.id  = aml.account_id
            JOIN res_company     rco ON rco.id = aml.company_id
            JOIN res_currency    rc  ON rc.id  = rco.currency_id
            WHERE aml.parent_state = 'posted'
        """
