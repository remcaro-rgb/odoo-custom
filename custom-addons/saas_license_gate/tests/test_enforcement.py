# Enforcement-layer tests for saas_license_gate.
#
# Run against a real Odoo test DB:
#   docker compose exec odoo odoo-bin -d test_license_gate \
#       -i saas_license_gate --test-enable \
#       --test-tags /saas_license_gate --stop-after-init

import time

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

_CFG_STATUS = 'saas.license.status'
_CFG_CHECKED_AT = 'saas.license.checked_at'


@tagged('post_install', '-at_install', 'saas_license_gate')
class TestEnforcementMatrix(TransactionCase):
    """Verify the enforcement matrix from models/enforcement.py."""

    def setUp(self):
        super().setUp()
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.ICP.set_param(_CFG_CHECKED_AT, str(int(time.time())))
        self.partner = self.env['res.partner'].create({
            'name': 'License Test Partner',
        })

    def _set_status(self, status):
        self.ICP.set_param(_CFG_STATUS, status)

    def _move_vals(self):
        return {
            'move_type': 'entry',
            'partner_id': self.partner.id,
            'date': fields.Date.today(),
        }

    def test_account_move_active_allows_create(self):
        self._set_status('active')
        move = self.env['account.move'].create(self._move_vals())
        self.assertTrue(move.id)

    def test_account_move_grace_allows_create(self):
        """DIAN escape hatch — account.move stays writable in grace."""
        self._set_status('grace')
        move = self.env['account.move'].create(self._move_vals())
        self.assertTrue(move.id)

    def test_account_move_expired_blocks_create(self):
        self._set_status('expired')
        with self.assertRaises(UserError) as cm:
            self.env['account.move'].create(self._move_vals())
        self.assertIn('License invalid (expired)', str(cm.exception))

    def test_account_move_revoked_blocks_create(self):
        self._set_status('revoked')
        with self.assertRaises(UserError):
            self.env['account.move'].create(self._move_vals())

    def test_account_move_bad_signature_blocks_create(self):
        self._set_status('bad-signature')
        with self.assertRaises(UserError):
            self.env['account.move'].create(self._move_vals())

    def test_account_move_grace_allows_write(self):
        self._set_status('active')
        move = self.env['account.move'].create(self._move_vals())
        self._set_status('grace')
        move.write({'ref': 'updated in grace'})
        self.assertEqual(move.ref, 'updated in grace')

    def _sale_vals(self):
        return {'partner_id': self.partner.id}

    def test_sale_order_active_allows_create(self):
        self._set_status('active')
        so = self.env['sale.order'].create(self._sale_vals())
        self.assertTrue(so.id)

    def test_sale_order_grace_blocks_create(self):
        """No DIAN escape hatch for sales — blocked in grace."""
        self._set_status('grace')
        with self.assertRaises(UserError) as cm:
            self.env['sale.order'].create(self._sale_vals())
        self.assertIn('License invalid (grace)', str(cm.exception))

    def test_sale_order_expired_blocks_create(self):
        self._set_status('expired')
        with self.assertRaises(UserError):
            self.env['sale.order'].create(self._sale_vals())

    def test_sale_order_grace_blocks_write(self):
        self._set_status('active')
        so = self.env['sale.order'].create(self._sale_vals())
        self._set_status('grace')
        with self.assertRaises(UserError):
            so.write({'note': 'shouldnt work'})

    def _picking_vals(self):
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
        ], limit=1)
        return {
            'partner_id': self.partner.id,
            'picking_type_id': picking_type.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
        }

    def test_stock_picking_active_allows_create(self):
        self._set_status('active')
        picking = self.env['stock.picking'].create(self._picking_vals())
        self.assertTrue(picking.id)

    def test_stock_picking_grace_blocks_create(self):
        self._set_status('grace')
        with self.assertRaises(UserError):
            self.env['stock.picking'].create(self._picking_vals())

    def test_stock_picking_revoked_blocks_create(self):
        self._set_status('revoked')
        with self.assertRaises(UserError):
            self.env['stock.picking'].create(self._picking_vals())

    def test_stale_blocks_create(self):
        """Setting checked_at >14 days ago triggers stale state, which
        blocks even if last cached status was 'active'."""
        self._set_status('active')
        self.ICP.set_param(
            _CFG_CHECKED_AT,
            str(int(time.time()) - 15 * 24 * 3600),
        )
        with self.assertRaises(UserError) as cm:
            self.env['sale.order'].create(self._sale_vals())
        self.assertIn('License invalid (stale)', str(cm.exception))
