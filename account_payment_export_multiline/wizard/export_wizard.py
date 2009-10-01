# -*- coding: utf-8 -*-
#####################################################
#          Module Wizard paiement Multiline         #
#                 AJM Technologies SA               #
#####################################################


#Chargement du module csv
import csv

import pooler
import wizard
import base64
from osv import osv
import time
import mx.DateTime
from mx.DateTime import RelativeDateTime, now, DateTime, localtime
import tools
from tools import ustr
import unicodedata

class Namespace: pass


form = """<?xml version="1.0"?>
<form string="Payment Export">
   <field name="charges_code" />
   <field name="payment_method" />
   </form>"""

fields = {
    'payment_method' : {
        'string':'Payment Method',
        'type':'many2one',
        'relation':'payment.method',
    },
    'charges_code' : {
        'string':'Charges Code',
        'type':'many2one',
        'relation':'charges.code',
        'required':True,
    },
}

export_form = """<?xml version="1.0"?>
<form string="Payment Export">
   <field name="pay"/>
   <field name="note" colspan="4" nolabel="1"/>
   </form>"""

export_fields = {
    'pay' : {
        'string':'Export File',
        'type':'binary',
        'required': False,
        'readonly':True,
    },
    'note' : {'string':'Log','type':'text'},
}

def strip_accents(s):
    if isinstance(s, str):
        s = unicode(s, 'utf-8')
    return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))

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

    pool = pooler.get_pool(cr.dbname)
    payment=pool.get('payment.order').browse(cr, uid, data['id'],context)

#        if not bank:
#            return {'note':'Please Provide Bank for the Ordering Customer.', 'reference': payment.id, 'pay': False, 'state':'failed' }

    pay_line_obj=pool.get('payment.line')
    pay_line_id = pay_line_obj.search(cr, uid, [('order_id','=',data['id'])])

