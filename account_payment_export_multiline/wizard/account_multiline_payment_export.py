# -*- coding: utf-8 -*-
##############################################################################
#
# Authors: Stéphane Bidoul & Olivier Laurent
# Copyright (c) 2012 Acsone SA/NV (http://www.acsone.eu)
# All Rights Reserved
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsibility of assessing all potential
# consequences resulting from its eventual inadequacies and bugs.
# End users who are looking for a ready-to-use solution with commercial
# guarantees and support are strongly advised to contact a Free Software
# Service Company.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

# Reference document related to ABBL VIR2000 format is available here:
# http://www.multiline.lu/fileadmin/media/downloads/VIR2000_fr.pdf

from osv import osv, fields

import base64
import time
import tools
from tools import ustr
from tools.translate import _
import unicodedata

class Log:
    def __init__(self):
        self.content = ""
    def add(self,s):
        self.content = self.content + s
    def __call__(self):
        return self.content

class MultilineDataException(Exception):
    def __init__(self, error):
        Exception.__init__(self, error)
        self.note = error

    def get_return_dict(self):
        return {
            'name': 'ERREUR GENERATION FICHIER',
            'note': self.note,
            'state': 'failed',
        }

def strip_accents(s):
    if isinstance(s, str):
        s = unicode(s, 'utf-8')
    s.replace(u'ß', 'ss')
    return ''.join((c for c in unicodedata.normalize('NFKD', s) if unicodedata.category(c) not in ('Mn','So', 'Pf', 'Sc')))

