import logging

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SEAT_CAP_PARAM = 'saas.seat_cap'
TENANT_ID_PARAM = 'saas.tenant_id'


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        new_internal = [v for v in vals_list if not v.get('share')]
        if new_internal:
            self._saas_check_seat_cap(len(new_internal))
        return super().create(vals_list)

    def _saas_check_seat_cap(self, new_count):
        """Raise UserError if creating ``new_count`` more internal users would
        exceed ``saas.seat_cap``. A cap of 0 (or unset) means unlimited."""
        cap_raw = self.env['ir.config_parameter'].sudo().get_param(SEAT_CAP_PARAM, '0')
        try:
            cap = int(cap_raw)
        except (TypeError, ValueError):
            cap = 0
        if cap <= 0:
            return

        current = self.sudo().search_count([
            ('share', '=', False),
            ('active', '=', True),
        ])
        projected = current + new_count
        if projected > cap:
            self._saas_audit_rejection(current, cap, new_count)
            raise UserError(_(
                "Seat cap reached for this tenant (cap=%(cap)d, active=%(current)d, "
                "requested=+%(new)d). Upgrade the plan or deactivate unused users.",
                cap=cap, current=current, new=new_count,
            ))

    def _saas_audit_rejection(self, current, cap, new_count):
        tenant_id = self.env['ir.config_parameter'].sudo().get_param(
            TENANT_ID_PARAM, 'unset'
        )
        msg = (
            "saas_tenant_gate: seat cap rejection tenant=%s cap=%d active=%d requested=+%d"
            % (tenant_id, cap, current, new_count)
        )
        _logger.warning(msg)
        # The caller raises UserError immediately after this; that rolls back
        # the current transaction, taking the audit row with it. Write via a
        # fresh cursor so the audit survives the rollback.
        with self.pool.cursor() as audit_cr:
            audit_env = api.Environment(audit_cr, self.env.uid, self.env.context)
            audit_env['ir.logging'].sudo().create({
                'name': 'saas_tenant_gate',
                'type': 'server',
                'level': 'WARNING',
                'message': msg,
                'path': 'saas_tenant_gate.res_users',
                'func': '_saas_check_seat_cap',
                'line': '0',
            })
