from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def color_scheme(self):
        if request and hasattr(request, 'httprequest'):
            scheme = request.httprequest.cookies.get('color_scheme')
            if scheme in ('dark', 'light'):
                return scheme
        return super().color_scheme()
