"""Parse CLI text products

The CLI report has lots of good data that is hard to find in other products,
so we take what data we find in this product and overwrite the database
storage of what we got from the automated observations
"""
from __future__ import print_function

from twisted.internet import reactor
from twisted.python import log
from pyldm import ldmbridge
from pyiem.nws.products import parser
from pyiem.network import Table as NetworkTable
import common

DBPOOL = common.get_database("iem", cp_max=1)
NT = NetworkTable("NWSCLI")
HARDCODED = {"PKTN": "PAKT"}


# LDM Ingestor
class MyProductIngestor(ldmbridge.LDMProductReceiver):
    """ I receive products from ldmbridge and process them 1 by 1 :) """

    def connectionLost(self, reason):
        """ Connection was lost! """
        log.err(reason)
        reactor.callLater(7, reactor.callWhenRunning, reactor.stop)

    def process_data(self, data):
        """ Process the product """
        deffer = DBPOOL.runInteraction(preprocessor, data)
        deffer.addErrback(common.email_error, data)


def send_tweet(prod):
    """ Send the tweet for this prod """

    jres = prod.get_jabbers(
        common.SETTINGS.get("pywwa_product_url", "pywwa_product_url")
    )
    for j in jres:
        jabber.send_message(j[0], j[1], j[2])


def preprocessor(txn, text):
    """ Protect the realprocessor """
    prod = parser(text)
    if not prod.data:
        return
    # Run each data through my local processor, which will set the db_station
    for data in prod.data:
        realprocessor(txn, prod, data)
        print(data["db_station"])
    # Run through database save now
    prod.sql(txn)
    send_tweet(prod)


def realprocessor(txn, prod, data):
    """ Actually do the work """
    # Can't always use the AFOS as the station ID :(
    if len(prod.data) > 1:
        station = None
        for stid in NT.sts.keys():
            if NT.sts[stid]["name"].upper() == data["cli_station"]:
                station = stid[1:]  # drop first char
                break
        if station is None:
            common.email_error(
                ("Unknown CLI Station Text: |%s|") % (data["cli_station"],),
                prod.unixtext,
            )
            return
    else:
        station = prod.afos[3:]
    data["db_station"] = "%s%s" % (prod.source[0], station)
    data["db_station"] = HARDCODED.get(data["db_station"], data["db_station"])

    table = "summary_%s" % (data["cli_valid"].year,)
    txn.execute(
        """
        SELECT max_tmpf, min_tmpf, pday, pmonth, snow from """
        + table
        + """ d
        JOIN stations t on (t.iemid = d.iemid)
        WHERE d.day = %s and t.id = %s and t.network ~* 'ASOS'
        """,
        (data["cli_valid"], station),
    )
    row = txn.fetchone()
    if row is None:
        print(
            ("No %s rows found for %s on %s")
            % (table, station, data["cli_valid"])
        )
        return
    updatesql = []
    logmsg = []

    if data["data"].get("temperature_maximum") is not None:
        climax = data["data"]["temperature_maximum"]
        if int(climax) != row["max_tmpf"]:
            updatesql.append(" max_tmpf = %s" % (climax,))
            logmsg.append("MaxT O:%s N:%s" % (row["max_tmpf"], climax))

    if data["data"].get("temperature_minimum") is not None:
        climin = data["data"]["temperature_minimum"]
        if int(climin) != row["min_tmpf"]:
            updatesql.append(" min_tmpf = %s" % (climin,))
            logmsg.append("MinT O:%s N:%s" % (row["min_tmpf"], climin))

    if data["data"].get("precip_month") is not None:
        val = data["data"]["precip_month"]
        if val != row["pmonth"]:
            updatesql.append(" pmonth = %s" % (val,))
            logmsg.append("PMonth O:%s N:%s" % (row["pmonth"], val))

    if data["data"].get("precip_today") is not None:
        val = data["data"]["precip_today"]
        if val != row["pday"]:
            updatesql.append(" pday = %s" % (val,))
            logmsg.append("PDay O:%s N:%s" % (row["pday"], val))

    if data["data"].get("snow_today") is not None:
        val = data["data"]["snow_today"]
        if row["snow"] is None or val != row["snow"]:
            updatesql.append(" snow = %s" % (val,))
            logmsg.append("Snow O:%s N:%s" % (row["snow"], val))

    if updatesql:
        txn.execute(
            """UPDATE """
            + table
            + """ d SET
        """
            + ",".join(updatesql)
            + """
         FROM stations t WHERE t.iemid = d.iemid and d.day = %s and t.id = %s
         and t.network ~* 'ASOS' """,
            (data["cli_valid"], station),
        )
        log.msg(
            ("%s rows for %s (%s) %s")
            % (
                txn.rowcount,
                station,
                data["cli_valid"].strftime("%y%m%d"),
                ",".join(logmsg),
            )
        )


if __name__ == "__main__":
    # Do Stuff
    jabber = common.make_jabber_client("cli_parser")
    ldmbridge.LDMProductFactory(MyProductIngestor())

    reactor.run()
