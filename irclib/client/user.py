#!/usr/bin/env python3

import weakref

class User:
    def __init__(self, network, nick, user=None, host=None, realname=None,
                 account=None):
        self.network = network
        self.nick = nick
        self.user = user
        self.host = host
        self.realname = realname
        self.account = account

        # Unknown away status
        self.away = None
        self.away_message = None

        self.channels = weakref.WeakValueDictionary()

    def channel_add(self, name, ch):
        self.channels[name] = ch


    def channel_del(self, name):
        del self.channels[name]


