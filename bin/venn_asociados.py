# -*- coding: utf-8 -*-
"""
venn_asociados: calculates and plots a venn diagram showing lacnic member groupings

(c) Carlos M:, carlos@lacnic.net
"""

import sqlite3 as sq
import os
import matplotlib_venn as mpv
import json
from matplotlib import pyplot as plt

if os.name == "nt":
    os.chdir(r"C:\Users\carlos\Dropbox (Personal)\Workspaces\LACNIC-Wksp\70-checkouts\labs-opendata-datasets.git")
elif os.name == "posix":
    os.chdir("/Users/carlos/Dropbox (Personal)/Workspaces/LACNIC-Wksp/70-checkouts/labs-opendata-datasets.git")
else:
    print("WARN unable to detect operating system")

def runq(type,rir='lacnic'):
    # TODO: parametrize date
    c=sq.connect("var/netdata-2017-08-23.db")
    cur=c.cursor()
    r1=cur.execute("select distinct(orgid) from numres where rir='%s' and type='%s' and (status='allocated' or status='assigned')"
                   % (rir, type) )
    rcorgs=[ x[0] for x in r1.fetchall() ]
    return rcorgs
# end runq

class SetEncoder(json.JSONEncoder):
    def default(self, obj):
            if isinstance(obj, set):
                return list(obj)
            return json.JSONEncoder.default(self, obj)
    # end default
# end SetEncoder

if __name__ == "__main__":
    rsets = { 'ipv4':0, 'ipv6':0, 'asn':0 }
    for rc in rsets.keys():
        print("get orgs with assigned %s" % (rc) )
        rsets[rc] = set(runq(rc))
        print("%s: %s" % (rc, len(rsets[rc])) )
    # end for
        
    ipv4nipv6 = rsets['ipv4'] & rsets['ipv6']
    # print("orgs with both ipv4 and ipv6: %s" % (len(ipv4nipv6) ) )
    
    ipv6only = rsets['ipv6'] - rsets['ipv4']
    #print("orgs with ipv6 only: %s" % (len(ipv6only) ) )
    
    s5 = rsets['ipv4'] & rsets['ipv6'] & rsets['asn']
    rsets['Orgs with ipv4, ipv6 and asn'] = s5
    
    s2 = (rsets['ipv4'] & rsets['ipv6']) - s5
    rsets['Orgs with ipv4 and ipv6 but no asn'] = s2
    
    s4 = (rsets['ipv4'] & rsets['asn']) - s5
    rsets['Orgs with ipv4 and asn but no ipv6'] = s4
    
    s6 = (rsets['ipv6'] & rsets['asn']) - s5
    rsets['Orgs with ipv6 and asn but no ipv4'] = s6
    
    s1 = rsets['ipv4'] - s4 -s5 - s2
    rsets['Orgs with ipv4 only'] = s1
    
    s3 = rsets['ipv6'] - s6 - s5 - s2
    rsets['Orgs with ipv6 only'] = s3   
    
    s7 = rsets['asn'] - s5 - s4 - s6
    rsets['Orgs with asn only'] = s7
    
#    mpv.venn3( 
#            subsets = (len(s1),len(s2),len(s3),len(s4),len(s5),len(s6),len(s7) ), 
#            set_labels = ('ipv4','asn','ipv6' ) 
#            )

    # print text info
    for rc in rsets.keys():
        print("%s: %s" % (rc,len(rsets[rc])) )

    # draw plot

    plt.figure(figsize=(10,10))
    plt.title("Asociados LACNIC", fontsize=24)    
    mpv.venn3([rsets['ipv4'], rsets['ipv6'], rsets['asn']], ('IPv4', 'IPv6', 'ASN'))
    plt.show()
    
    # print json
    fp = open("var/venn-asociados-20170823.json", "w")
    # fp = io.FileIO("var/venn-asociados-20170815.json","w")
    json.dump(rsets, fp, cls=SetEncoder, indent=4)
    fp.close()