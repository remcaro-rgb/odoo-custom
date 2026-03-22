from odoo import models, fields
from odoo.tools.misc import formatLang


class AccountCashFlowReport(models.AbstractModel):
    _name = 'report.account_cash_flow.account_cash_flow_document'
    _description = 'Cash Flow Statement Report'

    def _fmt(self, amount, currency):
        """Format amount with currency symbol; zero returns '0.00'."""
        return formatLang(self.env, amount, currency_obj=currency)

    def _get_report_values(self, docids, data=None):
        # Deduplicate docids — grouped list views can pass the same ID multiple times
        docids = list(dict.fromkeys(docids))
        lines = self.env['account.cash.flow'].browse(docids)
        currency = self.env.company.currency_id

        # Resolve journal names via direct SQL JSONB extraction.
        # account.journal.name is a translated Char stored as JSONB in Odoo 18;
        # ORM context tricks don't reliably unwrap it in report rendering, so we
        # query the column directly and extract the value for the user's language.
        lang = self.env.user.lang or self.env.lang or 'en_US'
        journal_ids = list({line.journal_id.id for line in lines if line.journal_id})
        journal_name_map = {}
        if journal_ids:
            self.env.cr.execute(
                """
                SELECT id,
                       COALESCE(
                           name->>%s,
                           name->>'en_US',
                           name::text
                       )
                FROM account_journal
                WHERE id = ANY(%s)
                """,
                (lang, journal_ids),
            )
            journal_name_map = dict(self.env.cr.fetchall())

        # --- Group lines by journal_id ---
        journals_map = {}   # {journal_id: {meta, lines_list}}
        for line in lines.sorted(key=lambda l: (l.journal_id.id, l.date or fields.Date.today(), l.id)):
            jid = line.journal_id.id
            if jid not in journals_map:
                journals_map[jid] = {
                    'journal_id': jid,
                    'journal_name': journal_name_map.get(jid) or '',
                    'journal_type': line.journal_type or '',
                    'lines': [],
                    'total_cash_in': 0.0,
                    'total_cash_out': 0.0,
                    'total_net_flow': 0.0,
                }
            journals_map[jid]['lines'].append({
                'date': line.date,
                'move_name': line.move_name or '',
                'partner_name': line.partner_id.name if line.partner_id else '',
                'cash_in_fmt': self._fmt(line.cash_in, currency),
                'cash_in_raw': line.cash_in,
                'cash_out_fmt': self._fmt(line.cash_out, currency),
                'cash_out_raw': line.cash_out,
                # net_flow_fmt uses abs so template wraps negative in parentheses cleanly
                'net_flow_fmt': self._fmt(abs(line.net_flow), currency),
                'net_flow_raw': line.net_flow,
            })
            journals_map[jid]['total_cash_in'] += line.cash_in
            journals_map[jid]['total_cash_out'] += line.cash_out
            journals_map[jid]['total_net_flow'] += line.net_flow

        # Sort journals: bank first, then cash, then rest — alphabetically within each type
        type_order = {'bank': 0, 'cash': 1}
        journals = sorted(
            journals_map.values(),
            key=lambda j: (type_order.get(j['journal_type'], 2), j['journal_name']),
        )

        # Format journal totals
        for j in journals:
            j['total_cash_in_fmt'] = self._fmt(j['total_cash_in'], currency)
            j['total_cash_out_fmt'] = self._fmt(j['total_cash_out'], currency)
            # use abs so template wraps negative in parentheses cleanly
            j['total_net_flow_fmt'] = self._fmt(abs(j['total_net_flow']), currency)
            j['total_net_flow_positive'] = j['total_net_flow'] >= 0

        # --- Grand totals ---
        grand_total_in = sum(j['total_cash_in'] for j in journals)
        grand_total_out = sum(j['total_cash_out'] for j in journals)
        grand_net_flow = sum(j['total_net_flow'] for j in journals)

        # --- Date range ---
        dates = [l.date for l in lines if l.date]
        date_from = min(dates) if dates else fields.Date.today()
        date_to = max(dates) if dates else fields.Date.today()

        return {
            'doc_ids': docids,
            'journals': journals,
            'grand_total_in_fmt': self._fmt(grand_total_in, currency),
            'grand_total_out_fmt': self._fmt(grand_total_out, currency),
            # use abs so template wraps negative in parentheses cleanly
            'grand_net_flow_fmt': self._fmt(abs(grand_net_flow), currency),
            'grand_net_flow_positive': grand_net_flow >= 0,
            'date_from': date_from,
            'date_to': date_to,
            'company': self.env.company,
            'user': self.env.user,
            'print_date': fields.Datetime.now(),
        }
