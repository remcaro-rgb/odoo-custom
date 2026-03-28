from odoo import api, fields, models


class PmsRevenueLog(models.Model):
    _name = 'pms.revenue.log'
    _description = 'Revenue Change Log'
    _order = 'change_datetime desc'

    property_id = fields.Many2one(
        'pms.property',
        required=True,
        string='Property',
        ondelete='cascade',
    )
    room_type_id = fields.Many2one(
        'pms.room.type',
        required=True,
        string='Room Type',
        ondelete='cascade',
    )
    date = fields.Date(required=True, string='Date')
    old_rate = fields.Float(string='Old Rate')
    new_rate = fields.Float(string='New Rate')
    change_pct = fields.Float(
        compute='_compute_change_pct',
        string='Change %',
        store=True,
    )
    reason = fields.Char(string='Reason')
    changed_by = fields.Many2one('res.users', string='Changed By')
    change_datetime = fields.Datetime(
        string='Changed At',
        default=fields.Datetime.now,
    )

    @api.depends('old_rate', 'new_rate')
    def _compute_change_pct(self):
        for rec in self:
            if rec.old_rate:
                rec.change_pct = (
                    (rec.new_rate - rec.old_rate) / rec.old_rate
                ) * 100
            else:
                rec.change_pct = 0.0
