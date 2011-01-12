#!/usr/bin/python

import os
import sys
from datetime import datetime
from datetime import date

class mt940e_account_info():
    def __init__(self, data):
        self.data = data
        self.ndata = len(data)
        self.offset = self.data.find('?')

    def __iter__(self):
        return self

    def next(self):
        if self.offset == -1:
            raise StopIteration

        next = self.data.find('?', self.offset+1)
        code = self.data[self.offset+1:self.offset+3]
        if next != -1:
            info = self.data[self.offset+3:next]
        else:
            info = self.data[self.offset+3:]
        self.offset = next
        return (code, info)

class mt940e_parser(object):
    _tagsep = ':'

    _code_map = {
        '20': 'type',
        '25': 'account_nb',
        '28': 'name',
    }

    def t_get_date(self, raw):
#        print(">>> parse date: _%s_" % (raw))
        return date(year=2000+int(raw[0:2]), month=int(raw[2:4]), day=int(raw[4:6]))

    def t_get_sign(self, raw):
#        print(">>> parse sign: _%s_" % (raw))
        return {
            'C': 1,
            'D': -1,
            #RC: ??
            #RD: ??
        }[raw.strip()]

    def t_get_amount(self, raw):
#        print(">>> parse amount: _%s_" % (raw))
        return float(raw.replace(',','.'))

    def t_get_swift_code(self, raw):
#        print(">>> parse swift code: _%s_" % (raw))
        if raw[0] != 'N':
            raise Exception("Invalid Swift Code, should start with N, %s" % (raw))
        return raw[1:4]

    def code_simple_store(self, code, data):
        self.data[self._code_map[code]] = data
        return True

    def p_opening_balance(self, code, data):
        sign = self.t_get_sign(data[0])
        d = self.t_get_date(data[1:7])
        currency = data[7:10]
        abs_amount = self.t_get_amount(data[10:])
        self.data.update({
            'date_start': d,
            'currency': currency,
            'balance_start': abs_amount * sign,
        })
#        print("Sign: %s" % (sign))
#        print("Data: %s" % (d))
#        print("Currency: %s" % (currency))
#        print("Abs Amount: %s" % (abs_amount))

    def p_ending_balance(self, code, data):
        sign = self.t_get_sign(data[0])
        d = self.t_get_date(data[1:7])
        currency = data[7:10]
        abs_amount = self.t_get_amount(data[10:])
#        print("Sign: %s" % (sign))
#        print("Data: %s" % (d))
#        print("Currency: %s" % (currency))
#        print("Abs Amount: %s" % (abs_amount))
        if self.data.get('currency') != currency:
            raise Exception("Invalid bank statement, opening and ending currency differs")
        self.data.update({
            'date_end': d,
            'balance_end': abs_amount * sign,
        })

    def p_transfert_statement(self, code, data):
        d = self.t_get_date(data[0:6]) # = 6
        entry_d = data[6:10] # = 4
        sign = self.t_get_sign(data[10:12]) # = 2
        amount = self.t_get_amount(data[12:27])
        swift_code = self.t_get_swift_code(data[27:31])
        owner_reference = data[31:47]
#        print("### SWIFT CODE: %s, OWNER REF: %s" % (swift_code, owner_reference))
        bank_reference = data[47:]
#        if not bank_reference.lstrip().startswith('//'):
#            raise Exception("Invalid bank reference _%s_" % (bank_reference))

        new_line = {
            'date': d,
            'entry_date': entry_d,
            'amount': sign * amount,
            'swift_code': swift_code,
            'owner_reference': owner_reference,
            'bank_reference': bank_reference,
        }
