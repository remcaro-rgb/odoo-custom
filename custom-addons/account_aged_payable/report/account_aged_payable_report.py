from odoo import models, fields
from odoo.tools.misc import formatLang


class AccountAgedPayableReport(models.AbstractModel):
    _name = 'report.account_aged_payable.account_aged_payable_document'
    _description = 'Aged Payable Report'

    def _fmt(self, amount, currency):
        """Format amount: negatives in parentheses, positives plain."""
        formatted = formatLang(self.env, abs(amount), currency_obj=currency)
        return f'({formatted})' if amount < 0 else formatted

    def _get_report_values(self, docids, data=None):
        lines = self.env['account.aged.payable'].browse(docids)
        currency = self.env.company.currency_id

        # Bucket display labels (ordered for columns)
        bucket_order = ['current', '1_30', '31_60', '61_90', '91_120', 'over_120']
        bucket_labels = {
            'current': 'Corriente',
            '1_30': '1-30',
            '31_60': '31-60',
            '61_90': '61-90',
            '91_120': '91-120',
            'over_120': '+120',
        }

        # Aggregate per partner per bucket
        partners = {}  # {partner_id: {name, buckets: {bucket: amount}, total}}
        for line in lines:
            pid = line.partner_id.id if line.partner_id else 0
            pname = line.partner_id.name if line.partner_id else '(Sin proveedor)'
            if pid not in partners:
                partners[pid] = {
                    'name': pname,
                    'buckets': {b: 0.0 for b in bucket_order},
                    'total': 0.0,
                }
            bucket = line.aging_bucket or 'current'
            partners[pid]['buckets'][bucket] += line.amount_residual
            partners[pid]['total'] += line.amount_residual

        # Build sorted rows — bucket_amounts is an ordered list matching bucket_order
        rows = []
        grand_totals = {b: 0.0 for b in bucket_order}
        grand_total = 0.0

        for pid in sorted(partners, key=lambda p: partners[p]['name']):
            pdata = partners[pid]
            row = {
                'partner': pdata['name'],
                'bucket_amounts': [
                    self._fmt(pdata['buckets'][b], currency)
                    for b in bucket_order
                ],
                'total': self._fmt(pdata['total'], currency),
            }
            rows.append(row)
            for b in bucket_order:
                grand_totals[b] += pdata['buckets'][b]
            grand_total += pdata['total']

        report_date = max(
            (l.date_maturity or l.date for l in lines if (l.date_maturity or l.date)),
            default=fields.Date.today(),
        )

        return {
            'doc_ids': docids,
            'rows': rows,
            'bucket_labels': [bucket_labels[b] for b in bucket_order],
            'grand_totals': [self._fmt(grand_totals[b], currency) for b in bucket_order],
            'grand_total': self._fmt(grand_total, currency),
            'company': self.env.company,
            'user': self.env.user,
            'report_date': report_date,
            'print_date': fields.Datetime.now(),
        }
