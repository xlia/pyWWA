"""Utility script to generate the HTML used for IEMBot Channel Documentation
"""
from __future__ import print_function
import re
import sys

import psycopg2.extras
from pyiem.reference import prodDefinitions
from pyiem.nws.ugc import UGC
from pyiem.nws.nwsli import NWSLI
from pyiem.nws.products.vtec import parser as vtec_parser
from pyiem.nws.products import parser as productparser

ugc_dict = {}
nwsli_dict = {}

C1 = "&lt;wfo&gt;"
C2 = "&lt;vtec_phenomena&gt;.&lt;vtec_significance&gt;"
C3 = "&lt;afos_pil&gt;"
C3p = "&lt;afos_pil_prefix&gt;..."
C4 = "&lt;vtec_phenomena&gt;.&lt;vtec_significance&gt;.&lt;wfo&gt;"
C5 = "&lt;vtec_phenomena&gt;.&lt;vtec_significance&gt;.&lt;ugc&gt;"
C5s = "&lt;vtec_phenomena&gt;.&lt;vtec_significance&gt;.&lt;state&gt;"
C6 = "&lt;ugc&gt;"
C7 = "&lt;afos_pil&gt;.&lt;wfo&gt;"
C8 = "&lt;wmo_source&gt;.&lt;aaa&gt;"
C9 = "&lt;afos_pil&gt;.&lt;ugc&gt;"
D = {
     '10-313': 'http://www.nws.noaa.gov/directives/sym/pd01003013curr.pdf',
     '10-314': 'http://www.nws.noaa.gov/directives/sym/pd01003014curr.pdf',
     '10-315': 'http://www.nws.noaa.gov/directives/sym/pd01003015curr.pdf',
     '10-320': "http://www.nws.noaa.gov/directives/sym/pd01003020curr.pdf",
     '10-330': "http://www.nws.noaa.gov/directives/sym/pd01003030curr.pdf",
     '10-401': 'http://www.nws.noaa.gov/directives/sym/pd01004001curr.pdf',
     '10-511': 'http://www.nws.noaa.gov/directives/sym/pd01005011curr.pdf',
     '10-513': 'http://www.nws.noaa.gov/directives/sym/pd01005013curr.pdf',
     '10-515': 'http://www.nws.noaa.gov/directives/sym/pd01005015curr.pdf',
     '10-517': 'http://www.nws.noaa.gov/directives/sym/pd01005017curr.pdf',
     '10-601': 'http://www.nws.noaa.gov/directives/sym/pd01006001curr.pdf',
     '10-912': 'http://www.nws.noaa.gov/directives/sym/pd01009012curr.pdf',
     '10-922': 'http://www.nws.noaa.gov/directives/sym/pd01009022curr.pdf',
     '10-1701': 'http://www.nws.noaa.gov/directives/sym/pd01017001curr.pdf',
    }

# TODO: TCV TSU ADR CDW DSA EQW HMW HPA LEw NUW RHW VOW PQS CWA
# Our dictionary of products!
S1 = [C1, C2, C3, C3p, C4, C5, C5s, C6]
VTEC_PRODUCTS = [
    dict(afos='CFW', directive='10-320', channels=S1),
    dict(afos='EWW', directive='10-601', channels=S1),
    dict(afos='FFA', directive='10-922', channels=S1),
    dict(afos='FFS', directive='10-922', channels=S1),
    dict(afos='FFW', directive='10-922', channels=S1),
    dict(afos='FLS', directive='10-922', channels=S1),
    dict(afos='FLW', directive='10-922', channels=S1),
    dict(afos='MWW', directive='10-315', channels=[C2, C3, C3p, C4, C5, C6],
         notes=("This product does not get routed to the "
                "<span class=\"badge\">&lt;wfo&gt;</span> "
                "channel.  This is because the product is very frequently "
                "issued for offices with marine zones.")),
    dict(afos='NPW', directive='10-515', channels=S1),
    dict(afos='RFW', directive='10-401', channels=S1),
    dict(afos='SMW', directive='10-313', channels=S1),
    dict(afos='SVR', directive='10-511', channels=S1),
    dict(afos='SVS', directive='10-511', channels=S1),
    dict(afos='TOR', directive='10-511', channels=S1),
    dict(afos='WCN', directive='10-511', channels=S1),
    dict(afos='WSW', directive='10-513', channels=S1),
                 ]
