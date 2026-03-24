from odoo import api, fields, models, _


class ClubStall(models.Model):
    _name = 'club.stall'
    _description = 'Club Stall'
    _rec_name = 'name'

    name = fields.Char(string='Stall Name', required=True)
    barn_section = fields.Char(string='Barn / Section')
    horse_id = fields.Many2one(
        'club.horse',
        string='Current Horse',
        compute='_compute_horse_id',
        search='_search_horse_id',
        readonly=True,
    )
    status = fields.Selection(
        [
            ('vacant', 'Vacant'),
            ('occupied', 'Occupied'),
            ('maintenance', 'Maintenance'),
        ],
        string='Status',
        compute='_compute_status',
        store=True,
        readonly=True,
    )
    under_maintenance = fields.Boolean(
        string='Under Maintenance',
        default=False,
    )
    notes = fields.Text(string='Notes')

    @api.depends_context('force_stall_recompute')
    def _compute_horse_id(self):
        """Compute horse_id by searching for a horse assigned to this stall."""
        Horse = self.env['club.horse']
        for stall in self:
            horse = Horse.search([('stall_id', '=', stall.id)], limit=1)
            stall.horse_id = horse.id if horse else False

    def _search_horse_id(self, operator, value):
        """Allow searching stalls by horse."""
        horses = self.env['club.horse'].search([('name', operator, value)])
        return [('id', 'in', horses.mapped('stall_id').ids)]

    @api.depends('under_maintenance')
    def _compute_status(self):
        """Status: maintenance > occupied > vacant.

        We must also look at live horse assignments; since horse_id is
        non-stored compute, we search each time.
        """
        Horse = self.env['club.horse']
        for stall in self:
            if stall.under_maintenance:
                stall.status = 'maintenance'
            else:
                horse = Horse.search([('stall_id', '=', stall.id)], limit=1)
                stall.status = 'occupied' if horse else 'vacant'
