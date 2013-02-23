from irclib.common.numerics import *
import base64

""" Authenticate to the server

TODO - other auth types
"""
def dispatch_sasl_authenticate(client, line):
    client.timer_cancel('cap_terminate')

    # We got an authentication message?
    if line.params[0] != '+':
       client.logger.warn('Unexpected response from SASL auth agent, '
                          'continuing')

    if not client.identified:
        # Generate
        send = '{acct}\0{acct}\0{pw}'.format(acct=client.sasl_username,
                                             pw=client.sasl_pw)
        send = base64.b64encode(send.encode('utf-8'))
        send = send.decode('ascii')

        # Split into 400 byte chunks
        split = [send[i:i+400] for i in range(0, len(send), 400)]
        for item in split:
            client.cmdwrite('AUTHENTICATE', [item])
 
        # Padding, if needed
        if len(split[-1]) == 400:
            client.cmdwrite('AUTHENTICATE', ['+'])

        # Timeout authentication
        client.timer_oneshot('cap_terminate', 15, client.terminate_cap)


def dispatch_sasl_success(client, line):
    client.identified = True
    if line.command == RPL_SASLSUCCESS:
        # end CAP
        client.terminate_cap()


def dispatch_sasl_error(client, line):
    # SASL failed
    client.logger.error('SASL auth failed! Error: {} {}'.format(
                        line.command,
                        line.params[-1]))
    client.terminate_cap()


hooks_in = ( 
    ('AUTHENTICATE', 0, dispatch_sasl_authenticate),
    (RPL_LOGGEDIN, 0, dispatch_sasl_success),
    (RPL_SASLSUCCESS, 0, dispatch_sasl_success),
    (ERR_SASLFAIL, 0, dispatch_sasl_error),
    (ERR_SASLTOOLONG, 0, dispatch_sasl_error),
)