S2 = [C3, C3p]
GEN_PRODUCTS = [
    dict(afos='ADA', directive='10-1701', channels=S2),
    dict(afos='ADM', directive='10-1701', channels=S2),
    dict(afos='AFD', directive='10-1701', channels=S2),
    dict(afos='AQI', directive='10-1701', channels=S2),
    dict(afos='AWU', directive='10-1701', channels=S2),
    dict(afos='AWW', directive='10-1701', channels=S2),
    dict(afos='AVA', directive='10-1701', channels=S2),
    dict(afos='AVW', directive='10-1701', channels=S2),
    dict(afos='AQA', directive='10-1701', channels=S2),
    dict(afos='CAE', directive='10-1701', channels=S2),
    dict(afos='CEM', directive='10-1701', channels=S2),
    dict(afos='CGR', directive='10-1701', channels=S2),
    dict(afos='CLI', directive='10-1701', channels=S2),
    dict(afos='CRF', directive='10-912', channels=S2),
    dict(afos='CWF', directive='10-1701', channels=S2),
    dict(afos='DGT', directive='10-1701', channels=S2),
    dict(afos='ESF', directive='10-1701', channels=S2),
    dict(afos='EQI', directive='10-1701', channels=S2),
    dict(afos='EQR', directive='10-1701', channels=S2),
    dict(afos='EVI', directive='10-1701', channels=S2),
    dict(afos='FRW', directive='10-1701', channels=S2),
    dict(afos='FTM', directive='10-1701', channels=S2),
    dict(afos='FWA', directive='10-1701', channels=S2),
    dict(afos='FWF', directive='10-1701', channels=S2),
    dict(afos='FWS', directive='10-1701', channels=S2),
    dict(afos='GLF', directive='10-1701', channels=S2),
    dict(afos='HLS', directive='10-601', channels=S2),
    dict(afos='HCM', directive='10-1701', channels=S2),
    dict(afos='HMD', directive='10-1701', channels=S2),
    dict(afos='HWO', directive='10-517', channels=S2),
    dict(afos='HYD', directive='10-1701', channels=S2),
    dict(afos='ICE', directive='10-330', channels=S2),
    dict(afos='LAE', directive='10-1701', channels=S2),
    dict(afos='LCO', directive='10-1701', channels=S2),
    dict(afos='LSR', directive='10-517', channels=S2),
    dict(afos='MCD', directive='10-517', channels=[C3, C7],
         notes=("The WFOs"
                " included are based on the ones highlighted by SPC within "
                "the text and not from a spatial check of their polygon.")),
    dict(afos='MPD', directive='10-517', channels=[C3, C7],
         notes=("The WFOs"
                " included are based on the ones highlighted by WPC within "
                "the text and not from a spatial check of their polygon.")),
    dict(afos='MIS', directive='10-1701', channels=S2),
    dict(afos='MWS', directive='10-314', channels=S2),
    dict(afos='NOW', directive='10-1701', channels=S2),
    dict(afos='NSH', directive='10-1701', channels=S2),
    dict(afos='OAV', directive='10-1701', channels=S2),
    dict(afos='OMR', directive='10-1701', channels=S2),
    dict(afos='PFM', directive='10-1701', channels=S2),
    dict(afos='PNS', directive='10-1701', channels=S2),
    dict(afos='PSH', directive='10-1701', channels=S2),
    dict(afos='REC', directive='10-1701', channels=S2),
    dict(afos='RER', directive='10-1701', channels=S2),
    dict(afos='RRM', directive='10-1701', channels=S2),
    dict(afos='RFD', directive='10-1701', channels=S2),
    dict(afos='RTP', directive='10-1701', channels=S2),
    dict(afos='RVA', directive='10-1701', channels=S2),
    dict(afos='RVD', directive='10-922', channels=S2),
    dict(afos='RVF', directive='10-912', channels=S2),
    dict(afos='RWS', directive='10-1701', channels=S2),
    dict(afos='RVS', directive='10-1701', channels=S2),
    dict(afos='STF', directive='10-1701', channels=S2),
    dict(afos='SPS', directive='10-1701', channels=[C3, C3p, C6, C9]),
    dict(afos='SRF', directive='10-1701', channels=S2),
    dict(afos='SPW', directive='10-1701', channels=S2),
    dict(afos='TAF', directive='10-1701', channels=[C3, C3p, C8]),
    dict(afos='TIB', directive='10-1701', channels=S2),
    dict(afos='TID', directive='10-320', channels=S2),
    dict(afos='TOE', directive='10-1701', channels=S2),
    dict(afos='WSV', directive='10-1701', channels=S2),
    dict(afos='VAA', directive='10-1701', channels=S2),
    dict(afos='WRK', directive='10-1701', channels=S2),
    dict(afos='ZFP', directive='10-1701', channels=S2),
                ]


