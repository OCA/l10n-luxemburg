#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import with_statement
import re
import sys
import codecs
import tempfile
from subprocess import Popen, PIPE
import subprocess
import logging
import time
from datetime import datetime
from cStringIO import StringIO

def get_pdf_raw_data(filename):
    p = subprocess.Popen(['pdftotext', '-layout', filename, '-'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
    (out, err) = p.communicate()
    return out


period_re = ur'.*Période: ([0-9-]+) au ([0-9-]+).*Date: ([0-9-]+).*'
statement_number_re = ur'\s*Extrait n° (\S+)$'
amount_start_re = ur'.*Solde initial au ([0-9-]+)\s+([0-9,+-\.]+).*'
amount_end_re = ur'.*Solde final au ([0-9-]+)\s+([0-9,+-\.]+).*'
#line_re = ur'\s+([0-9-]+) (\S+?)\s{4,}(.+?)\s{4,}([0-9-]{10})\s+([0-9,\.+-]+)'
line_re = ur'\s*?([0-9-]+) (\S+?)\s{1,}(.+?)\s{4,}([0-9-]{10})\s+([0-9,\.+-]+)'
onlydesc_line_re = ur'^\s*(.+?)\s*$'
empty_line_re = ur'^\s*$'
account_iban_currency_re = ur'\s+Compte Courant : IBAN (.+)\s+?\((.+?)\)\s*'
report_re = ur'\s+Report\s+([0-9,\.+-]+)\s*'

ING_D_FORMAT = '%d-%m-%Y'

#XXX: make real logging
logging.basicConfig(level=logging.INFO)

class INGBankStatementParser(object):

    def __init__(self):
        self.iban = None
        self.currency = None
        self.mode = None
        self.period_start = None
        self.period_end = None
        self.date = None
        self.number = None
        self.amount_start = None
        self.amount_end = None
        self.lines = []

        self.set_mode('head')

    def set_mode(self, new_mode):
        assert new_mode in ('head', 'report', 'line_out', 'line_in', 'finished')
        self.mode = new_mode

    def to_monetary(self, txt):
        v = txt.strip().replace('.','').replace(',','.')
        return float(v)

    def is_valid(self):
        for k in ['period_start', 'period_end', 'amount_start', 'amount_end']:
            if getattr(self, k) is None:
                return False
        a = self.amount_start
        a += sum([ d['amount'] for d in self.lines ])
        if abs(a - self.amount_end) < 10 ** -4:
            return True
        return False

    def get_period_from_date(self, dt):
        #TODO: do a real search based on OERP periods
        return dt.strftime('%Y-%m')

    def is_multi_periods(self):
        periods = set([ self.get_period_from_date(d['maturity_date']) for d in self.lines ])
        return len(periods) > 1

    def parse(self, f):
        with tempfile.NamedTemporaryFile() as ftmp:
            ftmp.write(f.read())
            ftmp.flush()
            p = Popen(['pdftotext', '-layout', ftmp.name, '-'], stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True, bufsize=-1)
            (out, err) = p.communicate(input=f.read())
        self.parse_text(out)
        return self.get_statement_entries()

    def parse_text(self, text):
        c = StringIO(text)
        return self.parse_file(c)

    def parse_file(self, f):
        logger = logging.getLogger('parser')
        if isinstance(f, basestring):
            f = open(f, 'r')

        for i, line in enumerate(f.readlines()):
            line = unicode(line, 'utf-8')
            #print("[%s] line: %s" % (self.mode, line,))
            if self.mode == 'head':
                m = re.match(period_re, line)
                if m:
                    logger.debug("[match period] %s" % (m.groups(),))
                    self.period_start = datetime.strptime(m.groups()[0], ING_D_FORMAT)
                    self.period_end = datetime.strptime(m.groups()[1], ING_D_FORMAT)
                    self.date = datetime.strptime(m.groups()[1], ING_D_FORMAT)
                    continue
                m = re.match(statement_number_re, line)
                if m:
                    logger.debug("[match number] %s" % (m.groups(),))
                    self.number, = m.groups()
                    #self.set_mode('start')
                    continue
                m = re.match(account_iban_currency_re, line)
                if m:
                    _iban, _currency = m.groups()
                    self.iban = _iban.replace(' ','').strip()
                    self.currency = _currency.strip()
                    continue
                m = re.match(amount_start_re, line)
                if m:
                    logger.debug("[match amount start] %s" % (m.groups(),))
                    self.amount_start = self.to_monetary(m.groups()[1])
                    self.set_mode('line_out')
                    continue
            elif self.mode == 'line_out':
                m = re.match(amount_end_re, line)
                logger.debug('[.. test amount_end] %s' % (m,))
                if m:
                    logger.debug("[match amount end] %s" % (m.groups(),))
                    self.amount_end = self.to_monetary(m.groups()[1])
                    self.set_mode('finished')
                    continue
                m = re.match(line_re, line)
                logger.debug('[.. test line] %s' % (m,))
                if m:
                    data = m.groups()
                    logger.debug("[match line] %s" % (data,))
                    self.lines.append({
                        'date': datetime.strptime(data[0], ING_D_FORMAT),
                        'reference': data[1],
                        'name': data[2],
                        'maturity_date': datetime.strptime(data[3], ING_D_FORMAT),
                        'amount': self.to_monetary(data[4]),
                        'note': u'',
                    })
                    self.set_mode('line_in')
                    continue
                m = re.match(report_re, line)
                logger.debug('[.. test report] %s' % (m,))
                if m:
                    self.set_mode('report')
                    logger.debug('[> report] %s' % (line))
            elif self.mode == 'line_in':
                m = re.match(empty_line_re, line)
                if m:
                    logger.debug("[match empty line]")
                    self.set_mode('line_out')
                    continue
                m = re.match(onlydesc_line_re, line)
                if m:
                    logger.debug("[match line desc_only] %s" % (m.groups(),))
                    text, = m.groups()
                    self.lines[-1]['name'] += u'\n%s' % (text)
            elif self.mode == 'report':
                logger.debug('[report]')
                m = re.match(report_re, line)
                if m:
                    self.set_mode('line_out')
                    continue

        import pprint
        for k in ['iban', 'currency', 'period_start', 'period_end', 'date', 'number', 'amount_start', 'amount_end', 'lines']:
            v = getattr(self, k)
            if k == 'lines':
                #import pprint
                #pprint.pprint(v)
                pass
            else:
                print("%s: %s" % (k, v,))


    def get_statement_entries(self):
        if not self.is_valid():
            raise Exception('statement is not valid')

        multi = self.is_multi_periods()

        # group lines by periods
        line_by_period = []
        for l in self.lines:
            p = self.get_period_from_date(l['maturity_date'])
            for lp in line_by_period:
                if lp['__period'] == p:
                    lp['lines'].append(l)
                    lp['amount_end'] += l['amount']
                    lp['period_start'] = min(lp['period_start'], l['maturity_date'])
                    lp['period_end'] = max(lp['period_end'], l['maturity_date'])
                    break
            else:
                if not len(line_by_period):
                    amount_start = self.amount_start
                else:
                    amount_start = line_by_period[-1]['amount_end']
                line_by_period.append({
                    '__period': p,
                    'account': self.iban,
                    'account_type': 'iban',
                    'currency': self.currency,
                    'amount_start': amount_start,
                    'amount_end': amount_start + l['amount'],
                    'date': self.date,
                    'period_start': l['maturity_date'],
                    'period_end': l['maturity_date'],
                    'lines': [ l ],
                })
            #line_by_period.setdefault(p, []).append(l)

        s = self.amount_end - line_by_period[-1]['amount_end']
        if not s < 10 ** -4:
            raise Exception('Final statements amount is not valid')
        for i, lp in enumerate(line_by_period, 1):
            if multi:
                lp['name'] = u'Extrait N° %s (%d)' % (self.number, i)
            else:
                lp['name'] = u'Extrait N° %s' % (self.number)
        return line_by_period

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: ing_parser.py file.txt")
        sys.exit(2)

    t = get_pdf_raw_data(sys.argv[1])
    #print(type(t))
    ib = INGBankStatementParser()
    #ib.parse_file(sys.argv[1])
    ib.parse_text(t)

    print("==> Is valid: %s" % (ib.is_valid()))
    print("==> Is multi periods: %s" % (ib.is_multi_periods()))

    sts = ib.get_statement_entries()
    import pprint
    pprint.pprint(sts)



#import codecs
#
#lines = codecs.open(sys.argv[1], 'r', encoding='utf-8').readlines()
#for line in lines:
#    print("line: %s <%s>" % (line, type(line)))
#    m = re.match(period_re, line)
#    print("m1: %s" % (str(m)))
#    if m:
#        print("period matched: %s" % (m.groups(),))
#
#    m = re.match(statement_number_re, line)
#    print("m2: %s" % (str(m)))
#    if m:
#        print("statement number found: %s" % (m.groups(),))
#
