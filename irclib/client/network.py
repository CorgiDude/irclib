#!/usr/bin/env python3

import errno
import warnings
import socket
import logging

from random import choice, randint
from threading import Timer, Lock

from irclib.common.line import Line

try:
    import ssl
except ImportError:
    warnings.warn('Could not load SSL implementation, SSL will not work!',
                  RuntimeWarning)
    ssl = None


def randomstr():
    validstr = string.ascii_letters + string.digits
    return ''.join([choice(validstr) for x in range(randint(5, 20))])


class IRCClientNetwork:
    def __init__(self, **kwargs):
        self.host = kwargs.get('host')
        self.port = kwargs.get('port')
        self.use_ssl = kwargs.get('use_ssl', False)
        self.use_starttls = kwargs.get('use_starttls', True)
        self.hs_callback = kwargs.get('handshake_cb')

        if any(e is None for e in (self.host, self.port)):
            raise RuntimeError('No valid host or port specified')

        if ssl is None:
            if self.use_ssl:
                # Explicit SSL use
                raise RuntimeError('SSL support is unavailable')
            elif self.use_starttls:
                # Implicit SSL use
                warnings.warn('Unable to use STARTTLS; SSL support is unavailable')
                self.use_starttls = False
        elif self.use_ssl:
            # Unneeded and probably harmful. :P
            self.use_starttls = False

        self.__buffer = ''

        self.sock = socket.socket()
        self.connected = False

        # Locks writes
        self.writelock = Lock()

        # Dispatch
        self.dispatch_cmd_in = dict()
        self.dispatch_cmd_out = dict()

        # Our logger
        self.logger = logging.getLogger(__name__)


    """ Pretty printing of IRC stuff outgoing
    
    Override this for custom logging.
    """
    def writeprint(self, line):
        print('<', repr(line))


    """ Pretty printing of IRC stuff incoming

    Override this for custom logging
    """
    def readprint(self, line):
        print('>', repr(line))


    """ Write a Line instance to the wire """
    def linewrite(self, line):
        # acquire the write lock
        with self.writelock:
            # Call hook for this command
            # if it returns true, cancel
            if self.call_dispatch_out(line):
                self.logger.debug("Cancelled event due to hook request")
                return

            self.writeprint(line)
            self.send(bytes(line))


    """ Write a raw command to the wire """
    def cmdwrite(self, command, params=[]):
        self.linewrite(Line(command=command, params=params))


    """ Connect to the server

    timeout for connect defaults to 10. Set to None for no timeout.
    Note gevent will not be pleased if you do not have a timeout.
    """
    def connect(self, timeout=10):
        if timeout is not None:
            self.sock.settimeout(timeout)
        self.sock.connect((self.host, self.port))
        self.connected = True

        if self.use_ssl:
            self.wrap_ssl()

        self.hs_callback()


    """ Wrap the socket in SSL """
    def wrap_ssl(self):
        self.sock = ssl.wrap_socket(self.sock)
        self.use_ssl = True


    """ Recieve data from the wire """
    def recv(self):
        self.sock.settimeout(None)
        while '\r\n' not in self.__buffer:
            data = self.sock.recv(2048)

            if not data:
                raise socket.error(errno.ECONNRESET,
                                   os.strerror(errno.ECONNRESET))

            self.__buffer += data.decode('UTF-8', 'replace')

        lines = self.__buffer.split('\r\n')
        self.__buffer = lines.pop() 

        return lines


    """ Send data onto the wire """
    def send(self, data):
        sendlen = len(data)
        curlen = 0
        while curlen < sendlen:
            curlen += self.sock.send(data[curlen:])


    """ Dispatch for a command incoming """
    def call_dispatch_in(self, line):
        if line.command in self.dispatch_cmd_in:
            self.dispatch_cmd_in[line.command](line)


    """ Dispatch for a command outgoing """
    def call_dispatch_out(self, line):
        if line.command in self.dispatch_cmd_out:
            return self.dispatch_cmd_out[line.command](line)


    """ Recieve lines """
    def process_in(self):
        if not self.connected:
            self.connect()
        lines = [Line(line=line) for line in self.recv()]

        for line in lines:
            self.readprint(line)
            self.call_dispatch_in(line)

        return lines