#    if not payment.line_ids:
#         return {'note':'Wizard can not generate export file: there are no payment lines.', 'reference': payment.id, 'pay': False, 'state':'failed' }

    ### AJM modified code ###
    ns = Namespace()
    ns.multiline_data = u''
    ns.multiline_newline = u'\r\n'

    def _ml_string_split(string, limit):
        s_list = []
        while len(string):
            # Remove unauthorized chars at line start
            while string[0] in (':','-'):
                string = string[1:] 
            s_list.append(string[:limit])
            string = string[limit:]
        return s_list

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

    def _ml_addlist(sequence_list, payment, payment_line=False, mode='multi'):
        for (c, l, m, s) in sequence_list:
            # Condition check, if False: line will not be added to datas
            if isinstance(m, (unicode,str)):
                if m and m != mode:
                    continue
            else:
                if not m(payment, payment_line, mode):
                    continue
            # Execute function is it's one
            if callable(s):
                s = s(payment, payment_line)
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
    #         Séquence 0  - initialisation              #
    #####################################################

    # payment
    payment=pool.get('payment.order').browse(cr, uid, data['id'],context)

    # payment lines
    payment_line_obj=pool.get('payment.line')
    pay_lines = payment_line_obj.read(cr, uid, pay_line_id,
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
            raise "ERROR"
        if not bank_id.bic:
            raise "ERROR"
        return bank_id.bic

    def _get_bank_account(bank_id, with_owner_info=True):
        data = ''
        if bank_id.state == 'iban':
            data += bank_id.iban.replace(' ','').upper()
        else:
            data += bank_id.acc_number[:34].upper()
        if with_owner_info:
            s_list = [
                (bank_id.owner_name and bank_id.owner_name.strip() or bank_id.partner_id.name),
                (bank_id.street and bank_id.street.strip() or ''),
                (bank_id.country_id and bank_id.country_id.name or ''),
                (bank_id.zip and bank_id.zip.strip() or ''),
                (bank_id.city and bank_id.city or ''),
                (bank_id.state_id and bank_id.state_id.name or ''),
            ]
            s_list = [ x for x in s_list if x ]
            s = u' '.join(s_list)

            t_list = _ml_string_split(s, 35)
            if len(t_list) > 4:
                t_list = t_list[:4]

        return [ u"/" + data ] + t_list
                        
    def _get_account(pay):
        return browse_one(partner_bank_obj, pay['bank_id'])

    def _get_communication(pay):
        s = (pay['communication'] or u'')
        s += (pay['communication2'] or u'')
        s_list = _ml_string_split(s, 35)
        return s_list[:4]

    #####################################################
    #         Séquence A  - début de fichier            #
    #####################################################
    start_sequence = [
        #:20: Identification débiteur
        ("20",  16, '',
                payment.mode.multiline_ident),
        #:21R: Libellé opération si virement de type collectif
        ("21R", 16, 'group',
                payment.reference),
        #:50H: Compte du donneur d'ordre
        ("50H", 35, 'group',
                lambda *a: _get_bank_account(payment.mode.bank_id)),
        #:52A: Code bic du donneur d'ordre	
        ("52A", 8,  '',
                lambda *a: _get_bank_bic(payment.mode.bank_id).upper()),
        #:30: Date d'exécution souhaitée
        ("30",  6, '',
                lambda *a: _get_order_date_value(payment)),
    ]
    _ml_addlist(start_sequence, payment, mode=payment_type)

    #####################################################
    #       Séquence B - Une séquence par paiement      #
    #####################################################
    seq = 0
    total = 0.0
    for pay in pay_lines:
        seq += 1

        payment_sequence_B = [
            #:21: Référence de l'opération (payment multiple)
            ("21", 16,
                    'multi',
                    pay['name'] and (payment.reference+'-'+pay['name']) or payment.reference),
            #:23E: Instruction banque donneur d'ordre
            ("23E", 35,
                    lambda *a: pay['instruction_code_id'] and True or False,
                    lambda *a: browse_one(paym_inst_code, pay['instruction_code_id']).code.upper()),
            #:32B: Devise et Montant en devis
            ("32B", 15,
                    '',
                    "%s%s" % (pay['currency'][1].upper(), _ml_formatamount(pay['amount_currency']))),
            #:50H: Compte du donneur d'ordre / virement simple
            #      ou si veut un débit unique par opération.	
            ("50H", 0,
                    'multi',
                    lambda paym, *a: _get_bank_account(paym.mode.bank_id)),
            #:57A: Code BIC banque du bénéficiaire
            ("57A", 15,
                    lambda *a: _get_account(pay).state == 'iban',
                    lambda *a: _get_bank_bic(_get_account(pay)).upper()),
            #:57D: Nom de la banque du bénéficiare - si :59: <> code IBAN 	
            ("57D", 0,
                    lambda *a: _get_account(pay).state != 'iban',
                "TODO: Nom de la banque du bénéficiaire"),
            #:59: Numéro de compte banque du bénéficiaire 
            ("59",  0,
                    '',
                    lambda *a: _get_bank_account(_get_account(pay))),
            #:70: Libellé de l'opération
            #     1ere ligne peut etre ref standard national: ***14x*** 
            ("70",  0,
                    '',
                    lambda *a: _get_communication(pay)),
            #:77B: Information IBLC
            ("77B", 0,
                    lambda *a: False, # TODO
                    "TODO Information IFBL"),
            #:71A: Mode facturation Frais
            ("71A", 3,
                    '',
                    lambda *a: browse_one(charges_code_obj, data['form']['charges_code']).name),
        ]
        _ml_addlist(payment_sequence_B, payment, payment_line=pay, mode=payment_type)
        total += pay['amount_currency']     

    #####################################################
    #           Séquence C  - Fin de fichier            #
    #####################################################
    payment_sequence_C = [
        #:19A: Nombre de paiement - Obligatoire	
        ("19A", 5,
                '',
                unicode(seq).upper()),
        #:19: Montant total toutes devises confondues
        ("19",  17,
                '',
                unicode(_ml_formatamount(total)).upper()),
    ]
    _ml_addlist(payment_sequence_C, payment, mode=payment_type)

    #####################################################
    #           Fin de création du fichier LUP          #
    #####################################################
    try:
        # Setup multiline data in place
        pay_order = strip_accents(ns.multiline_data)
        pay_order = pay_order.encode('ascii')
        log.add("Successfully Exported\n--\nSummary:\n\nTotal amount paid : %.2f \nTotal Number of Payments : %d \n-- " %(total,seq))
    except Exception, e:
        print e
        log= log +'\n'+ str(e) + 'CORRUPTED FILE !\n'
        raise e

    pool.get('payment.order').set_done(cr,uid,payment.id,context)
    return {
        'note':log(),
        'reference': payment.id,
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
                        'fields' : fields,
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
wizard_pay_create('account.payment_create')
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

