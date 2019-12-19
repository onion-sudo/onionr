"""Onionr - Private P2P Communication.

launch the api servers and communicator
"""
import os
import sys
import platform
import sqlite3
from threading import Thread
from gevent import time

import toomanyobjs

import config
import apiservers
import logger
import communicator
from onionrplugins import onionrevents as events
from netcontroller import NetController
from onionrutils import localcommand
import filepaths
from coredb import daemonqueue
from etc import onionrvalues, cleanup
from onionrcrypto import getourkeypair
from utils import hastor, logoheader
from . import version
import serializeddata
import runtests
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


def _proper_shutdown():
    localcommand.local_command('shutdown')
    sys.exit(1)


def daemon():
    """Start the Onionr communication daemon."""
    offline_mode = config.get('general.offline_mode', False)

    if not hastor.has_tor():
        offline_mode = True
        logger.error("Tor is not present in system path or Onionr directory",
                     terminal=True)

    # remove runcheck if it exists
    if os.path.isfile(filepaths.run_check_file):
        logger.debug('Runcheck file found on daemon start, deleting.')
        os.remove(filepaths.run_check_file)

    # Create shared objects

    shared_state = toomanyobjs.TooMany()

    Thread(target=shared_state.get(apiservers.ClientAPI).start,
           daemon=True, name='client HTTP API').start()
    if not offline_mode:
        Thread(target=shared_state.get(apiservers.PublicAPI).start,
               daemon=True, name='public HTTP API').start()

    # Init run time tester
    # (ensures Onionr is running right, for testing purposes)

    shared_state.get(runtests.OnionrRunTestManager)
    shared_state.get(serializeddata.SerializedData)
    shared_state.share_object()  # share the parent object to the threads

    apiHost = ''
    while apiHost == '':
        try:
            with open(filepaths.public_API_host_file, 'r') as hostFile:
                apiHost = hostFile.read()
        except FileNotFoundError:
            pass
        time.sleep(0.5)

    logger.raw('', terminal=True)
    # print nice header thing :)
    if config.get('general.display_header', True):
        logoheader.header()
    version.version(verbosity=5, function=logger.info)
    logger.debug('Python version %s' % platform.python_version())

    if onionrvalues.DEVELOPMENT_MODE:
        logger.warn('Development mode enabled', timestamp=False, terminal=True)

    net = NetController(config.get('client.public.port', 59497),
                        apiServerIP=apiHost)
    shared_state.add(net)

    if not offline_mode:
        logger.info('Tor is starting...', terminal=True)
        if not net.startTor():
            localcommand.local_command('shutdown')
            cleanup.delete_run_files()
            sys.exit(1)
        if len(net.myID) > 0 and config.get('general.security_level', 1) == 0:
            logger.debug('Started .onion service: %s' %
                         (logger.colors.underline + net.myID))
        else:
            logger.debug('.onion service disabled')

    logger.info('Using public key: %s' %
                (logger.colors.underline +
                 getourkeypair.get_keypair()[0][:52]))

    try:
        time.sleep(1)
    except KeyboardInterrupt:
        pass

    events.event('init', threaded=False)
    events.event('daemon_start')
    communicator.startCommunicator(shared_state)

    localcommand.local_command('shutdown')

    if not offline_mode:
        net.killTor()

    try:
        # Time to allow threads to finish,
        # if not any "daemon" threads will be slaughtered
        # http://docs.python.org/library/threading.html#threading.Thread.daemon
        time.sleep(5)
    except KeyboardInterrupt:
        pass
    cleanup.delete_run_files()


def _ignore_sigint(sig, frame):  # pylint: disable=W0612,W0613
    """Space intentionally left blank."""
    return


def kill_daemon():
    """Shutdown the Onionr daemon (communicator)."""
    logger.warn('Stopping the running daemon...', timestamp=False,
                terminal=True)

    # On platforms where we can, fork out to prevent locking
    try:
        pid = os.fork()
        if pid != 0:
            return
    except (AttributeError, OSError):
        pass

    events.event('daemon_stop')
    net = NetController(config.get('client.port', 59496))
    try:
        daemonqueue.daemon_queue_add('shutdown')
    except sqlite3.OperationalError:
        pass

    net.killTor()


kill_daemon.onionr_help = "Gracefully stops the "  # type: ignore
kill_daemon.onionr_help += "Onionr API servers"  # type: ignore


def start(override: bool = False):
    """If no lock file, make one and start onionr.

    Error exit if there is and its not overridden
    """
    if os.path.exists(filepaths.lock_file) and not override:
        logger.fatal('Cannot start. Daemon is already running,'
                     + ' or it did not exit cleanly.\n'
                     + ' (if you are sure that there is not a daemon running,'
                     + ' delete onionr.lock & try again).', terminal=True)
    else:
        if not onionrvalues.DEVELOPMENT_MODE:
            lock_file = open(filepaths.lock_file, 'w')
            lock_file.write('delete at your own risk')
            lock_file.close()

        # Start Onionr daemon
        daemon()

        try:
            os.remove(filepaths.lock_file)
        except FileNotFoundError:
            pass


start.onionr_help = "Start Onionr node "  # type: ignore
start.onionr_help += "(public and clients API servers)"  # type: ignore
