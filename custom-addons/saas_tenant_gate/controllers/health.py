from odoo import http
from odoo.http import request


class SaasHealthController(http.Controller):

    @http.route('/saas/health', type='http', auth='none', methods=['GET'], csrf=False)
    def health(self):
        env = request.env(su=True)
        config = env['ir.config_parameter'].sudo()
        return request.make_json_response({
            'ok': True,
            'database': env.cr.dbname,
            'tenant_id': config.get_param('saas.tenant_id', 'unset'),
        })