#        print("NEW LINE: %s" % (new_line))
        self.data['lines'].append(new_line)

    def p_transfert_accountinfo(self, code, data):
        gvc = int(data[0:2])
        _infocode = {
            '00': [27, 'reference', 'Trans. Descr. / Payment. Origin'],
            '20': [27, 'details', 'Debit/Credit AccountBankInfo with leading Zero'],
            '21': [10, 'details', ''],
            '22': [27, 'details', ''],
            #'23': [27, 'client_info', ''],
            #'24': [27, 'beneficiary', ''],
            #'25': [27, 'beneficiary', ''],
            '26': [27, 'original_amount', ''],
            '27': [27, 'charges', ''],
            '28': [27, 'exchange_rate', ''],
            #'29': [27, 'exchange_rate', ''],
            #'30': [8, 'bank_code', ''],
            '31': [24, 'communication', ''],
            '32': [27, 'beneficiary', ''],
            '33': [27, 'beneficiary', ''],
            '38': [31, 'iban', ''],
        }
        cline = data[2:]
        cdata = {
            'reference': '',
#            'trans_num': '',
            'details': '',
            'amount_currency': '',
            'communication': '',
            'charges': '',
            'exchange_rate': '',
#            'account_info': '',
#            'client_info': '',
            'beneficiary': '',
#            'bank_code': '',
            'original_amount': '',
#            'beneficiary_name': '',
            'iban': '',
        }
        def update_extra(content):
            _, type, val, _ = content.split('/')
            if type == 'OCMT':
                cdata['original_amount'] = self.t_get_amount(val[3:])
            elif type == 'CHGS':
                cdata['charges'] = self.t_get_amount(val[3:])
            elif type == 'EXCH':
                cdata['exchange_rate'] = self.t_get_amount(val)

        info = mt940e_account_info(cline)
        for (c, i) in info:
#            print("C: %s, I: %s" % (c, i))
            if not c or not i:
                continue
#            print("C: %s %s" % (c, type(c)))
            try:
                if c in ('26', '27', '28'):
                    update_extra(i)
                else:
#                if c in ('21', '22', '33') and len(i) > 7:
#                    print("FIXUP?")
#                    if not cdata[_infocode[c][1]][-1:].isspace() \
#                            and not i[0].isspace():
#                        i = ' %s' % (i)
#                    ipos = i[7:].find(' ')
#                    if ipos != -1:
#                        k = i[:ipos+7] + i[ipos+1+7:]
#                        print("FIXUP: %s" % (k))
#                        i = k
                    cdata[_infocode[c][1]] += i
            except KeyError:
                raise Exception("Unknonw account info code %s" % (c))
#        offset = 0
#        while True:
#            x = cline.find('?', offset)
#            print("X: %s" % (x))
#            if x == -1:
#                break
#            offset = x+1
        # cleanup details fields (extra space are added every 35 chars)
        def cleanup_text_field(text, range):
            z = ''
            t = text
            while t:
                z += t[:range]
                t = t[range:]
                if t:
                    t = t[1:]
#            print("----> Z: %s" % (z))
            return t

        #cdata['details'] = cleanup_text_field(cdata['details'], 35)
        #cdata['beneficiary'] = cleanup_text_field(cdata['beneficiary'], 32)

#        print("CDATA: %s" % (cdata))
        self.data['lines'][-1].update(cdata)

    _codes = {
        '20': code_simple_store,
        '25': code_simple_store,
        '28': code_simple_store,
        '60F': p_opening_balance,
        '61': p_transfert_statement,
        '86': p_transfert_accountinfo,
        '62F': p_ending_balance,
    }

    def __init__(self):
        self.elem = []
        self.data = {
            'type': '',
            'account_nb': '',
            'name': '',
            'date_start': '', # date of opening balance
            'date_end': '',
            'balance_start': '',
            'balance_end': '',
            'currency': '',
            'lines': [],
        }
        pass

    def parse(self, f):
#        print("%s" % (self._tagsep))
        for l in f.readlines():
            l = l.replace('\r\n','')
            if l and l[0] == self._tagsep:
                self.elem.append(l)

            else:
                self.elem[-1] += l

        for e in self.elem:
#            print(e)
            code, d = e[1:].split(self._tagsep, 1)
#            print("Code: %s, D: %s" % (code, d))
            if code in self._codes:
                self._codes[code](self, code, d)

#        print("Summary:")
#        print("========")
#        print("Type: %s" % (self.data['type']))
#        print("Account: %s" % (self.data['account_nb']))
#        print("Number: %s" % (self.data['name']))
#        print("Start: %16s %s" % (self.data['date_start'], self.data['balance_start']))
#        print("End: %16s %s" % (self.data['date_end'], self.data['balance_end']))
#        print("Lines: %s" % (len(self.data['lines'])))

if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print("usage: mt940e_parser file")
        sys.exit()
    p = mt940e_parser()
    f = open(sys.argv[1])
    p.parse(f)

