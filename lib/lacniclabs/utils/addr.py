"""
addr.py: Some useful functions for IP address management

:author: carlos@lacnic.net
:date: 2016-05-26

"""
##############################################################################################
import math
import sys
import ipaddr

#begin
def pfxExplode(w_pfx):
    """
    Calculates meta columns for the delegated file.
    :param w_pfx:  prefix to be exploded

    Returns a dictionary with the following fields:
        'pfx'
        'type'
        'istart'
        'iend'
        'pfxlen'
    """
    # record = dict(w_row)
    record = dict()
    #
    if w_pfx:
        if w_pfx.find(":") != -1:
            loc_type = 'ipv6'
        else:
            loc_type = 'ipv4'
    else:
        loc_type = 'na'
    #
    record['pfx'] = w_pfx

    record['type'] = loc_type
    record['pfxlen'] = 0
    record['equiv'] = 0

    if record['type'] == 'ipv4' and w_pfx:
        record['prefix'] = w_pfx
        #print "prefix %s" % (w_pfx)
        try:
            pfx = ipaddr.IPv4Network(w_pfx)
            record['istart'] = int(pfx.network)
            record['iend'] = int(pfx.broadcast)
            record['pfxlen'] = pfx.prefixlen
            record['equiv'] = (record['iend']-record['istart']+1)/256
        except ipaddr.AddressValueError:
            sys.stderr.write("##### bad ip prefix: %s\n\n\n" % (record['prefix']))
            record['istart'] = -1
            record['iend']   = -1
            record['pfxlen'] = -1
            record['type'] ='badipv4'
        # record['equiv'] = (record['iend']-record['istart'])/256 + 1
        # return record
        return record
    elif record['type'] == 'ipv6' and w_pfx:
        if w_pfx.startswith("2"):
            pfx_norm_base = pow(2,64)
            try:
                pfx = ipaddr.IPv6Network( w_pfx )
                record['istart'] = int(pfx.network) / pfx_norm_base
                record['iend'] = int(pfx.broadcast) / pfx_norm_base
                record['pfxlen'] = pfx.prefixlen
                record['equiv'] = (record['iend'] - record['istart']+1) / math.pow(2, 32)
            except ipaddr.AddressValueError:
                sys.stderr.write("##### bad ip prefix: %s\n\n\n" % (record['prefix']))
                record['istart'] = -1
                record['iend']   = -1
                record['pfxlen'] = -1
                record['type'] = 'badipv6'                
        else:
            record['istart'] = 0
            record['iend']   = 0
            record['pfxlen'] = 0
            record['equiv'] = 0
        return record
    else:
        # return record['type']
        return record
# end
##############################################################################################
