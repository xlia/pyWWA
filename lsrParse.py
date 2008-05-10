# Copyright (c) 2005 Iowa State University
# http://mesonet.agron.iastate.edu/ -- mailto:akrherz@iastate.edu
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
""" LSR product ingestor """


# Standard python imports
import re, traceback, StringIO, logging, pickle, os
from email.MIMEText import MIMEText

# Third party python stuff
import mx.DateTime
from twisted.python import log
from twisted.enterprise import adbapi
from twisted.mail import smtp
from twisted.words.protocols.jabber import client, jid, xmlstream
from twisted.internet import reactor

# IEM python Stuff
import common
import secret
from support import TextProduct,  ldmbridge, reference

DBPOOL = adbapi.ConnectionPool("psycopg2", database=secret.dbname, 
                               host=secret.dbhost)


errors = StringIO.StringIO()

log.startLogging(open('/mesonet/data/logs/%s/lsrParse.log' \
    % (os.getenv("USER"),), 'a'))
log.FileLogObserver.timeFormat = "%Y/%m/%d %H:%M:%S %Z"

class ProcessingException(Exception): pass

# Cheap datastore for LSRs to avoid Dups!
lsrdb = {}
try:
    lsrdb = pickle.load( open('lsrdb.p') )
except:
    pass

def cleandb():
    thres = mx.DateTime.gmt() - mx.DateTime.RelativeDateTime(hours=48)
    init_size = len(lsrdb.keys())
    for key in lsrdb.keys():
        if (lsrdb[key] < thres):
            del lsrdb[key]

    fin_size = len(lsrdb.keys())
    log.msg("cleandb() init_size: %s final_size: %s" % (init_size, fin_size))
    # Non blocking hackery
    reactor.callInThread(pickledb)

    # Call Again in 30 minutes
    reactor.callLater(60*30, cleandb) 

def pickledb():
    pickle.dump(lsrdb, open('lsrdb.p','w'))

# LDM Ingestor
class myProductIngestor(ldmbridge.LDMProductReceiver):

    def process_data(self, buf):
        try:
            raw = buf.replace("\015\015\012", "\n")
            real_processor(raw)
        except ProcessingException, msg:
            send_iemchat_error(raw, msg)
        except:
            io = StringIO.StringIO()
            traceback.print_exc(file=io)
            log.msg( io.getvalue() )
            msg = MIMEText("%s\n\n>RAW DATA\n\n%s"%(io.getvalue(),raw ))
            msg['subject'] = 'Unhandled lsrParse.py Traceback'
            msg['From'] = "ldm@mesonet.agron.iastate.edu"
            msg['To'] = "akrherz@iastate.edu"

            smtp.sendmail("mailhub.iastate.edu", msg["From"], msg["To"], msg)

    def connectionLost(self,reason):
        log.msg("LDM Closed PIPE")


def send_iemchat_error(raw, msgtxt):
    nws = TextProduct.TextProduct(raw)

    msg = "%s: iembot processing error:\nProduct: %s\nError: %s" % \
            (nws.get_iembot_source(), \
             nws.get_product_id(), msgtxt )

    htmlmsg = "<span style='color: #FF0000; font-weight: bold;'>\
iembot processing error:</span><br/>Product: %s<br/>Error: %s" % \
            (nws.get_product_id(), msgtxt )
    jabber.sendMessage(msg, htmlmsg)
    jabber.sendMessage(msg, htmlmsg, 'iowamesonet')


