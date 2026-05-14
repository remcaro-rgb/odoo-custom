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
# Override each with a 404 NotFound. We SUBCLASS the stock Database
# controller and override its methods so Python's MRO determines the
# winner regardless of route-registration order. A sibling http.Controller
# (the original approach) only wins for db-context requests; nodb
# requests go through a different resolution path that picks the
# earliest-registered route — which is the stock one because the web
# addon loads before saas_provisioning_gateway.
#
# Phase-2 HARDENING.md item 1 — at-the-Odoo equivalent for Railway tenants
# (which don't pass through our Traefik). Fly tenants get the same defense
# in depth here regardless of whether Traefik is in front of them yet.

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.addons.web.controllers.database import Database


class SaasDatabaseLockdown(Database):

    # GET surfaces — the most common fingerprinting probe. 404 hides the
    # endpoint shape entirely.
    @http.route(
        '/web/database/manager',
        type='http', auth='none', methods=['GET'], csrf=False,
    )
    def manager(self, **kw):
        return http.request.not_found()

    @http.route(
        '/web/database/selector',
        type='http', auth='none', methods=['GET'], csrf=False,
    )
    def selector(self, **kw):
        return http.request.not_found()

    # POST verbs that mutate state — keep the verb constraints stock had,
    # so a GET still falls through to method-not-allowed rather than 404
    # disclosure-equivalent. The action ones are
    # @check_db_management_enabled-protected at the service layer; this is
    # defense in depth that prevents an attacker from even probing the
    # endpoint shape. AccessDenied → Odoo converts to a generic auth-error
    # response (better than 404 here because legitimate internal callers
    # see a clear "you can't do this" instead of "doesn't exist").
    @http.route(
        '/web/database/duplicate',
        type='http', auth='none', methods=['POST'], csrf=False,
    )
    def duplicate(self, master_pwd=None, name=None, new_name=None, **kw):
        raise AccessDenied()

    @http.route(
        '/web/database/drop',
        type='http', auth='none', methods=['POST'], csrf=False,
    )
    def drop(self, master_pwd=None, name=None, **kw):
        raise AccessDenied()

    @http.route(
        '/web/database/backup',
        type='http', auth='none', methods=['POST'], csrf=False,
    )
    def backup(self, master_pwd=None, name=None, backup_format='zip', **kw):
        raise AccessDenied()

    @http.route(
        '/web/database/restore',
        type='http', auth='none', methods=['POST'], csrf=False,
    )
    def restore(self, master_pwd=None, backup_file=None, name=None, copy=False, **kw):
        raise AccessDenied()

    @http.route(
        '/web/database/change_password',
        type='http', auth='none', methods=['POST'], csrf=False,
    )
    def change_password(self, master_pwd=None, master_pwd_new=None, **kw):
        raise AccessDenied()

    # /web/database/list is type='json'; mirror that. Returns an empty
    # array to avoid leaking the actual db inventory.
    @http.route(
        '/web/database/list',
        type='json', auth='none', methods=['POST'], csrf=False,
    )
    def list(self, **kw):
        return []

    # NOTE: /web/database/create is intentionally NOT overridden here.
    # The stock implementation is already gated by list_db=False at the
    # service layer (@check_db_management_enabled), and we expose a
    # replacement at /saas/provision (controllers/provision.py) that the
    # control plane calls with an HMAC signature.
