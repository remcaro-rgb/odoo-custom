from odoo import models, fields
from odoo.tools.misc import formatLang


class AccountProfitLossReport(models.AbstractModel):
    _name = 'report.account_profit_loss.account_profit_loss_document'
    _description = 'Profit & Loss Report'

    def _fmt(self, amount, currency):
        """Format amount: negatives in parentheses, positives plain."""
        formatted = formatLang(self.env, abs(amount), currency_obj=currency)
        return f'({formatted})' if amount < 0 else formatted

    def _get_report_values(self, docids, data=None):
        lines = self.env['account.profit.loss'].browse(docids)
        currency = self.env.company.currency_id

        # Aggregate debit/credit per class per account (sorted by account_code)
        aggregated = {}  # {class: {account_id: {code, name, debit, credit}}}
        for line in lines.sorted(key=lambda l: (l.account_class or '', l.account_code or '')):
            cls = line.account_class or '?'
            acct_id = line.account_id.id
            if cls not in aggregated:
                aggregated[cls] = {}
            if acct_id not in aggregated[cls]:
                aggregated[cls][acct_id] = {
                    'account_code': line.account_code or '',
                    'account_name': line.account_name or '',
                    'debit': 0.0,
                    'credit': 0.0,
                }
            aggregated[cls][acct_id]['debit'] += line.debit
            aggregated[cls][acct_id]['credit'] += line.credit

        # Build structured sections with sign convention:
        # Class 4 (INGRESOS):        saldo = credit - debit  (revenue is credit-normal)
        # Class 6 (COSTOS DE VENTAS): saldo = debit - credit  (cost is debit-normal)
        # Class 5 (GASTOS):          saldo = debit - credit  (expense is debit-normal)
        class_labels = {
            '4': 'INGRESOS',
            '6': 'COSTOS DE VENTAS',
            '5': 'GASTOS',
        }
        sections = []
        totals = {'4': 0.0, '5': 0.0, '6': 0.0}

        for cls in ['4', '6', '5']:
            accounts = []
            for acct_data in sorted(
                aggregated.get(cls, {}).values(),
                key=lambda x: x['account_code'],
            ):
                raw = acct_data['debit'] - acct_data['credit']
                # Revenue (class 4): invert sign so credits show as positive
                saldo = -raw if cls == '4' else raw
                accounts.append({
                    'account_code': acct_data['account_code'],
                    'account_name': acct_data['account_name'],
                    'saldo_fmt': self._fmt(saldo, currency),
                })
                totals[cls] += saldo

            sections.append({
                'class': cls,
                'label': class_labels[cls],
                'accounts': accounts,
                'total_fmt': self._fmt(totals[cls], currency),
            })

        # Summary calculations
        total_ingresos = totals['4']
        total_costos = totals['6']
        total_gastos = totals['5']
        utilidad_bruta = total_ingresos - total_costos
        utilidad_operacional = utilidad_bruta - total_gastos

        # Date range
        dates = [l.date for l in lines if l.date]
        date_from = min(dates) if dates else fields.Date.today()
        date_to = max(dates) if dates else fields.Date.today()

        return {
            'doc_ids': docids,
            'sections': sections,
            'total_ingresos_fmt': self._fmt(total_ingresos, currency),
            'total_costos_fmt': self._fmt(total_costos, currency),
            'utilidad_bruta_fmt': self._fmt(utilidad_bruta, currency),
            'total_gastos_fmt': self._fmt(total_gastos, currency),
            'utilidad_operacional_fmt': self._fmt(utilidad_operacional, currency),
            'utilidad_operacional_positive': utilidad_operacional >= 0,
            'company': self.env.company,
            'user': self.env.user,
            'date_from': date_from,
            'date_to': date_to,
            'print_date': fields.Datetime.now(),
        }