def real_processor(raw):
    nws = TextProduct.TextProduct(raw)
    # Need to find wfo
    tokens = re.findall("LSR([A-Z][A-Z][A-Z,0-9])\n", raw)
    wfo = tokens[0]

    tsoff = mx.DateTime.RelativeDateTime(hours= reference.offsets[nws.z])

    goodies = "\n".join( nws.sections[3:] )
    data = re.split("&&", goodies)
    lines = re.split("\n", data[0])

    _state = 0
    i = 0
    while (i < len(lines)):
        # Line must start with a number?
        if (len(lines[i]) < 40 or (re.match("[0-9]", lines[i][0]) == None)):
            i += 1
            continue
        # We can safely eat this line
        #0914 PM     HAIL             SHAW                    33.60N 90.77W
        tq = re.split(" ", lines[i])
        hh = tq[0][:-2]
        mm = tq[0][-2:]
        am = tq[1]
        type = (lines[i][12:29]).strip().upper()
        city = (lines[i][29:53]).strip().title()
        lalo = lines[i][53:]
        tokens = lalo.strip().split()
        lat = tokens[0][:-1]
        lon = tokens[1][:-1]

        i += 1
        # And safely eat the next line
        #04/29/2005  1.00 INCH        BOLIVAR            MS   EMERGENCY MNGR
        dstr = "%s:%s %s %s" % (hh,mm,am, lines[i][:10])
        ts = mx.DateTime.strptime(dstr, "%I:%M %p %m/%d/%Y")
        magf = (lines[i][12:29]).strip()
        mag = re.sub("(ACRE|INCHES|INCH|MPH|U|FT|F|E|M|TRACE)", "", magf)
        if (mag == ""): mag = 0
        cnty = (lines[i][29:48]).strip().title()
        st = lines[i][48:50]
        source = (lines[i][53:]).strip().lower()

        # Now we search
        searching = 1
        remark = ""
        while (searching):
            i += 1
            if (len(lines) == i):
                break
            #print i, lines[i], len(lines[i])
            if (len(lines[i]) == 0 or [" ","\n"].__contains__(lines[i][0]) ):
                remark += lines[i]
            else:
                break

        remark = remark.lower().strip()
        remark = re.sub("[\s]{2,}", " ", remark)
        remark = remark.replace("&", "&amp;")
        remark = remark.replace(">", "&gt;").replace("<","&lt;")

        gmt_ts = ts + tsoff
        if not reference.lsr_events.has_key(type):
            raise ProcessingException, "Unknown LSR typecode '%s'" % (type,)
        dbtype = reference.lsr_events[type]
        mag_long = ""
        if (type == "HAIL" and reference.hailsize.has_key(float(mag))):
            haildesc = reference.hailsize[float(mag)]
            mag_long = "of %s size (%s) " % (haildesc, magf)
        elif (mag != 0):
            mag_long = "of %s " % (magf,)
        time_fmt = "%I:%M %p"
        if (ts < (mx.DateTime.now() - mx.DateTime.RelativeDateTime(hours=12))):
            time_fmt = "%d %b, %I:%M %p"

        # We have all we need now
        unique_key = "%s_%s_%s_%s_%s_%s" % (gmt_ts, type, city, lat, lon, magf)
        if (lsrdb.has_key(unique_key)):
            log.msg("DUP! %s" % (unique_key,))
            continue
        lsrdb[ unique_key ] = mx.DateTime.gmt()

        uri = url_builder(lat,lon,gmt_ts.strftime("%Y-%m-%d%%20%H:%M"))
        jm = "%s:%s [%s Co, %s] %s reports %s %sat %s %s -- %s %s" % \
             (wfo, city, cnty, st, source, type, mag_long, \
              ts.strftime(time_fmt), nws.z, remark, uri)
        jmhtml = \
          "%s [%s Co, %s] %s <a href='%s'>reports %s %s</a>at %s %s -- %s" %\
          (city, cnty, st, source, uri, type, mag_long, \
           ts.strftime(time_fmt), nws.z, remark)
        jabber.sendMessage(jm,jmhtml)

        sql = "INSERT into lsrs_%s (valid, type, magnitude, city, \
               county, state, source, remark, geom, wfo, typetext) \
               values ('%s+00', '%s', %s, '%s', '%s', '%s', \
               '%s', '%s', 'SRID=4326;POINT(-%s %s)', '%s', '%s')" % \
          (gmt_ts.year, gmt_ts.strftime("%Y-%m-%d %H:%M"), dbtype, mag, \
           city.replace("'","\\'"), re.sub("'", "\\'",cnty), st, source, \
           re.sub("'", "\\'", remark), lon, lat, wfo, type)

        DBPOOL.runOperation(sql)

def url_builder(lat,lon,ts):
    uri = "http://mesonet.agron.iastate.edu/cow/maplsr.phtml"
    uri += "?lat0=%s&amp;lon0=-%s&amp;ts=%s" % (lat,lon,ts)
    return uri

myJid = jid.JID('iembot_ingest@%s/lsrParse_%s' \
    % (secret.chatserver, mx.DateTime.gmt().strftime("%Y%m%d%H%M%S") ) )
factory = client.basicClientFactory(myJid, secret.iembot_ingest_password)

jabber = common.JabberClient(myJid)

factory.addBootstrap('//event/stream/authd',jabber.authd)
factory.addBootstrap("//event/client/basicauth/invaliduser", jabber.debug)
factory.addBootstrap("//event/client/basicauth/authfailed", jabber.debug)
factory.addBootstrap("//event/stream/error", jabber.debug)

reactor.connectTCP(secret.connect_chatserver,5222,factory)

ldm = ldmbridge.LDMProductFactory( myProductIngestor() )
reactor.callLater( 20, cleandb)
reactor.run()

