#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from irclib.client import client
from irclib.common.line import Line
from random import choice, randint

import logging
import os

# Set log level
logging.basicConfig(level=logging.DEBUG)

randomshit = [
    'I have to go in five minutes',
    'what?',
    '?',
    'I don\'t know what that is in swedish',
    'I had to go to the fotvårdsspecialist (no idea what that is in English)',
    'I need to shower in a few minutes. make it quick',
    '^',
    'Liz, ^',
    'Night →',
    'bbl',
    'Perhaps you should use erlang, or scheme.',
    'FORTH is a wonderful language',
    'Use Clojure!',
    'maybe use some kind of message passing',
    'what does that mean',
    'I have no idea what that means',
    'Stop that',
    'that bot is annoying',
    'there, I have it on ignore now.',
    'but can it run emacs? that\'s important',
    'ew vim',
    'LISP is an awesome language',
    'Haskell makes you think in new ways',
    'perhaps you should play nethack',
    'try playing skyrim',
    'where is the data taken from?',
    '\x01ACTION made a bot in bash\x01',
    '\x01ACTION prefers erlang\x01',
    'Perhaps a high level language with a generational GC like haskell or erlang',
    'I hate git. We only use hg at work',
    'How do I sync my SD card to my computer? too cheap to buy a $1 adaptor',
    'I have mouse arm and my wrists hurt',
    'I can\'t type right now',
    'can you repeat that? it\'s out of scrollback',
    'too lazy to scroll up, what did you say',
]

def spew(line, generator, cprefix):
    if randint(0, 14) != 0:
        return

    if len(line.params) <= 1: return

    target = line.params[0]
    msg = line.params[-1]

    if target[0] not in cprefix:
        target = line.hostmask.nick

    generator.send(Line(command='PRIVMSG', params=(target, choice(randomshit))))


def run(instance):
    try:
        generator = instance.get_lines()
        for line in generator:
            if line.command == "PRIVMSG":
                spew(line, generator, instance.isupport['CHANTYPES'])
    except IOError as e:
        print("Disconnected", str(e))
        os.sleep(5)

kwargs = {
    'nick' : 'Vorpel',
    'host' : 'okami.interlinked.me',
    'port' : 6667,
    'channels' : ['#irclib'],
    'use_sasl' : True,
    'sasl_username' : 'Vorpel',
    'sasl_pw' : 'changeme',
}

instance = client.IRCClient(**kwargs)

while True:
    run(instance)

