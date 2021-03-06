from irclib.common.numerics import *
from irclib.common.dispatch import PRIORITY_DEFAULT, PRIORITY_FIRST

""" Generic introspection routine to learn about ourself """
def dispatch_introspect(client, line):
    if line.hostmask is None:
        return

    if not line.hostmask.nick:
        return

    if line.hostmask.nick != client.current_nick:
        return

    if line.hostmask.user:
        client.current_user = line.hostmask.user

    if line.hostmask.host:
        client.current_host = line.hostmask.host


""" We've been cloaked """
def dispatch_sethost(client, line):
    client.current_host = line.params[1]


hooks_in = (
    (None, PRIORITY_FIRST, dispatch_introspect),
    (RPL_HOSTHIDDEN, PRIORITY_DEFAULT, dispatch_sethost),
)

