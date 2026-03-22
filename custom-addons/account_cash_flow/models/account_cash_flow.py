from odoo import fields, models, tools


class AccountCashFlow(models.Model):
    _name = 'account.cash.flow'
    _description = 'Cash Flow Statement'
    _auto = False
    _order = 'date desc, id desc'
    _rec_name = 'move_name'

    _depends = {
        'account.move': ['name', 'date', 'state', 'journal_id'],
        'account.move.line': [
            'move_id', 'account_id', 'partner_id',
            'debit', 'credit', 'company_id', 'parent_state',
        ],
        'account.account': ['code_store', 'name', 'account_type'],
        'account.journal': ['name', 'type'],
        'res.company': ['currency_id'],
    }

    date = fields.Date(string='Date', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    account_code = fields.Char(string='Code', readonly=True)
    account_name = fields.Char(string='Account', translate=True, readonly=True)
    journal_id = fields.Many2one('account.journal', string='Journal', readonly=True)
    journal_name = fields.Char(string='Journal Name', readonly=True)
    journal_type = fields.Char(string='Journal Type', readonly=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
    move_name = fields.Char(string='Reference', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    cash_in = fields.Monetary(
        string='Entradas', currency_field='currency_id', readonly=True)
    cash_out = fields.Monetary(
        string='Salidas', currency_field='currency_id', readonly=True)
    net_flow = fields.Monetary(
        string='Flujo Neto', currency_field='currency_id', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute("""
            CREATE OR REPLACE VIEW %s AS (%s)
        """ % (self._table, self._table_query))

    @property
    def _table_query(self):
        return """
            SELECT
                aml.id                                                                      AS id,
                am.date                                                                     AS date,
                aml.account_id                                                              AS account_id,
                aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text)                AS account_code,
                aa.name                                                                     AS account_name,
                am.journal_id                                                               AS journal_id,
                aj.name                                                                     AS journal_name,
                aj.type                                                                     AS journal_type,
                aml.move_id                                                                 AS move_id,
                am.name                                                                     AS move_name,
                aml.partner_id                                                              AS partner_id,
                aml.debit                                                                   AS cash_in,
                aml.credit                                                                  AS cash_out,
                aml.debit - aml.credit                                                      AS net_flow,
                aml.company_id                                                              AS company_id,
                rc.id                                                                       AS currency_id
            FROM account_move_line  aml
            JOIN account_move       am  ON am.id  = aml.move_id
            JOIN account_journal    aj  ON aj.id  = am.journal_id
            JOIN account_account    aa  ON aa.id  = aml.account_id
            JOIN res_company        rco ON rco.id = aml.company_id
            JOIN res_currency       rc  ON rc.id  = rco.currency_id
            WHERE aml.parent_state = 'posted'
              AND aa.account_type  = 'asset_cash'
        """
