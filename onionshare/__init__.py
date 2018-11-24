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

import os, sys, time, argparse, threading

from . import strings
from .common import Common
from .web import Web
from .onion import *
from .onionshare import OnionShare

def main(cwd=None):
    """
    The main() function implements all of the logic that the command-line version of
    onionshare uses.
    """
    common = Common()
    common.load_settings()
    strings.load_strings(common)

    # Parse arguments
    parser = argparse.ArgumentParser(formatter_class=lambda prog: argparse.HelpFormatter(prog,max_help_position=28))
    parser.add_argument('filename', metavar='filename', nargs='*', help=strings._('help_filename'))
    args = parser.parse_args()

    filenames = args.filename
    for i in range(len(filenames)):
        filenames[i] = os.path.abspath(filenames[i])

    # Create the Web object
    web = Web(common)

    # Start the Onion object
    onion = Onion(common)
    onion.connect()

    # Start the onionshare app
    app = OnionShare(common, onion)
    app.choose_port()
    app.start_onion_service()

    # Prepare files to share
    web.share_mode.set_file_info(filenames)
    app.cleanup_filenames += web.share_mode.cleanup_filenames

    # Start OnionShare http service in new thread
    t = threading.Thread(target=web.start, args=(app.port,))
    t.daemon = True
    t.start()

    try:  # Trap Ctrl-C
        # Build the URL
        print(app.onion_host)
        url = 'http://{0:s}/'.format(app.onion_host)

        print('')
        print(strings._("give_this_url"))
        print(url)
        print('')
        print(strings._("ctrlc_to_stop"))

        # Wait for app to close
        while t.is_alive():
            # Allow KeyboardInterrupt exception to be handled with threads
            # https://stackoverflow.com/questions/3788208/python-threading-ignores-keyboardinterrupt-exception
            time.sleep(0.2)
    except KeyboardInterrupt:
        web.stop(app.port)
    finally:
        # Shutdown
        app.cleanup()
        onion.cleanup()

if __name__ == '__main__':
    main()
