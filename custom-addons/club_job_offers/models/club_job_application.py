from odoo import fields, models


class ClubJobApplication(models.Model):
    _name = 'club.job.application'
    _description = 'Job Application'
    _order = 'submit_date desc, id desc'
    _rec_name = 'applicant_name'

    offer_id = fields.Many2one(
        'club.job.offer',
        required=True,
        ondelete='cascade',
        string='Job Offer',
    )
    applicant_affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Recommending Affiliate',
    )
    applicant_name = fields.Char(required=True, string='Applicant Name')
    applicant_phone = fields.Char(string='Phone')
    applicant_email = fields.Char(string='Email')
    cover_note = fields.Text(string='Cover Note')
    status = fields.Selection(
        [
            ('submitted', 'Submitted'),
            ('reviewed', 'Reviewed'),
            ('accepted', 'Accepted'),
            ('rejected', 'Rejected'),
        ],
        default='submitted',
        required=True,
    )
    submit_date = fields.Date(
        string='Submit Date',
        default=fields.Date.context_today,
    )
    notes = fields.Text()
