""" Generic NWS Product Parser """

# Twisted Python imports
from twisted.python import log
from twisted.python import logfile
from twisted.internet import reactor

# Standard Python modules
import re
import datetime
import sys

# third party
import pytz
from shapely.geometry import MultiPolygon

# pyLDM https://github.com/akrherz/pyLDM
from pyldm import ldmbridge
# pyIEM https://github.com/akrherz/pyIEM
from pyiem.nws.products import parser as productparser
from pyiem.nws import ugc
from pyiem.nws import nwsli

import common

ugc_dict = {}
nwsli_dict = {}


def shutdown():
    ''' Stop this app '''
    log.msg("Shutting down...")
    reactor.callWhenRunning(reactor.stop)
    

# LDM Ingestor
class MyProductIngestor(ldmbridge.LDMProductReceiver):
    """ I receive products from ldmbridge and process them 1 by 1 :) """

    def connectionLost(self, reason):
        ''' callback when the stdin reader connection is closed '''
        log.msg('connectionLost() called...')
        log.err( reason )
        reactor.callLater(7, shutdown)

    def process_data(self, buf):
        """ Process the product """
        try:
            really_process_data(buf)
        except Exception, myexp: #pylint: disable=W0703
            common.email_error(myexp, buf) 

def really_process_data(buf):
    ''' Actually do some processing '''
    utcnow = datetime.datetime.utcnow()
    utcnow = utcnow.replace(tzinfo=pytz.timezone("UTC"))
    
    # Create our TextProduct instance
    prod = productparser( buf, utcnow=utcnow, ugc_provider=ugc_dict,
                               nwsli_provider=nwsli_dict)

    # Insert into database
    product_id = prod.get_product_id()
    sqlraw = buf.replace("\015\015\012", "\n").replace("\000", "").strip()
    sql = """INSERT into text_products(product, product_id) values (%s,%s)"""
    myargs = (sqlraw, product_id)
    if (len(prod.segments) > 0 and prod.segments[0].sbw):
        giswkt = 'SRID=4326;%s' % (MultiPolygon([prod.segments[0].sbw]).wkt,)
        sql = """INSERT into text_products(product, product_id, geom) 
                values (%s,%s,%s)"""
        myargs = (sqlraw, product_id, giswkt)
    deffer = PGCONN.runOperation(sql, myargs)
    deffer.addErrback( common.email_error, sqlraw)
    
    #Do the Jabber work necessary after the database stuff has completed
    for (plain, html, xtra) in prod.get_jabbers( 
            common.settings.get('pywwa_product_url', 'pywwa_product_url') ):
        if xtra.get('channels', '') == '':
            common.email_error("xtra[channels] is empty!", buf)
        if not MANUAL:
            jabber.sendMessage(plain, html, xtra)
    
def load_ugc(txn):
    """ load ugc"""
    sql = """SELECT name, ugc, wfo from ugcs WHERE 
        name IS NOT Null and end_ts is null"""
    txn.execute(sql)
    for row in txn:
        ugc_dict[ row['ugc'] ] = ugc.UGC(row['ugc'][:2], row['ugc'][2],
                        row['ugc'][3:],
                name=(row["name"]).replace("\x92"," ").replace("\xc2"," "),
                wfos=re.findall(r'([A-Z][A-Z][A-Z])',row['wfo']))

    log.msg("ugc_dict loaded %s entries" % (len(ugc_dict),))

    sql = """SELECT nwsli, 
     river_name || ' ' || proximity || ' ' || name || ' ['||state||']' as rname 
     from hvtec_nwsli"""
    txn.execute( sql )
    for row in txn:
        nwsli_dict[ row['nwsli'] ] = nwsli.NWSLI(row['nwsli'], 
                                name=row['rname'].replace("&"," and "))

    log.msg("nwsli_dict loaded %s entries" % (len(nwsli_dict),))
    
    return None

def ready(dummy):
    ''' cb when our database work is done '''
    ldmbridge.LDMProductFactory( MyProductIngestor() )

def dbload():
    ''' Load up database stuff '''
    df = PGCONN.runInteraction(load_ugc)
    df.addCallback( ready )

if __name__ == '__main__':
    log.FileLogObserver.timeFormat = "%Y/%m/%d %H:%M:%S %Z"
    log.startLogging( logfile.DailyLogFile('generic_parser.log','logs'))

    MANUAL = False
    if len(sys.argv) == 2 and sys.argv[1] == 'manual':
        log.msg("Manual runtime (no jabber, 1 database connection) requested")
        MANUAL = True

    # Fire up!
    PGCONN = common.get_database("postgis", cp_max=(5 if not MANUAL else 1))
    dbload()
    jabber = common.make_jabber_client('generic_parser')
    
    reactor.run()
