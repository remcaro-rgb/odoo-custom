from odoo import fields, models, tools


class AccountAgedReceivable(models.Model):
    _name = 'account.aged.receivable'
    _description = 'Aged Receivable'
    _auto = False
    _order = 'partner_id asc, days_overdue asc'
    _rec_name = 'move_name'

    _depends = {
        'account.move': ['name', 'date', 'state'],
        'account.move.line': [
            'move_id', 'account_id', 'partner_id',
            'balance', 'amount_residual', 'reconciled',
            'date_maturity', 'company_id', 'parent_state',
        ],
        'account.account': ['account_type'],
        'res.company': ['currency_id'],
    }

    date = fields.Date(string='Date', readonly=True)
    date_maturity = fields.Date(string='Due Date', readonly=True)
    days_overdue = fields.Integer(string='Days Overdue', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
    move_name = fields.Char(string='Invoice', readonly=True)
    amount_total = fields.Monetary(
        string='Invoice Amount', currency_field='currency_id', readonly=True)
    amount_residual = fields.Monetary(
        string='Balance Due', currency_field='currency_id', readonly=True)
    aging_bucket = fields.Char(string='Aging Bucket', readonly=True)
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
                aml.id                                                                          AS id,
                am.date                                                                         AS date,
                COALESCE(aml.date_maturity, am.date)                                            AS date_maturity,
                (CURRENT_DATE - COALESCE(aml.date_maturity, am.date))::integer                 AS days_overdue,
                aml.partner_id                                                                  AS partner_id,
                aml.account_id                                                                  AS account_id,
                aml.move_id                                                                     AS move_id,
                am.name                                                                         AS move_name,
                -aml.balance                                                                    AS amount_total,
                aml.amount_residual                                                             AS amount_residual,
                CASE
                    WHEN (CURRENT_DATE - COALESCE(aml.date_maturity, am.date)) <= 0  THEN 'current'
                    WHEN (CURRENT_DATE - COALESCE(aml.date_maturity, am.date)) <= 30 THEN '1_30'
                    WHEN (CURRENT_DATE - COALESCE(aml.date_maturity, am.date)) <= 60 THEN '31_60'
                    WHEN (CURRENT_DATE - COALESCE(aml.date_maturity, am.date)) <= 90 THEN '61_90'
                    WHEN (CURRENT_DATE - COALESCE(aml.date_maturity, am.date)) <= 120 THEN '91_120'
                    ELSE 'over_120'
                END                                                                             AS aging_bucket,
                aml.company_id                                                                  AS company_id,
                rc.id                                                                           AS currency_id
            FROM account_move_line    aml
            JOIN account_move         am  ON am.id  = aml.move_id
            JOIN account_account      aa  ON aa.id  = aml.account_id
            JOIN res_company          rco ON rco.id = aml.company_id
            JOIN res_currency         rc  ON rc.id  = rco.currency_id
            WHERE aml.parent_state = 'posted'
              AND aa.account_type  = 'asset_receivable'
              AND aml.reconciled   = false
        """
