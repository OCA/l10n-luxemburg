# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution   
#    Copyright (C) 2004-2008 Tiny SPRL (<http://tiny.be>). All Rights Reserved
#    Copyright (C) 2009 AJM Technologies S.A.
#                                   (<http://www.ajm.lu>). All Rights Reserved
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

#Chargement du module csv
import csv

import pooler
import wizard
import base64
import time
import mx.DateTime
from mx.DateTime import RelativeDateTime, now, DateTime, localtime
import tools
from tools import ustr
from tools.translate import _
import unicodedata

from osv import osv
from osv import fields


class Namespace: pass


form = """<?xml version="1.0"?>
<form string="Payment Export">
   <field name="charges_code" />
   <field name="payment_method" />
   </form>"""

base_fields = {
    'payment_method' : {
        'string': 'Payment Method',
        'type': 'many2one',
        'relation': 'payment.method',
    },
    'charges_code' : {
        'string': 'Charges Code',
        'type': 'many2one',
        'relation': 'charges.code',
        'required': True,
    },
}

export_form = """<?xml version="1.0"?>
<form string="Payment Export Multiline">
   <field name="name" colspan="4"/>
   <field name="pay" filename="name"/>
   <field name="note" colspan="4" nolabel="1"/>
   </form>"""

export_fields = {
    'name': {
        'string': 'Name',
        'type': 'char',
        'size': '64',
        'required': True
    },
    'pay' : {
        'string':'Export File',
        'type':'binary',
        'required': False,
        'readonly': True,
    },
    'note' : {
        'string':'Log',
        'type':'text'
    },
}

def strip_accents(s):
    if isinstance(s, str):
        s = unicode(s, 'utf-8')
    s.replace(u'ß', 'ss')
    return ''.join((c for c in unicodedata.normalize('NFKD', s) if unicodedata.category(c) not in ('Mn','So', 'Pf', 'Sc')))

class Log:
    def __init__(self):
        self.content= ""
        self.error= False
    def add(self,s,error=True):
        self.content= self.content + s
        if error:
            self.error= error
    def __call__(self):
        return self.content

def _create_pay(self,cr,uid,data,context):
    log=Log()

#        if not bank:
#            return {'note':'Please Provide Bank for the Ordering Customer.', 'reference': payment.id, 'pay': False, 'state':'failed' }

#    if not payment.line_ids:
#         return {'note':'Wizard can not generate export file: there are no payment lines.', 'reference': payment.id, 'pay': False, 'state':'failed' }

    #####################################################
    #         Séquence 0  - initialisation              #
    #####################################################
    ns = Namespace()
    ns.multiline_data = u''
    ns.multiline_newline = u'\r\n'

    pool = pooler.get_pool(cr.dbname)

    # payment
    payment=pool.get('payment.order').browse(cr, uid, data['id'],context)

    # payment lines
    payment_line_obj=pool.get('payment.line')
    pay_line_ids = payment_line_obj.search(cr, uid, [('order_id','=',data['id'])])
    pay_lines = payment_line_obj.read(cr, uid, pay_line_ids,
                ['date','company_currency','currency',
                 'partner_id','amount','amount_currency',
                 'bank_id','move_line_id',
                 'name','info_owner','info_partner',
                 'communication','communication2',
                 'instruction_code_id']
    )
    # partner.bank
    partner_bank_obj = pool.get('res.partner.bank')
    # instruction.code
    paym_inst_code = pool.get('payment.instruction.code')
    # charges codes
    charges_code_obj = pool.get('charges.code')

    # payment type
    # :multi = one debit per line
    # :group = one debit for all lines
    payment_type = payment.payment_type
    if len(pay_lines) == 1 and payment_type == 'group':
        # Only one line, so no need to group payments
        payment_type = 'multi'

    payment_authz_mode = set()
    payment_mode_obj = self.pool.get('payment.mode')
    suitable_bank_types = payment_mode_obj.suitable_bank_types(cr, uid, payment_code =  payment.mode.id)
    for type in suitable_bank_types:
        payment_authz_mode.add(type)

    #####################################################
    #         Séquence 0  - utilities class / functions #
    #####################################################

    class MultilineDataException(Exception):
        def __init__(self, error):
            Exception.__init__(self, error)
            self.note = error
            self.reference = payment.id
            self.pay = False
            self.state = 'failed'

        def get_return_dict(self):
            return {
                'name': 'ERREUR GENERATION FICHIER',
                'note': self.note,
                'reference': self.reference,
                'pay': self.pay,
                'state': self.state
            }

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
        ns.multiline_data += _ml_string(code, string)
        ns.multiline_data += u"%s" % (ns.multiline_newline)

    def _ml_addlist_error_return(exception):
        pass

    def _ml_addlist(sequence_list, payment, payment_line=False,
                    mode='multi',sequence=-1):
        for (c, desc, l, m, s) in sequence_list:
            # Condition check, if False: line will not be added to datas
            if isinstance(m, (unicode,str)):
                if m and m != mode:
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
    #         Séquence 1  - functions                   #
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
            raise MultilineDataException(
                            u"pas de banque associée au compte bancaire")
        if not bank_id.bic:
            raise MultilineDataException(
                            u"pas de code BIC spécifié sur la banque")
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
        _ml_addlist(start_sequence, payment, mode=payment_type)
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
                    lambda *a: browse_one(paym_inst_code,
                                    pay['instruction_code_id']).code.upper()),
            ("32B", u'Devise et montant en devise',
                    15,
                    '',
                    "%s%s" % (pay['currency'][1].upper(),
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
                    lambda *a: browse_one(charges_code_obj, data['form']['charges_code']).name),
        ]
        try:
            _ml_addlist(payment_sequence_B, payment, payment_line=pay,
                        mode=payment_type, sequence=seq)
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
        _ml_addlist(payment_sequence_C, payment, mode=payment_type)
    except MultilineDataException, e:
        return e.get_return_dict()

    #####################################################
    #           Fin de création du fichier LUP          #
    #####################################################
    try:
        # Setup multiline data in place
        pay_order = strip_accents(ns.multiline_data)
        pay_order = pay_order.encode('ascii', 'ignore')
        log.add("Successfully Exported\n--\nSummary:\n\nTotal amount paid : %.2f \nTotal Number of Payments : %d \n-- " %(total,seq))
    except Exception, e:
        log.add("Export Failed\n"+ tools.ustr(e) + 'CORRUPTED FILE !\n')
        log.add(tools.ustr(strip_accents(ns.multiline_data)))
        return {
            'name': _('ERROR'),
            'note': log(),
            'reference': payment.id,
            'state': 'failed',
        }

    pool.get('payment.order').set_done(cr,uid,[payment.id],context)
    return {
        'note':log(),
        'reference': payment.id,
        'name': payment.reference.replace('/','-')+str(payment.id)+'.lup',
        'pay': base64.encodestring(pay_order),
        'state':'succeeded'
    }

