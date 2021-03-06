""" SPC Watch Ingestor """

from twisted.python import log
from twisted.internet import reactor
from pyiem.nws.products.saw import parser as sawparser
from pyldm import ldmbridge
import common  # @UnresolvedImport

DBPOOL = common.get_database("postgis", cp_max=1)
IEM_URL = common.SETTINGS.get("pywwa_watch_url", "pywwa_watch_url")
JABBER = common.make_jabber_client("new_watch")


def shutdown():
    """Shut things down, please"""
    reactor.callWhenRunning(reactor.stop)  # @UndefinedVariable


class MyProductIngestor(ldmbridge.LDMProductReceiver):
    """ I receive products from ldmbridge and process them 1 by 1 :) """

    def connectionLost(self, reason):
        """STDIN is shut, so lets shutdown"""
        log.msg("connectionLost")
        log.err(reason)
        reactor.callLater(7, shutdown)  # @UndefinedVariable

    def process_data(self, data):
        """Process the product!"""
        df = DBPOOL.runInteraction(real_process, data)
        df.addErrback(common.email_error, data)


def real_process(txn, raw):
    """Process the product, please"""
    prod = sawparser(raw)
    if prod.is_test():
        log.msg("TEST watch found, skipping")
        return
    prod.sql(txn)
    prod.compute_wfos(txn)
    for (txt, html, xtra) in prod.get_jabbers(IEM_URL):
        JABBER.send_message(txt, html, xtra)


def main():
    """Go Main Go"""
    ldmbridge.LDMProductFactory(MyProductIngestor())
    reactor.run()  # @UndefinedVariable


if __name__ == "__main__":
    main()