def get_data(afos):
    """Return the text data for a given afos identifier"""
    return open(("/home/akrherz/projects/pyIEM/data/channel_examples/%s.txt"
                 ) % (afos,)).read()


def load_dicts():
    """Load up the directionaries"""
    pgconn = psycopg2.connect(database='postgis', host='iemdb', user='nobody')
    cursor = pgconn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    sql = """SELECT name, ugc, wfo from ugcs WHERE
        name IS NOT Null and end_ts is null"""
    cursor.execute(sql)
    for row in cursor:
        nm = (row["name"]).replace("\x92", " ").replace("\xc2", " ")
        wfos = re.findall(r'([A-Z][A-Z][A-Z])', row['wfo'])
        ugc_dict[row['ugc']] = UGC(row['ugc'][:2], row['ugc'][2],
                                   row['ugc'][3:],
                                   name=nm,
                                   wfos=wfos)

    sql = """SELECT nwsli,
     river_name || ' ' || proximity || ' ' || name || ' ['||state||']' as rname
     from hvtec_nwsli"""
    cursor.execute(sql)
    for row in cursor:
        nm = row['rname'].replace("&", " and ")
        nwsli_dict[row['nwsli']] = NWSLI(row['nwsli'], name=nm)


def do_generic():
    print("""
    <h3>NWS Local Office / National Products</h3>
    <table class="table table-bordered table-condensed">
    <thead>
    <tr><td></td><th>AFOS PIL + Product Name</th><th>Directive</th>
    <th>Channel Templates Used</th></tr>
    </thead>
    """)
    for entry in GEN_PRODUCTS:
        afos = entry['afos']
        if afos == '':
            continue
        try:
            v = productparser(get_data(afos), ugc_provider=ugc_dict,
                              nwsli_provider=nwsli_dict)
            assert v.afos is not None
        except Exception as exp:
            sys.stderr.write(str(exp))
            sys.stderr.write(afos+"\n")
            continue
        j = v.get_jabbers("https://mesonet.agron.iastate.edu/p.php")
        jmsg = ""
        tweet = ""
        channels = []
        for (_, html, xtra) in j:
            tweet += xtra['twitter'] + "<br />"
            jmsg += html
            if isinstance(xtra['channels'], list):
                xtra['channels'] = ",".join(xtra['channels'])
            for channel in xtra['channels'].split(","):
                if channel not in channels:
                    channels.append(channel)
        channels.sort()
        print("""<tr><td><a name="channel_%s"/>
<a id="%s_btn" class="btn btn-small" role="button"
 href="javascript: revdiv('%s');"><i class="fa fa-plus"></i></a>
        </td><td>%s (%s)</td><td><a href="%s">%s</a></td><td>%s</td></tr>
        <tr><td colspan="4"><div id="%s" style="display:none;">
        <dl class="dl-horizontal">
        %s
        <dt>Example Raw Text:</dt>
<dd><a href="https://mesonet.agron.iastate.edu/p.php?pid=%s">View Text</a></dd>
        <dt>Channels for Product Example:</dt><dd>%s</dd>
        <dt>XMPP Chatroom Example:</dt><dd>%s</dd>
        <dt>Twitter Example:</dt><dd>%s</dd>
        </dl>
        </div>
        </td>
        </tr>
        """ % (afos, afos, afos, prodDefinitions.get(afos, afos), afos,
               D[entry['directive']], entry['directive'],
               " ".join(["<span class=\"badge\">%s</span>" % (s,)
                         for s in entry['channels']]),
               afos,
               '<dt>Notes</dt><dd>%s</dd>' % (entry.get('notes'),)
               if 'notes' in entry else '',
               v.get_product_id(),
               " ".join(["<span class=\"badge\">%s</span>" % (s,)
                         for s in channels]),
               jmsg, tweet))

    print("""</table>""")


