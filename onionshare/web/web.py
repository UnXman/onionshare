import hmac
import logging
import os
import queue
import socket
import sys
import tempfile
from distutils.version import LooseVersion as Version
from urllib.request import urlopen

import flask
from flask import Flask, request, render_template, abort, make_response, __version__ as flask_version

from .. import strings

from .share_mode import ShareModeWeb

# Stub out flask's show_server_banner function, to avoiding showing warnings that
# are not applicable to OnionShare
def stubbed_show_server_banner(env, debug, app_import_path, eager_loading):
    pass

flask.cli.show_server_banner = stubbed_show_server_banner


class Web(object):
    """
    The Web object is the OnionShare web server, powered by flask
    """
    def __init__(self, common):
        self.common = common
        self.common.log('Web', '__init__')

        # The flask app
        self.app = Flask(__name__,
                         static_folder=self.common.get_resource_path('static'),
                         template_folder=self.common.get_resource_path('templates'))
        self.app.secret_key = self.common.random_string(8)

        self.debug_mode()

        self.security_headers = [
            ('Content-Security-Policy', 'default-src \'self\'; style-src \'self\'; script-src \'self\'; img-src \'self\' data:;'),
            ('X-Frame-Options', 'DENY'),
            ('X-Xss-Protection', '1; mode=block'),
            ('X-Content-Type-Options', 'nosniff'),
            ('Referrer-Policy', 'no-referrer'),
            ('Server', 'OnionShare')
        ]

        self.q = queue.Queue()
        self.error404_count = 0

        self.done = False

        # shutting down the server only works within the context of flask, so the easiest way to do it is over http
        self.shutdown_slug = self.common.random_string(16)

        # Keep track if the server is running
        self.running = False

        # Define the web app routes
        self.define_common_routes()

        # Create the mode web object, which defines its own routes
        self.share_mode = ShareModeWeb(self.common, self)

    def define_common_routes(self):
        """
        Common web app routes between sending and receiving
        """
        @self.app.errorhandler(404)
        def page_not_found(e):
            """
            404 error page.
            """
            return self.error404()

        @self.app.route("/<slug_candidate>/shutdown")
        def shutdown(slug_candidate):
            """
            Stop the flask web server, from the context of an http request.
            """
            self.check_shutdown_slug_candidate(slug_candidate)
            self.force_shutdown()
            return ""

    def error404(self):
        if request.path != '/favicon.ico':
            self.error404_count += 1

        r = make_response(render_template('404.html'), 404)
        return self.add_security_headers(r)

    def add_security_headers(self, r):
        """
        Add security headers to a request
        """
        for header, value in self.security_headers:
            r.headers.set(header, value)
        return r

    def _safe_select_jinja_autoescape(self, filename):
        if filename is None:
            return True
        return filename.endswith(('.html', '.htm', '.xml', '.xhtml'))

    def debug_mode(self):
        """
        Turn on debugging mode, which will log flask errors to a debug file.
        """
        temp_dir = tempfile.gettempdir()
        log_handler = logging.FileHandler(
            os.path.join(temp_dir, 'onionshare_server.log'))
        log_handler.setLevel(logging.WARNING)
        self.app.logger.addHandler(log_handler)

    def check_slug_candidate(self, slug_candidate):
        self.common.log('Web', 'check_slug_candidate: slug_candidate={}'.format(slug_candidate))
        if not hmac.compare_digest(self.slug, slug_candidate):
            abort(404)

    def check_shutdown_slug_candidate(self, slug_candidate):
        self.common.log('Web', 'check_shutdown_slug_candidate: slug_candidate={}'.format(slug_candidate))
        if not hmac.compare_digest(self.shutdown_slug, slug_candidate):
            abort(404)

    def force_shutdown(self):
        """
        Stop the flask web server, from the context of the flask app.
        """
        # Shutdown the flask service
        try:
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:
                raise RuntimeError('Not running with the Werkzeug Server')
            func()
        except:
            pass
        self.running = False

    def start(self, port):
        """
        Start the flask web server.
        """
        self.common.log('Web', 'start', 'port={}'.format(port))

        # In Whonix, listen on 0.0.0.0 instead of 127.0.0.1 (#220)
        if os.path.exists('/usr/share/anon-ws-base-files/workstation'):
            host = '0.0.0.0'
        else:
            host = '127.0.0.1'

        self.running = True
        self.app.run(host=host, port=port, threaded=True)

    def stop(self, port):
        """
        Stop the flask web server by loading /shutdown.
        """
        # If the user cancels the download, let the download function know to stop
        # serving the file
        self.share_mode.client_cancel = True

        # To stop flask, load http://127.0.0.1:<port>/<shutdown_slug>/shutdown
        if self.running:
            try:
                s = socket.socket()
                s.connect(('127.0.0.1', port))
                s.sendall('GET /{0:s}/shutdown HTTP/1.1\r\n\r\n'.format(self.shutdown_slug))
            except:
                try:
                    urlopen('http://127.0.0.1:{0:d}/{1:s}/shutdown'.format(port, self.shutdown_slug)).read()
                except:
                    pass
