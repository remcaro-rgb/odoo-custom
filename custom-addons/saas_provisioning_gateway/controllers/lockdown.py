# Hardening: 404 the legacy /web/database/* surface.
#
# Even with list_db=False in odoo.conf, the database-manager endpoints
# still respond with HTTP 200 carrying the "The database manager has been
# disabled by the administrator" template. That confirms Odoo is running
# here — useful info-disclosure for an attacker fingerprinting the stack.
#
# We have no legitimate use for these endpoints in production:
#   - /web/database/create        replaced by /saas/provision (HMAC)
#   - /web/database/duplicate     unused
#   - /web/database/restore       unused (control-plane uses pgBackRest)
#   - /web/database/backup        unused (control-plane uses pgBackRest)
#   - /web/database/drop          unused
#   - /web/database/manager       unused
#   - /web/database/selector      unused (per-host dbfilter handles routing)
#   - /web/database/list          unused
#   - /web/database/change_password unused
#
# Override each with a 404 NotFound. Odoo's @http.route decoration is
# applied per-class-per-method; the runtime registers them in source-order,
# and the LAST controller registered wins for a duplicate route. Because
# saas_provisioning_gateway is loaded server-wide via --load AFTER the web
# addon's Database controller (which is in `base` deps), our route wins.
#
# Phase-2 HARDENING.md item 1 — at-the-Odoo equivalent for Railway tenants
# (which don't pass through our Traefik). Fly tenants get the same defense
# in depth here regardless of whether Traefik is in front of them yet.

from odoo import http
from odoo.exceptions import AccessDenied


class SaasDatabaseLockdown(http.Controller):

    # GET endpoints (browser-friendly probes)
    @http.route(
        ['/web/database/manager', '/web/database/selector'],
        type='http', auth='none', methods=['GET'], csrf=False,
    )
    def hidden_get(self, **kw):
        return http.request.not_found()

    # POST endpoints — keep the verb constraints Odoo's stock controller had,
    # so a GET still falls through to method-not-allowed rather than 404
    # disclosure-equivalent. The action ones (create/duplicate/...) are
    # @check_db_management_enabled-protected at the service layer; this is
    # defense in depth that prevents an attacker from even probing the
    # endpoint shape.
    @http.route(
        ['/web/database/duplicate',
         '/web/database/drop',
         '/web/database/backup',
         '/web/database/restore',
         '/web/database/change_password'],
        type='http', auth='none', methods=['POST'], csrf=False,
    )
    def hidden_post(self, **kw):
        # AccessDenied → Odoo converts to a generic auth-error response.
        # Better than 404 here because some legitimate-ish internal callers
        # might still hit these by mistake and a 404 would mask the real
        # reason. AccessDenied also shows up in audit logs cleanly.
        raise AccessDenied()

    # /web/database/list is type='json'; mirror that. Returns an empty
    # array to avoid leaking the actual db inventory.
    @http.route(
        '/web/database/list',
        type='json', auth='none', methods=['POST'], csrf=False,
    )
    def hidden_list_json(self, **kw):
        return []
