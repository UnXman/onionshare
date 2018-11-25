# -*- coding: utf-8 -*-
"""
OnionShare | https://onionshare.org/

Copyright (C) 2014-2018 Micah Lee <micah@micahflee.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from stem.control import Controller
from stem import ProtocolError, SocketClosed
from stem.connection import MissingPassword, UnreadableCookieFile, AuthenticationFailure
import base64, os, sys, tempfile, shutil, urllib, platform, subprocess, time, shlex

from distutils.version import LooseVersion as Version
from . import onionkey
from . import common, strings
from .settings import Settings

class Onion(object):
    """
    Onion is an abstraction layer for connecting to the Tor control port and
    creating onion services. OnionShare supports creating onion services by
    connecting to the Tor controller and using ADD_ONION, DEL_ONION.

    stealth: Should the onion service be stealth?

    settings: A Settings object. If it's not passed in, load from disk.

    bundled_connection_func: If the tor connection type is bundled, optionally
    call this function and pass in a status string while connecting to tor. This
    is necessary for status updates to reach the GUI.
    """
    def __init__(self, common):
        self.common = common
        self.common.log('Onion', '__init__')
        self.service_id = None

    def connect(self):
        self.common.log('Onion', 'connect')
        self.settings = self.common.settings

        # Connect tor controller to Tor Browser's control port
        self.c = Controller.from_port(port=9151)
        self.c.authenticate()

        # Does this version of Tor support next-gen ('v3') onions?
        self.tor_version = self.c.get_version().version_str
        self.supports_next_gen_onions = self.tor_version > Version('0.3.3.1')

    def start_onion_service(self, port):
        """
        Start a onion service on port 80, pointing to the given port, and
        return the onion hostname.
        """
        self.common.log('Onion', 'start_onion_service')
        print(strings._("config_onion_service").format(int(port)))

        # Generate a v3 onion key
        key_type = "ED25519-V3"
        key_content = onionkey.generate_v3_private_key()[0]

        # Create onion service
        res = self.c.create_ephemeral_hidden_service({ 80: port }, await_publication=True, key_type=key_type, key_content=key_content)
        self.service_id = res.service_id
        onion_host = self.service_id + '.onion'
        return onion_host

    def cleanup(self):
        """
        Stop onion services that were created earlier. If there's a tor subprocess running, kill it.
        """
        self.common.log('Onion', 'cleanup')

        # Cleanup the ephemeral onion services, if we have any
        try:
            onions = self.c.list_ephemeral_hidden_services()
            for onion in onions:
                try:
                    self.common.log('Onion', 'cleanup', 'trying to remove onion {}'.format(onion))
                    self.c.remove_ephemeral_hidden_service(onion)
                except:
                    self.common.log('Onion', 'cleanup', 'could not remove onion {}.. moving on anyway'.format(onion))
                    pass
            self.service_id = None

        except:
            pass

    def get_tor_socks_port(self):
        """
        Returns a (address, port) tuple for the Tor SOCKS port
        """
        return ('127.0.0.1', 9150)
