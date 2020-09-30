"""Onionr - Private P2P Communication.

Process incoming requests to the public api server for certain attacks
"""
from flask import Blueprint, request, abort, g
from onionrservices import httpheaders
from onionrutils import epoch
from utils import gettransports
"""
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""


class PublicAPISecurity:
    def __init__(self, public_api):
        public_api_security_bp = Blueprint('publicapisecurity', __name__)
        self.public_api_security_bp = public_api_security_bp

        @public_api_security_bp.before_app_request
        def validate_request():
            """Validate request has the correct hostname"""
            # If high security level, deny requests to public
            # (HS should be disabled anyway for Tor, but might not be for I2P)

            g.is_onionr_client = False
            transports = gettransports.get()
            if public_api.config.get('general.security_level', default=1) > 0:
                abort(403)

            if request.host not in transports:
                # Abort conn if wrong HTTP hostname, to prevent DNS rebinding
                if not public_api.config.get(
                        'general.allow_public_api_dns_rebinding', False):
                    abort(403)
            public_api.hitCount += 1  # raise hit count for valid requests
            try:
                if 'onionr' in request.headers['User-Agent'].lower():
                    g.is_onionr_client = True
                else:
                    g.is_onionr_client = False
            except KeyError:
                g.is_onionr_client = False
            # Add shared objects
            try:
                g.too_many = public_api._too_many
            except KeyError:
                g.too_many = None

        @public_api_security_bp.after_app_request
        def send_headers(resp):
            """Send api, access control headers"""
            resp = httpheaders.set_default_onionr_http_headers(resp)
            # Network API version
            resp.headers['X-API'] = public_api.API_VERSION
            resp.headers['Access-Control-Allow-Origin'] = "*"
            # Delete some HTTP headers for Onionr user agents
            NON_NETWORK_HEADERS = (
                'Content-Security-Policy', 'X-Frame-Options',
                'X-Content-Type-Options', 'Feature-Policy',
                'Clear-Site-Data', 'Referrer-Policy')

            # For other nodes, we don't need to waste bits on the above headers
            try:
                if g.is_onionr_client:
                    for header in NON_NETWORK_HEADERS:
                        del resp.headers[header]
                else:
                    del resp.headers['X-API']
            except AttributeError:
                abort(403)

            public_api.lastRequest = epoch.get_rounded_epoch(roundS=5)
            return resp
