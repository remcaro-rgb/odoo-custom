from odoo import models, fields
from odoo.tools.misc import formatLang


BUCKET_ORDER = ['current', '1_30', '31_60', '61_90', '91_120', 'over_120']
BUCKET_LABELS = {
    'current':  'No Vencido',
    '1_30':     '1-30 días',
    '31_60':    '31-60 días',
    '61_90':    '61-90 días',
    '91_120':   '91-120 días',
    'over_120': '+120 días',
}


class AccountAgedReceivableReport(models.AbstractModel):
    _name = 'report.account_aged_receivable.account_aged_receivable_document'
    _description = 'Aged Receivable Report'

    def _fmt(self, amount, currency):
        """Format monetary amount; negatives in parentheses."""
        formatted = formatLang(self.env, abs(amount), currency_obj=currency)
        return '({})'.format(formatted) if amount < 0 else formatted

    def _get_report_values(self, docids, data=None):
        lines = self.env['account.aged.receivable'].browse(docids)
        currency = self.env.company.currency_id

        # Group lines by partner
        partners = {}  # {partner_id: {'name': str, 'buckets': {bucket: total}, 'lines': [...]}}
        for line in lines.sorted(key=lambda l: (l.partner_id.name or '', l.days_overdue)):
            pid = line.partner_id.id
            if pid not in partners:
                partners[pid] = {
                    'name': line.partner_id.name or 'Sin Contacto',
                    'buckets': {b: 0.0 for b in BUCKET_ORDER},
                    'total': 0.0,
                }
            bucket = line.aging_bucket or 'current'
            residual = line.amount_residual or 0.0
            partners[pid]['buckets'][bucket] += residual
            partners[pid]['total'] += residual

        # Build partner rows with pre-formatted amounts
        partner_rows = []
        bucket_totals = {b: 0.0 for b in BUCKET_ORDER}
        grand_total = 0.0

        for pid, pdata in partners.items():
            row = {
                'name': pdata['name'],
                'buckets_fmt': {},
                'total_fmt': self._fmt(pdata['total'], currency),
            }
            for bucket in BUCKET_ORDER:
                amt = pdata['buckets'][bucket]
                row['buckets_fmt'][bucket] = self._fmt(amt, currency) if amt else ''
                bucket_totals[bucket] += amt
            grand_total += pdata['total']
            partner_rows.append(row)

        # Format bucket totals footer
        bucket_totals_fmt = {
            b: self._fmt(bucket_totals[b], currency) for b in BUCKET_ORDER
        }
        grand_total_fmt = self._fmt(grand_total, currency)

        report_date = fields.Date.today().strftime('%d/%m/%Y')
        print_date = fields.Datetime.now()

        return {
            'doc_ids': docids,
            'partner_rows': partner_rows,
            'bucket_labels': BUCKET_LABELS,
            'bucket_order': BUCKET_ORDER,
            'bucket_totals_fmt': bucket_totals_fmt,
            'grand_total_fmt': grand_total_fmt,
            'report_date': report_date,
            'company': self.env.company,
            'user': self.env.user,
            'print_date': print_date,
        }
