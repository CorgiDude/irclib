#!/usr/bin/env python3

from __future__ import unicode_literals, print_function, division

import sys
import codecs
import importlib
import logging

from functools import partial
from random import randint
from copy import deepcopy

from irclib.client.user import User
from irclib.client.channel import Channel
from irclib.client.network import IRCClientNetwork
from irclib.common.modes import ModeSet
from irclib.common.six import u, b
from irclib.common.colourmap import replace_colours

try:
    from queue import Queue
except ImportError:
    from Queue import Queue


""" Basic IRC client class. """
class IRCClient(IRCClientNetwork):
    """
    Creates an instance of IRCClient

    host - hostname to connect to
    port - port to connect to
    nick - nickname to use
    altnick - alternate nickname
    user - username to use (defaults to same as nick)
    realname - GECOS to use
    version - CTCP version reply
    use_ssl - use SSL (default False)
    use_starttls - use STARTTLS where available (default True)
    password - server passwrod
    default_channels - default places to join
    channel_keys - key:value pair of channel keys
    keepalive - interval to send keepalive pings (for lagcheck etc.)
    use_cap - use CAP
    kick_autorejoin - rejoin on kick
    kick_wait - wait time for rejoin (5 seconds default)
    """
    def __init__(self, **kwargs):
        IRCClientNetwork.__init__(self, **kwargs)

        self.nick = kwargs.get('nick', 'irclib')
        self.altnick = kwargs.get('altnick', self.nick+'_')
        self.user = kwargs.get('user', self.nick)
        self.realname = kwargs.get('realname', 'Python IRC library')
        self.version = kwargs.get('version', 'Python irclib v0.1. (C) Elizabeth Myers')
        self.password = kwargs.get('password', None)
        self.default_channels = kwargs.get('channels', [])
        self.channel_keys = kwargs.get('channel_keys', {})
        self.keepalive = kwargs.get('keepalive', 60)
        self.use_cap = kwargs.get('use_cap', True)
        self.use_sasl = kwargs.get('use_sasl', False)
        self.sasl_username = kwargs.get('sasl_username', None)
        self.sasl_pw = kwargs.get('sasl_pw', None)
        self.autorejoin = kwargs.get('kick_autorejoin', False)
        self.autorejoin_wait = kwargs.get('kick_wait', 5)
        self.custom_dispatch = kwargs.get('custom_dispatch', [])

        if self.use_sasl and (not self.sasl_pw or not self.sasl_username):
            self.logger.warn("Unable to use SASL, no username/password provided")
            self.use_sasl = False
        elif self.sasl_username and self.sasl_pw:
            # Use SASL.
            self.use_sasl = True

        if (self.use_sasl or self.use_starttls) and not self.use_cap:
            self.logger.warn("Enabling CAP because starttls and/or sasl requested")
            self.use_cap = True

        self.pending_channels = set()
        self.isupport = dict()
        self._whox_pending = set()

        # Default handlers
        self.default_dispatch()

        # Set everything up
        self.reset()

        # Fix printing Unicode on the screen
        if sys.stdout.encoding != "UTF-8":
            sys.stdout = codecs.getwriter('utf8')(sys.stdout)


    """ Logging callback """
    def log_callback(self, line, recv):
        if recv:
            ch = '>'
        else:
            ch = '<'

        line = deepcopy(line)
        # special formatters
        if line.command in ('PRIVMSG', 'NOTICE'):
            line.params[-1] = replace_colours(line.params[-1])

        print('{} {}'.format(ch, line), end='')


    """ Generator for IRC lines, e.g. non-terminating stream """
    def get_lines(self):
        while True:
            try:
                for l in self.process_in():
                    line = (yield l)
                    if line is not None:
                        self.linewrite(line)
            except:
                try:
                    self.timer_cancel_all()
                except ValueError:
                    pass
                raise


    """ Create default dispatches
    
    Only override this if you know what this does and what you're doing.
    """
    def default_dispatch(self):
        # Default list of dispatchers
        dispatchers = ['account', 'away', 'introspect', 'isupport', 'join',
                       'mode', 'monitor', 'names', 'nick', 'part', 'pingpong',
                       'privmsg', 'quit', 'topic', 'welcome', 'who', 'whois']

        if self.use_starttls:
            dispatchers.append('starttls')
            self.use_cap = True

        if self.use_sasl:
            dispatchers.append('sasl')
            self.use_cap = True

        # CAP state
        if self.use_cap:
            dispatchers.append('cap')

            # Capabilities
            self.cap_req = {'multi-prefix', 'account-notify', 'away-notify',
                            'away-notify', 'extended-join'}

            if self.use_starttls:
                self.cap_req.add('tls')

            if self.use_sasl:
                self.cap_req.add('sasl')

        def module_add_hooks(module):
            imp = importlib.import_module(module)
            if hasattr(imp, 'hooks_in'):
                for hook in imp.hooks_in:
                    self.add_dispatch_in(*hook)

            if hasattr(imp, 'hooks_out'):
                for hook in imp.hooks_out:
                    self.add_dispatch_out(*hook)

            if hasattr(imp, 'hooks_ctcp_in'):
                for hook in imp.hooks_ctcp_in:
                    self.add_ctcp_in(*hook)

        # Begin the imports
        for module in dispatchers:
            # Ergh I'd like it to use a relative import.
            module = 'irclib.client.dispatch.{}'.format(module)
            module_add_hooks(module)

        for module in self.custom_dispatch:
            module_add_hooks(module)


    """ Reset everything """
    def reset(self):
        # Cancel timers
        try:
            self.timer_cancel_all()
        except ValueError:
            pass

        # umodes
        self.umodes = ModeSet()
        self.snomask = None

        # Pending channels
        self.pending_channels.clear() 

        # Reset caps
        self.supported_cap = []
        self.cap_end = False

        # Reset ISUPPORT
        self.isupport.clear() 

        # Defaults for ancient-ass servers
        self.isupport['PREFIX'] = [('o', '@'), ('v', '+')]
        self.isupport['CHANTYPES'] = '#&!+' # Old servers tend to use these.
        self.isupport['NICKLEN'] = 8 # Olden servers
        # Not sure if this is correct but it's good enough
        self.isupport['CHANMODES'] = ['beI', 'k', 'l', 'imntsp']
       
        # Map prefix to mode
        self.prefix_to_mode = {s:m for m,s in self.isupport['PREFIX']}

        # Handshaken?
        self.handshake = False

        # Registered?
        self.registered = False

        # Identified?
        self.identified = False

        # Lag stats
        self._last_pingstr = None
        self._last_pingtime = 0
        self.lag = 0

        # Nick trials
        if hasattr(self, '_nick_trycount'):
            del self._nick_trycount

        # For privmsg
        if hasattr(self, '_msg_last'):
            del self._msg_last

        # Pending WHOX replies
        self._whox_pending.clear()

        # ISON list pending
        self._ison_list = Queue()

        try:
            # Cancel all outstanding timers
            self.timer_cancel_all()
        except ValueError:
            pass

        # Authoriative
        self.channels = dict()
        self.users = dict()

        # Our own stuff
        self.current_nick = None
        self.current_user = None
        self.current_host = None


    """ Write the user/nick line """
    def dispatch_register(self):
        if not self.registered:
            self.cmdwrite('USER', [self.user, '+iw', self.host, self.realname])
            self.cmdwrite('NICK', [self.nick])

            if self.password:
                self.cmdwrite('PASS', [self.password])

            self.registered = True

            if self.cap_end:
                return

            # End of CAP if we're not using SASL
            if self.use_cap and not self.use_sasl:
                self.cap_terminate()
            elif self.use_sasl and 'sasl' in self.supported_cap:
                self.cmdwrite('AUTHENTICATE', ['PLAIN'])

                # Abort SASL after some time
                self.timer_oneshot('cap_terminate', 15, self.cap_terminate)


    """ Start initial handshake """
    def connect(self, timeout=10):
        IRCClientNetwork.connect(self, timeout)

        self.do_handshake()


    """ Do actual connect stuff """
    def do_handshake(self):
        if self.handshake:
            return

        self.handshake = True
        if not self.use_cap:
            # Not using CAP :(
            self.dispatch_register()
        elif self.use_cap:
            # Request caps
            self.cmdwrite('CAP', ['LS'])

            # Cancel CAP after some time
            self.timer_oneshot('cap_terminate', 10, self.cap_terminate)


    """ Terminate CAP """
    def cap_terminate(self):
        if self.cap_end:
            return

        self.cap_end = True
        self.cmdwrite('CAP', ['END'])
        self.dispatch_register()


    """ Add a user to expiry checks """
    def expire_user(self, nick):
        if len(self.users[nick].channels) == 0:
            if 'MONITOR' in self.isupport:
                # We support monitor :D
                self.cmdwrite('MONITOR', ('+', nick))
            else:
                # :( use ISON as a fallback
                isoncheck = partial(self.cmdwrite, 'ISON', (nick,))
                timername = 'ison_user_{}'.format(nick)
                self.timer_repeat(timername, 60, isoncheck)
                isoncheck()


    """ Unexpire a user """
    def unexpire_user(self, nick):
        self.timer_cancel('ison_user_{}'.format(nick))
        if 'MONITOR' in self.isupport:
            # XXX might send useless monitor
            self.cmdwrite('MONITOR', ('-', nick))


    """ Create a user """
    def create_user(self, nick, user=None, host=None, realname=None,
                    account=None):
        self.users[nick] = User(self, nick, user, host, realname, account)


    """ Delete a user """
    def delete_user(self, nick):
        self.users.pop(nick, None)


    """ Create a channel """
    def create_channel(self, channel):
        self.channels[channel] = Channel(self, channel)


    """ Destroy a channel """
    def delete_channel(self, channel):
        self.channels.pop(channel, None)


    """ Attach channel and user """
    def attach_nick_channel(self, nick, channel):
        if nick not in self.users:
            self.create_user(nick)

        if channel not in self.channels:
            self.create_channel(channel)

        self.channels[channel].user_add(nick, client.users[nick])
        self.users[nick].channel_add(channel, client.channels[channel])


    """ Combine channels for join """
    def join_channels(self, chlist, chkeys={}):
        chcount = 0
        buflen = 0
        sbuf = []
        chbuf = []
        keybuf = []
        MAXLEN = 500
        for ch in chlist:
            clen = len(ch) + 1
            key = None 
            if ch in chkeys:
                # +1 for space
                key = chkeys[ch]
                clen = len(key) + 1

            # Sod it. this will never fit. :/
            if clen > MAXLEN:
                self.logger.error('Unable to join channel:key; too long: '
                                  '{}:{}'.format(ch, key))
                continue

            # Full buffer!
            if (buflen + clen) > MAXLEN or len(chbuf) >= 4:
                sbuf.append((chbuf, keybuf))

                chbuf = []
                keybuf = []
                buflen = 0

            # Add to the buffer
            chbuf.append(ch)
            if key: keybuf.append(key)
            buflen += clen

        # Remainder
        if len(chbuf) > 0:
            sbuf.append((chbuf, keybuf))

        if len(sbuf) > 3:
            # Pace our joins
            pace_join = True
            counter = 0
        else:
            pace_join = False

        for buf in sbuf:
            channels = ','.join(buf[0])
            keys = ' '.join(buf[1])
            joinfunc = partial(self.cmdwrite, 'JOIN', (channels, keys))
            if pace_join:
                timername = 'join_channel_{}'.format(str(counter))
                interval = randint(1, 150) / 10
                self.timer_oneshot(timername, interval, joinfunc)
                counter += 1
            else:
                joinfunc()