def _log_create(self, cr, uid, data, context):
    pool = pooler.get_pool(cr.dbname)
    pool.get('account.pay').create(cr,uid,{
        'payment_order_id': data['form']['reference'],
        'note': data['form']['note'],
        'file': data['form']['pay'] and base64.encodestring(data['form']['pay'] or False),
        'state': data['form']['state'],
    })

    return {}

class wizard_pay_create(wizard.interface):
    states = {
        'init' : {
            'actions' : [],
            'result' : {'type' : 'form',
                        'arch' : form,
                        'fields' : base_fields,
                        'state' : [('end', 'Cancel'),('export','Export') ]}
        },
        'export' : {
            'actions' : [_create_pay],
            'result' : {'type' : 'form',
                        'arch' : export_form,
                        'fields' : export_fields,
                        'state' : [('close', 'Ok','gtk-ok') ]}
        },
        'close': {
            'actions': [_log_create],
            'result': {'type': 'state', 'state':'end'}
        }

    }
#wizard_pay_create('account.payment_create')

class wizard_payment_order_export(osv.osv_memory):
    _name = 'payment.order.export.wizard'
    _columns = {
        'charges_code': fields.many2one('charges.code', 'Charges Code', required=True),
        'payment_method': fields.many2one('payment.method', 'Payment Method'),
        'export_file': fields.binary('Export File', readonly=True),
        'export_filename': fields.char('Export Filename', size=128, readonly=True),
        'note': fields.text('Log', readonly=True),
        'state': fields.selection([('init','Init'),('export','Export')], 'State', required=True),
    }

    _defaults = {
        'state': 'init',
    }

    def button_payment_export(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        if not ids:
            return {}
        wizard = self.browse(cr, uid, ids[0], context=context)
        data = {
            'id': context.get('active_id', False),
            'form': {
                'charges_code': wizard.charges_code.id,
            },
        }
#        try:
        payment = _create_pay(self, cr, uid, data, context)
        payment_file = payment.pop('pay',False)
        payment['file'] = payment_file
#        except MultilineDataException, e:
#            self.write(cr, uid, [ids[0]], {
#                'name': _('ERROR DURING GENERATION'),
#                'note': str(e),
#                'state': 'export',
#            })
#            return {}
        self.write(cr, uid, [ids[0]], {
            'note': payment.get('note',''),
            'export_filename': payment.get('name',''),
            'export_file': payment_file,
            'state': 'export',
        })

        self.pool.get('account.pay').create(cr,uid, payment)

        print("Payment: %s" % (payment))
        return False

wizard_payment_order_export()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

