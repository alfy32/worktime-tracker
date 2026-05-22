#!/usr/bin/env python3
"""D-Bus lock/unlock listener — posts login/logout events to work time tracker.

Runs as a persistent systemd user service. Subscribes to
org.gnome.ScreenSaver.ActiveChanged on the session bus, which fires for
Super+L and all normal GNOME screen lock paths. On SIGTERM (shutdown) posts a
logout before exiting so the session end is recorded on reboot.
"""

import json
import os
import signal
import sys
import urllib.error
import urllib.request
from datetime import datetime

import dbus
import dbus.mainloop.glib
import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib

from sync import load_config


def _now_iso():
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def post_event(server_url, computer_name, action):
    """POST a single login or logout event. Returns (inserted, skipped)."""
    payload = json.dumps({
        'computer': computer_name,
        'events': [{'timestamp': _now_iso(), 'action': action}],
    }).encode()
    req = urllib.request.Request(
        server_url + '/api/sync',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            return body.get('inserted', 0), body.get('skipped', 0)
    except urllib.error.HTTPError as e:
        print(f'HTTP {e.code}: {e.read().decode()}', file=sys.stderr)
    except urllib.error.URLError as e:
        print(f'Connection error: {e.reason}', file=sys.stderr)
    return 0, 0


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    server_url, computer_name = load_config()

    try:
        bus = dbus.SessionBus()
    except dbus.DBusException as e:
        print(f'Cannot connect to D-Bus session bus: {e}', file=sys.stderr)
        sys.exit(1)

    loop = GLib.MainLoop()

    def on_active_changed(is_active):
        if is_active:
            inserted, _ = post_event(server_url, computer_name, 'logout')
            print(f'Screen locked — logout posted (inserted={inserted})', flush=True)
        else:
            inserted, _ = post_event(server_url, computer_name, 'login')
            print(f'Screen unlocked — login posted (inserted={inserted})', flush=True)

    def on_terminate(signum, frame):
        print('Shutting down — posting logout', flush=True)
        post_event(server_url, computer_name, 'logout')
        loop.quit()

    bus.add_signal_receiver(
        on_active_changed,
        signal_name='ActiveChanged',
        dbus_interface='org.gnome.ScreenSaver',
        path='/org/gnome/ScreenSaver',
    )

    signal.signal(signal.SIGTERM, on_terminate)
    signal.signal(signal.SIGINT, on_terminate)

    print('Listening for screen lock/unlock events', flush=True)
    loop.run()


if __name__ == '__main__':
    main()