class multiline_payment_export(osv.TransientModel):
    _name = 'multiline.payment.export'
    _columns = {
        'charge_code_id': fields.many2one('multiline.payment.charge.code', 'Charge Code', required=True),
        'content': fields.binary('Exported Content', readonly=True),
        'filename': fields.char('Export Filename', size=128, readonly=True),
        'note': fields.text('Log', readonly=True),
        'state': fields.selection([('init','Init'),('export','Export')], 'State', required=True),
    }

    def default_get(self, cr, uid, fields, context=None):
        res = {'state': 'init'}
        
        ids = self.pool.get('multiline.payment.charge.code').search(cr, uid, [('code','=','OUR')], context=context)
        if ids:
            res['charge_code_id'] = ids[0]

        return res

    def _create_pay(self, cr, uid, data, context):
        #####################################################
        #         Sequence 0  - initialisation              #
        #####################################################
        
        log = Log()
    
        multiline_export = []
    
        # payment order
        payment = self.pool.get('payment.order').browse(cr, uid, data['id'], context)
    
        # payment lines
        payment_line_obj = self.pool.get('payment.line')
        pay_line_ids = payment_line_obj.search(cr, uid, [('order_id','=',data['id'])])
        pay_lines = payment_line_obj.read(cr, uid, pay_line_ids,
                    ['date','company_currency','currency',
                     'partner_id','amount','amount_currency',
                     'bank_id','move_line_id',
                     'name','info_owner','info_partner',
                     'communication','communication2',
                     'instruction_code_id']
        )
        
        # partner bank
        partner_bank_obj = self.pool.get('res.partner.bank')
        # instruction code
        instruction_code_obj = self.pool.get('multiline.payment.instruction.code')
        # charge code
        charges_code_obj = self.pool.get('multiline.payment.charge.code')
        # payment mode
        payment_mode_obj = self.pool.get('payment.mode')
    
        # payment type
        # :multi = one debit per line
        # :group = one debit for all lines
        if len(pay_lines) == 1:
            # Only one line, so no need to group payments
            grouped = False
        else:
            grouped = payment.grouped_payment

        suitable_bank_types = payment_mode_obj.suitable_bank_types(cr, uid, payment_code=payment.mode.id)
        payment_authz_mode = set()
        for type in suitable_bank_types:
            payment_authz_mode.add(type)
    
        #####################################################
        #         Sequence 0  - utilities class / functions #
        #####################################################
    
        def _ml_string_split(string, limit):
            s_list = []
            while len(string):
                # Remove unauthorized chars at line start
                while string[0] in (':','-'):
                    string = string[1:]
                s_list.append(string[:limit])
                string = string[limit:]
            return s_list
    
        def _ml_string_split_preformatted(string_list, limit):
            c_list = [
                string_list[0][:limit], # Name
                string_list[1][:limit], # Street
            ]
            if string_list[2] == 'Luxembourg':
                c_list += [
                    (string_list[3].ljust(10) + string_list[4])[:limit],
                ]
            else:
                c_list += [
                    (' '.join([ string_list[x] for x in (3, 4, 5, 2)]))[:limit],
                ]
            return c_list
    
        def _ml_string(code, string):
            s = u''
            if code:
                s += u":%s:" % (code)
            s += u"%s" % (string)
            s.replace('\n', '')
            return s
    
        def _ml_add(code, string):
            multiline_export.append(_ml_string(code, string))
    
        def _ml_addlist_error_return(exception):
            pass
    
        def _ml_addlist(sequence_list, payment, payment_line=False, mode=False, sequence=-1):
            for (c, desc, l, m, s) in sequence_list:
                # Condition check, if False: line will not be added to datas
                if isinstance(m, (unicode,str)):
                    if m and ((m != 'multi') != mode):
                        continue
                else:
                    try:
                        m_ret = m(payment, payment_line, mode)
                        if not m_ret:
                            continue
                    except MultilineDataException, e:
                        e_line = sequence != -1 and ('Ligne %s, %s:\n'%(sequence, payment_line['partner_id'][1])) or ''
                        e.note = '%s%s %s: %s' % (ustr(e_line),c,desc,ustr(e.note))
                        raise e
                # Execute function is it's one
                if callable(s):
                    try:
                        s = s(payment, payment_line)
                    except MultilineDataException, e:
                        # Add infos from local context
                        e_line = sequence != -1 and ('Ligne %s, %s:\n'%(sequence, payment_line['partner_id'][1])) or ''
                        e.note = u'%s%s %s: %s' % (e_line,c,desc,e.note)
                        raise e
                # Convert to list
                if not isinstance(s, list):
                    s = [ s ]
                for s_idx, s_val in enumerate(s):
                    s_val.encode('utf-8')
                    # check length limit
                    if l:
                        s_val = s_val[:l]
                    # add to datas
                    if s_idx == 0:
                        _ml_add(c, s_val)
                    else:
                        _ml_add('', s_val)
    
        def _ml_formatamount(amount, digit=12):
            # TODO: ... implement coma management
            s = ('%.2f' % (amount)).strip().replace(' ','')
            t = s.split('.')
            if len(t[0]) > digit:
                raise "AMOUT TOO BIG"
            return '%s,%s' % (t[0][:12], t[1][:2])
    
        #####################################################
        #         Sequence 1  - functions                   #
        #####################################################
    
        def browse_one(pool, id):
            if isinstance(id, tuple):
                id = id[0]
            return pool.browse(cr, uid, [id])[0]
    
        def _get_order_date_value(payment_order):
            date = ''
            if payment_order.date_prefered == 'fixed':
                date = payment_order.date_planned
            else:
                date = payment_order.date_created
            if date:
                return time.strftime('%y%m%d', time.strptime(date, '%Y-%m-%d'))
            else:
                return time.strftime('%y%m%d')
    
        def _get_bank_bic(partner_bank_id):
            # type = partner / beneficiary
            bank_id = partner_bank_id.bank
            if not bank_id:
                raise MultilineDataException(u"pas de banque associée au compte bancaire")
            if not bank_id.bic:
                raise MultilineDataException(u"pas de code BIC spécifié sur la banque")
            return bank_id.bic
    
        def _get_bank_account(bank_id, with_owner_info=True,
                                       use_owner_code=False,
                                       no_compress_line=False):
            data = ''
            if not bank_id:
                raise MultilineDataException(u"pas de compte bancaire spécifié")
            if bank_id.state == 'iban':
                data += bank_id.iban.replace(' ','').upper()
            else:
                data += bank_id.acc_number[:34].upper()
            if with_owner_info:
                t_list = []
                s_list = [
                    (bank_id.owner_name and bank_id.owner_name.strip() \
                        or (use_owner_code and bank_id.partner_id.ref or
                            bank_id.partner_id.name)),
                    (bank_id.street and bank_id.street.strip() or ''),
                    (bank_id.country_id and bank_id.country_id.name or ''),
                    (bank_id.zip and bank_id.zip.strip() or ''),
                    (bank_id.city and bank_id.city or ''),
                    (bank_id.state_id and bank_id.state_id.name or ''),
                ]
    
                if no_compress_line:
                    t_list = _ml_string_split_preformatted(s_list, 35)
                else:
                    s_list = [ x for x in s_list if x ]
                    s = u' '.join(s_list)
                    t_list = _ml_string_split(s, 35)
    
                if len(t_list) > 4:
                    t_list = t_list[:4]
    
            return [ u"/" + data ] + t_list
    
        def _get_account(pay):
            if not pay['bank_id']:
                raise MultilineDataException(u"pas de compte bancaire spécifié")
            return browse_one(partner_bank_obj, pay['bank_id'])
    
        def _get_communication(pay):
            s = (pay['communication'] or u'')
            s += (pay['communication2'] or u'')
            # don't allow double point or accentuated char to crash multiline import
            s = strip_accents(s).replace(':','') 
            s_list = _ml_string_split(s, 35)
            return s_list[:4]
    
        #####################################################
        #         Séquence A  - début de fichier            #
        #####################################################
        start_sequence = [
            ("20",  u'Identification débiteur',
                    16,
                    '',
                    payment.mode.multiline_ident),
            ("21R", u'Libellé opération virement collectif/groupé',
                    16,
                    'group',
                    payment.reference),
            ("50H", u'Compte bancaire du donneur d\'ordre',
                    35,
                    'group',
                    lambda *a: _get_bank_account(payment.mode.bank_id, use_owner_code=True, no_compress_line=True)),
            ("52A", u'Code bic de la banque du donneur d\'ordre',
                    8,
                    '',
                    lambda *a: _get_bank_bic(payment.mode.bank_id).upper()),
            ("30",  u'Date d\'éxécution souhaitée',
                    6,
                    '',
                    lambda *a: _get_order_date_value(payment)),
        ]
        try:
            _ml_addlist(start_sequence, payment, mode=grouped)
        except MultilineDataException, e:
            return e.get_return_dict()
    
        #####################################################
        #       Séquence B - Une séquence par paiement      #
        #####################################################
        seq = 0
        total = 0.0
        for pay in pay_lines:
            seq += 1
    
            try:
                account_pay_state = _get_account(pay).state
            except MultilineDataException, e:
                e.note = u'Ligne: %s: %s' % (seq, e.note)
                return e.get_return_dict()
    
            if account_pay_state not in payment_authz_mode:
                e = MultilineDataException("")
                e.note = u"Ligne %s: %s: compte bancaire n'est pas de type IBAN, impossible d'exporter" % (seq, pay['partner_id'] and pay['partner_id'][1] or '???')
                return e.get_return_dict()
    
            payment_sequence_B = [
                ("21", u'Référence de l\'opération',
                        16,
                        'multi',
                        pay['name'] and (payment.reference+'-'+pay['name']) or payment.reference),
                ("23E", u'Instruction banque donneur d\'ordre',
                        35,
                        lambda *a: pay['instruction_code_id'] and True or False,
                        lambda *a: browse_one(instruction_code_obj, pay['instruction_code_id']).code.upper()),
                ("32B", u'Devise et montant en devise',
                        15,
                        '',
                        "%s%s" % (pay['currency'][1].split(' ',1)[0].upper(),
                                  _ml_formatamount(pay['amount_currency']))),
                ("50H", u'Compte bancaire du donneur d\'ordre',
                        0,
                        'multi',
                        lambda paym, *a: _get_bank_account(paym.mode.bank_id,
                                                use_owner_code=True,
                                                no_compress_line=True)),
                ("57A", u'Code BIC banque bénéficiaire',
                        15,
                        lambda *a: _get_account(pay).state == 'iban',
                        lambda *a: _get_bank_bic(_get_account(pay)).upper()),
                ("57D", u'Nom de la banque du bénéficiare (car pas de code BIC',
                        0,
                        lambda *a: _get_account(pay).state != 'iban',
                        "TODO: Nom de la banque du bénéficiaire"),
                ("59", u'Numéro du compte bancaire du bénéficiaire',
                        0,
                        '',
                        lambda *a: _get_bank_account(_get_account(pay))),
                ("70", u'Libellé de l\'opération',
                        # 1ere ligne peut etre ref standard national: ***14x*** 
                        0,
                        '',
                        lambda *a: _get_communication(pay)),
                ("77B", u'Information IBLC pour montant > 8676,2733 EUR',
                        0,
                        lambda *a: False, # TODO
                        "TODO Information IFBL"),
                ("71A", u'Mode de facturation des frais bancaire',
                        3,
                        '',
                        lambda *a: data['charge_code']),
            ]
            try:
                _ml_addlist(payment_sequence_B, payment, payment_line=pay,
                            mode=grouped, sequence=seq)
                total += pay['amount_currency']
            except MultilineDataException, e:
                return e.get_return_dict()
    
        #####################################################
        #           Séquence C  - Fin de fichier            #
        #####################################################
        payment_sequence_C = [
            ("19A", u'Nombre de paiement(s)',
                    5,
                    '',
                    unicode(seq).upper()),
            ("19", u'Montant total toutes devises confondues',
                    17,
                    '',
                    unicode(_ml_formatamount(total)).upper()),
        ]
        try:
            _ml_addlist(payment_sequence_C, payment, mode=grouped)
        except MultilineDataException, e:
            return e.get_return_dict()
    
        #####################################################
        #           Fin de création du fichier LUP          #
        #####################################################
        mx = u'\r\n'.join(multiline_export)

        try:
            # Setup multiline data in place
            pay_order = strip_accents(mx)
            pay_order = pay_order.encode('ascii', 'ignore')
            log.add("Successfully Exported\n--\nSummary:\n\nTotal amount paid : %.2f \nTotal Number of Payments : %d \n-- " %(total,seq))
        except Exception, e:
            log.add("Export Failed\n" + tools.ustr(e) + 'CORRUPTED FILE !\n')
            log.add(tools.ustr(strip_accents(mx)))
            return {
                'name': _('ERROR'),
                'note': log(),
                'state': 'failed',
            }
    
        return {
            'name': payment.reference.replace('/','-') + str(payment.id) + '.lup',
            'note': log(),
            'content': base64.encodestring(pay_order),
            'state': 'succeeded',
        }

    def export(self, cr, uid, ids, context=None):
        if context is None:
            context = {}

        payment_order_id = context.get('active_id', False)

        wizard = self.browse(cr, uid, ids[0], context=context)
        data = {
            'id': payment_order_id,
            'charge_code': wizard.charge_code_id.code,
        }

        payment = self._create_pay(cr, uid, data, context)
        content = payment.pop('content', False)

        self.write(cr, uid, [ids[0]], {
            'content': content,
            'filename': payment.get('name', ''),
            'note': payment.get('note',''),
            'state': 'export',
        })

        self.pool.get('multiline.payment.export.history').create(cr, uid, {
            'payment_order_id': payment_order_id,
            'state': payment['state'],
            'content': content,
            'note': payment.get('note', ''),
        })

        return False

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
