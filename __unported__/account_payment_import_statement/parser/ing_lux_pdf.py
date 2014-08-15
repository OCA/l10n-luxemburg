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


#XXX: make real logging
#logging.basicConfig(level=logging.INFO)

class INGBankStatementParser(object):
    ING_D_FORMAT = '%d-%m-%Y'
    ING_D2_FORMAT = '%d.%m.%Y'

    # generic regexp
    empty_line_re = ur'^\s*$'

    # main statement part regexp
    period_re = ur'.*Période: ([0-9-]+) au ([0-9-]+).*Date: ([0-9-]+).*'
    statement_number_re = ur'\s*Extrait n° (\S+)$'
    amount_start_re = ur'.*Solde initial au ([0-9-]+)\s+([0-9,+-\.]+).*'
    amount_end_re = ur'.*Solde final au ([0-9-]+)\s+([0-9,+-\.]+).*'
    #line_re = ur'\s+([0-9-]+) (\S+?)\s{4,}(.+?)\s{4,}([0-9-]{10})\s+([0-9,\.+-]+)'
    line_re = ur'\s*?([0-9-]+) (\S+?)\s{1,}(.+?)\s{4,}([0-9-]{10})\s+([0-9,\.+-]+)'
    onlydesc_line_re = ur'^\s*(.+?)\s*$'
    account_iban_currency_re = ur'\s+Compte Courant : IBAN (.+)\s+?\((.+?)\)\s*'
    report_re = ur'\s+Report\s+([0-9,\.+-]+)\s*'

    # detail statement part regexp
    detail_start_re = ur'\s+AVIS DE (DEBIT|CREDIT)\s+Date: ([0-9\.]+)\s*'
    detail_reference_re = ur'\s+Référence: (.*)\s*?'
    detail_party_re = ur"\s+(DONNEUR D'ORDRE|BENEFICIAIRE)\s+(DONNEUR D'ORDRE|BENEFICIAIRE)\s*?"
    detail_party_line_re = ur'\s+(.+?)\s{4,}(.+)\s*'

    detail_party_account_all_re = u'\s+Compte n°: (.*?)\s+\w{3}\s+Compte n°: (.*)\s*?'
    detail_party_account_left_re = u'\s+Compte n°: (.*)\s+\w{3}\s*'
    detail_party_date_name_re = ur'\s+Date valeur: ([0-9.]+)\s+Auprès de: (.*)\s*'
    detail_party_date_re = ur'\s+Date valeur: ([0-9.]+)\s*'


    detail_motif_amount_operation_re = ur'\s+MOTIF DE PAIEMENT\s+MONTANT OPERATION\s+([0-9+.,-]+)\s+(\w+).*'
    detail_motif_desc_re = ur'\s+(.*)\s*'
    #detail_end_amount = ur'\s+MONTANT DEBITE\s+([0-9.,+-]+)\s+(\w+)\s*'
    detail_end_amount_re = ur'.*\s+MONTANT (DEBITE|CREDITE)\s+([0-9.,+-]+)\s+(\w+)\s*'

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
        self.details = []

        self.set_mode('head')

    def set_mode(self, new_mode):
        assert new_mode in ('head', 'report', 'line_out', 'line_in',
                            'detail', 'detail_head', 'detail_party', 'detail_operation', 'detail_end',
                            'finished')
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
        s = self
        logger = logging.getLogger('parser')
        if isinstance(f, basestring):
            f = open(f, 'r')

        for i, line in enumerate(f.readlines()):
            line = unicode(line, 'utf-8')
            #print("[%s] line: %s" % (self.mode, line,))
            if self.mode == 'head':
                m = re.match(s.period_re, line)
                if m:
                    logger.debug("[match period] %s" % (m.groups(),))
                    self.period_start = datetime.strptime(m.groups()[0], s.ING_D_FORMAT)
                    self.period_end = datetime.strptime(m.groups()[1], s.ING_D_FORMAT)
                    self.date = datetime.strptime(m.groups()[1], s.ING_D_FORMAT)
                    continue
                m = re.match(s.statement_number_re, line)
                if m:
                    logger.debug("[match number] %s" % (m.groups(),))
                    self.number, = m.groups()
                    #self.set_mode('start')
                    continue
                m = re.match(s.account_iban_currency_re, line)
                if m:
                    _iban, _currency = m.groups()
                    self.iban = _iban.replace(' ','').strip()
                    self.currency = _currency.strip()
                    continue
                m = re.match(s.amount_start_re, line)
                if m:
                    logger.debug("[match amount start] %s" % (m.groups(),))
                    self.amount_start = self.to_monetary(m.groups()[1])
                    self.set_mode('line_out')
                    continue
            elif self.mode == 'line_out':
                m = re.match(s.amount_end_re, line)
                logger.debug('[.. test amount_end] %s' % (m,))
                if m:
                    logger.debug("[match amount end] %s" % (m.groups(),))
                    self.amount_end = self.to_monetary(m.groups()[1])
                    self.set_mode('detail')
                    continue
                m = re.match(s.line_re, line)
                logger.debug('[.. test line] %s' % (m,))
                if m:
                    data = m.groups()
                    logger.debug("[match line] %s" % (data,))
                    self.lines.append({
                        'date': datetime.strptime(data[0], s.ING_D_FORMAT),
                        'reference': data[1],
                        'name': data[2],
                        'maturity_date': datetime.strptime(data[3], s.ING_D_FORMAT),
                        'amount': self.to_monetary(data[4]),
                        'note': u'',
                        'details': {},
                    })
                    self.set_mode('line_in')
                    continue
                m = re.match(s.report_re, line)
                logger.debug('[.. test report] %s' % (m,))
                if m:
                    self.set_mode('report')
                    logger.debug('[> report] %s' % (line))
            elif self.mode == 'line_in':
                m = re.match(s.empty_line_re, line)
                if m:
                    logger.debug("[match empty line]")
                    self.set_mode('line_out')
                    continue
                m = re.match(s.onlydesc_line_re, line)
                if m:
                    logger.debug("[match line desc_only] %s" % (m.groups(),))
                    text, = m.groups()
                    self.lines[-1]['name'] += u'\n%s' % (text)
            elif self.mode == 'report':
                logger.debug('[report]')
                m = re.match(s.report_re, line)
                if m:
                    self.set_mode('line_out')
                    continue
            elif self.mode == 'detail':
                m = re.match(s.detail_start_re, line)
                if m:
                    _mode, _date = m.groups()
                    self.details.append({
                        'date': datetime.strptime(_date, s.ING_D2_FORMAT),
                        'maturity_date': datetime.strptime(_date, s.ING_D2_FORMAT),
                        'type': _mode.lower(), # debit / credit
                        'reference': '',
                        'company_info': '',
                        'company_account': '',
                        'party_info': '',
                        'party_account': '',
                        'party_bank': '', # bank name of beneficiary
                        'operation_info': '',
                        'operation_amount': 00, # operation amount (w/o extra charges) ?
                        'amount': 0.0,
                        'currency': '',
                    })
                    self.set_mode('detail_head')
                    continue
                m = re.match(s.detail_motif_amount_operation_re, line)
                if m:
                    op_amount = m.groups()[0]
                    self.details[-1]['operation_amount'] = self.to_monetary(op_amount)
                    self.set_mode('detail_operation')
                    continue
                m = re.match(s.detail_end_amount_re, line)
                if m:
                    _mode, _amount, _currency = m.groups()
                    self.details[-1].update({
                        'amount': self.to_monetary(_amount),
                        'currency': _currency,
                    })
                    continue

            elif self.mode == 'detail_head':
                m = re.match(s.detail_reference_re, line)
                if m:
                    self.details[-1]['reference'] = m.groups()[0]
                    continue
                m = re.match(s.detail_party_re, line)
                if m:
                    self.set_mode('detail_party')
                    continue
            elif self.mode == 'detail_party':
                m = re.match(s.empty_line_re, line)
                if m:
                    self.set_mode('detail')
                    continue
                d = self.details[-1]
                detail_type = d['type']
                if detail_type == 'debit':
                    m = re.match(s.detail_party_account_all_re, line)
                    if m:
                        d['company_account'], d['party_account'] = m.groups()
                        continue
                    m = re.match(s.detail_party_date_name_re, line)
                    if m:
                        _date, _party_bank = m.groups()
                        d.update({
                            'party_bank': _party_bank,
                            'maturity_date': datetime.strptime(_date, s.ING_D2_FORMAT),
                        })
                        continue
                elif detail_type == 'credit':
                    m = re.match(s.detail_party_account_left_re, line)
                    if m:
                        d['company_account'] = m.groups()[0]
                        continue
                    m = re.match(s.detail_party_date_re, line)
                    if m:
                        _date = m.groups()[0]
                        d.update({
                            'maturity_date': datetime.strptime(_date, s.ING_D2_FORMAT),
                        })
                        continue

                m = re.match(s.detail_party_line_re, line)
                if m:
                    txt_left, txt_right = m.groups()
                    # left is own company, right is third party
                    tnl = d['company_info'] and u'\n' or u''
                    d['company_info'] += tnl + txt_left
                    bnl = d['party_info'] and u'\n' or u''
                    d['party_info'] += bnl + txt_right
                    continue
                #m = re.match(s.
            elif self.mode == 'detail_operation':
                m = re.match(s.empty_line_re, line)
                if m:
                    self.set_mode('detail')
                    continue
                d = self.details[-1]
                detail_type = d['type']
                m = re.match(s.detail_motif_desc_re, line)
                txt = m.groups()[0]
                onl = d['operation_info'] and u'\n' or u''
                d['operation_info'] += onl + txt

        unmatched_details = []
        for d in self.details:
            for l in self.lines:
                r = []
                for k in ['date', 'maturity_date', 'amount', 'reference']:
                    r.append(d[k] == l[k])
                if all(r):
                    l['details'].update(d)
                    if d['type'] == 'debit':
                        p_1 = [
                            "DONNEUR D'ORDRE",
                            "===============",
                        ]
                        p_2 = "BENEFICIAIRE"
                    else:
                        p_1 = "BENEFICIAIRE"
                        p_2 = "DONNEUR D'ORDRE"
                    break

#                        'date': datetime.strptime(_date, s.ING_D2_FORMAT),
#                        'maturity_date': datetime.strptime(_date, s.ING_D2_FORMAT),
#                        'type': _mode.lower(), # debit / credit
#                        'reference': '',
#                        'company_info': '',
#                        'company_account': '',
#                        'party_info': '',
#                        'party_account': '',
#                        'party_bank': '', # bank name of beneficiary
#                        'operation_info': '',
#                        'operation_amount': 00, # operation amount (w/o extra charges) ?
#                        'amount': 0.0,
#                        'currency': '',
            else:
                unmatched_details.append(d)

        self.details = unmatched_details

        import pprint
        for k in ['iban', 'currency', 'period_start', 'period_end', 'date', 'number', 'amount_start', 'amount_end', 'lines', 'details']:
            v = getattr(self, k)
            if k == 'lines':
                #import pprint
                #pprint.pprint(v)
                pass
            elif k == 'details':
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
