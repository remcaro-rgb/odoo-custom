from odoo import fields, models, tools


class AccountBalanceSheet(models.Model):
    _name = 'account.balance.sheet'
    _description = 'Balance Sheet'
    _auto = False
    _order = 'account_code asc, id asc'
    _rec_name = 'move_name'

    _depends = {
        'account.move': ['name', 'date', 'state'],
        'account.move.line': [
            'move_id', 'account_id', 'partner_id',
            'debit', 'credit', 'company_id', 'parent_state',
        ],
        'account.account': ['code_store', 'name'],
        'res.company': ['currency_id'],
    }

    date = fields.Date(string='Date', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    account_code = fields.Char(string='Code', readonly=True)
    account_name = fields.Char(string='Account', translate=True, readonly=True)
    account_class = fields.Char(string='Class', readonly=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
    move_name = fields.Char(string='Reference', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    debit = fields.Monetary(string='Debit', currency_field='currency_id', readonly=True)
    credit = fields.Monetary(string='Credit', currency_field='currency_id', readonly=True)
    balance = fields.Monetary(string='Balance', currency_field='currency_id', readonly=True)
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
                aml.id                                                                    AS id,
                am.date                                                                   AS date,
                aml.account_id                                                            AS account_id,
                aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text)              AS account_code,
                aa.name                                                                   AS account_name,
                LEFT(aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text), 1)     AS account_class,
                aml.move_id                                                               AS move_id,
                am.name                                                                   AS move_name,
                aml.partner_id                                                            AS partner_id,
                aml.debit                                                                 AS debit,
                aml.credit                                                                AS credit,
                aml.debit - aml.credit                                                    AS balance,
                aml.company_id                                                            AS company_id,
                rc.id                                                                     AS currency_id
            FROM account_move_line aml
            JOIN account_move    am  ON am.id  = aml.move_id
            JOIN account_account aa  ON aa.id  = aml.account_id
            JOIN res_company     rco ON rco.id = aml.company_id
            JOIN res_currency    rc  ON rc.id  = rco.currency_id
            WHERE aml.parent_state = 'posted'
              AND LEFT(aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text), 1)
                  IN ('1', '2', '3')
        """
