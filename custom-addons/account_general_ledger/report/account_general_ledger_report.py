from odoo import models, fields
from odoo.tools.misc import formatLang


class AccountGeneralLedgerReport(models.AbstractModel):
    _name = 'report.account_general_ledger.account_general_ledger_document'
    _description = 'General Ledger Report'

    def _fmt(self, amount, currency):
        """Format amount: negatives in parentheses, positives plain."""
        formatted = formatLang(self.env, abs(amount), currency_obj=currency)
        return f'({formatted})' if amount < 0 else formatted

    def _get_report_values(self, docids, data=None):
        lines = self.env['account.general.ledger'].browse(docids)
        currency = self.env.company.currency_id

        # Group lines by account, preserving date/id order within each account
        accounts_map = {}  # {account_id: {...}}
        for line in lines.sorted(key=lambda l: (l.account_code or '', l.date or fields.Date.today(), l.id)):
            acct_id = line.account_id.id
            if acct_id not in accounts_map:
                accounts_map[acct_id] = {
                    'account_code': line.account_code or '',
                    'account_name': line.account_name or '',
                    'lines': [],
                    'total_debit': 0.0,
                    'total_credit': 0.0,
                }
            accounts_map[acct_id]['lines'].append({
                'date': line.date,
                'move_name': line.move_name or '',
                'partner_name': line.partner_id.name or '' if line.partner_id else '',
                'debit_fmt': self._fmt(line.debit, currency) if line.debit else '',
                'credit_fmt': self._fmt(line.credit, currency) if line.credit else '',
                'cumulative_balance_fmt': self._fmt(line.cumulative_balance, currency),
            })
            accounts_map[acct_id]['total_debit'] += line.debit
            accounts_map[acct_id]['total_credit'] += line.credit

        # Build sorted list of accounts with formatted totals and final balance
        accounts = []
        for acct_data in sorted(accounts_map.values(), key=lambda x: x['account_code']):
            final_balance = acct_data['total_debit'] - acct_data['total_credit']
            accounts.append({
                'account_code': acct_data['account_code'],
                'account_name': acct_data['account_name'],
                'lines': acct_data['lines'],
                'total_debit_fmt': self._fmt(acct_data['total_debit'], currency),
                'total_credit_fmt': self._fmt(acct_data['total_credit'], currency),
                'final_balance_fmt': self._fmt(final_balance, currency),
            })

        # Date range: min and max dates across all selected lines
        dates = [l.date for l in lines if l.date]
        date_from = min(dates) if dates else fields.Date.today()
        date_to = max(dates) if dates else fields.Date.today()

        return {
            'doc_ids': docids,
            'accounts': accounts,
            'date_from': date_from,
            'date_to': date_to,
            'company': self.env.company,
            'user': self.env.user,
            'print_date': fields.Datetime.now(),
        }
