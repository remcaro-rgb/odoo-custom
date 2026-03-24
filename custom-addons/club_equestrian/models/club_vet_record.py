from datetime import timedelta

from odoo import api, fields, models, _


class ClubVetRecord(models.Model):
    _name = 'club.vet.record'
    _inherit = ['mail.thread']
    _description = 'Veterinary Record'
    _rec_name = 'horse_id'
    _order = 'date desc'

    horse_id = fields.Many2one(
        'club.horse',
        string='Horse',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    date = fields.Date(
        string='Visit Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    vet_name = fields.Char(string='Veterinarian', required=True)
    procedure = fields.Text(string='Procedure / Diagnosis')
    next_visit_date = fields.Date(string='Next Scheduled Visit')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'club_vet_record_attachment_rel',
        'vet_record_id',
        'attachment_id',
        string='Attachments',
    )

    @api.model
    def _cron_check_vet_visits(self):
        """Send reminders on horse chatter for upcoming vet visits (within 7 days)."""
        today = fields.Date.context_today(self)
        deadline = today + timedelta(days=7)
        records = self.search([
            ('next_visit_date', '>=', today),
            ('next_visit_date', '<=', deadline),
        ])
        for rec in records:
            rec.horse_id.message_post(
                body=_(
                    "Reminder: Veterinary visit scheduled on %(date)s "
                    "with %(vet)s. Procedure: %(procedure)s",
                    date=rec.next_visit_date,
                    vet=rec.vet_name,
                    procedure=rec.procedure or _('N/A'),
                ),
                subject=_("Upcoming Vet Visit"),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