def do_vtec():
    """Do VTEC"""
    print("""
    <h3>NWS Products with P-VTEC and/or H-VTEC Included</h3>
    <table class="table table-bordered table-condensed">
    <thead>
    <tr><td></td><th>AFOS PIL + Product Name</th><th>Directive</th>
    <th>Channel Templates Used</th></tr>
    </thead>
    """)
    for entry in VTEC_PRODUCTS:
        afos = entry['afos']
        if afos == '':
            continue
        v = vtec_parser(get_data(afos), ugc_provider=ugc_dict,
                        nwsli_provider=nwsli_dict)
        j = v.get_jabbers("https://mesonet.agron.iastate.edu/vtec/",
                          "https://mesonet.agron.iastate.edu/vtec/")
        jmsg = ""
        tweet = ""
        channels = []
        for (_, html, xtra) in j:
            tweet += xtra['twitter'] + "<br />"
            jmsg += html
            for channel in xtra['channels'].split(","):
                if channel not in channels:
                    channels.append(channel)
        channels.sort()
        print("""<tr><td><a name="channel_%s"/>
        <a id="%s_btn" class="btn btn-small" role="button"
 href="javascript: revdiv('%s');"><i class="fa fa-plus"></i></a>
        </td><td>%s (%s)</td><td><a href="%s">%s</a></td><td>%s</td></tr>
        <tr><td colspan="4"><div id="%s" style="display:none;">
        <dl class="dl-horizontal">
        %s
        <dt>Example Raw Text:</dt>
<dd><a href="https://mesonet.agron.iastate.edu/p.php?pid=%s">View Text</a></dd>
        <dt>Channels for Product Example:</dt><dd>%s</dd>
        <dt>XMPP Chatroom Example:</dt><dd>%s</dd>
        <dt>Twitter Example:</dt><dd>%s</dd>
        </dl>
        </div>
        </td>
        </tr>
        """ % (afos, afos, afos, prodDefinitions.get(afos, afos), afos,
               D[entry['directive']], entry['directive'],
               " ".join(["<span class=\"badge\">%s</span>" % (s,)
                         for s in entry['channels']]),
               afos,
               '<dt>Notes</dt><dd>%s</dd>' % (entry.get('notes'),)
               if 'notes' in entry else '',
               v.get_product_id(),
               " ".join(["<span class=\"badge\">%s</span>" % (s,)
                         for s in channels]),
               jmsg, tweet))

    print("""</table>""")


def main():
    """Do Something Fun"""
    load_dicts()
    print("""
    <style>
    .badge {
        background-color: #EEEEEE;
        color: #000;
    }
    .dl-horizontal dt {
        white-space: normal;
        padding-bottom: 10px;
    }
    </style>
    """)
    do_vtec()
    do_generic()

    print("""
    <script>
    function revdiv(myid){
      var $a = $('#'+myid);
      if ($a.css('display') == 'block'){
        $a.css('display', 'none');
        $("#"+myid+"_btn").html('<i class="fa fa-plus"></i>');
      } else {
        window.location.hash = '#channel_'+myid;
        $("#"+myid+"_btn").parent().parent().addClass('info');
        $a.css('display', 'block');
        $("#"+myid+"_btn").html('<i class="fa fa-minus"></i>');
      }
    }
    </script>
    """)


if __name__ == '__main__':
    # Go Main Go
    main()
