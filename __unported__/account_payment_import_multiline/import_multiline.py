# -*- coding: utf-8 -*-
##############################################################################
#
#    account_payment_import_multiline module for OpenERP, eletronic bank statement import
#    Copyright (C) 2011 Thamini S.à.R.L (<http://www.thamini.com>) Xavier ALT
#
#    This file is a part of account_payment_import_multiline
#
#    account_payment_import_multiline is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    account_payment_import_multiline is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import re
import base64
from StringIO import StringIO
from osv import osv
from osv import fields
from tools.translate import _
from tools.misc import logged
from mt940e_parser import mt940e_parser

class account_bank_statement_mt940e_import_wizard_line(osv.osv_memory):
    _name = 'account.bank.statement.mt940e.import.wizard.line'
account_bank_statement_mt940e_import_wizard_line()

class account_bank_statement_mt940_import_wizard(osv.osv_memory):
    _name = 'account.bank.statement.mt940e.import.wizard'

    _STATES = [
        ('init', 'Choose File'),
        ('check_import', 'Check Imported Data'),
        ('already_imported', 'Already Imported'),
        ('create_statement', 'Create Statement'),
        ('import_failed', 'Import Failed'),
    ]

    def _compute_balance_end(self, cr, uid, ids, fn, args, context=None):
        res = dict.fromkeys(ids, 0.0)
        for stw in self.browse(cr, uid, ids, context=context):
            balance = 0.0
            for line in stw.line_ids:
                balance += line.amount
            res[stw.id] = stw.balance_start + balance
        return res

    def _get_currency_id(self, cr, uid, ids, fieldname, args, context=None):
        result = dict.fromkeys(ids, False)
        for wizard in self.browse(cr, uid, ids, context=context):
            journal = wizard.journal_id
            if not journal:
                continue
            print("wizard: %s, journal: %s" % (str(wizard), str(journal)))
            if journal.currency:
                result[wizard.id] = journal.currency.id
            else:
                result[wizard.id] = journal.company_id.currency_id.id
        return result

    _columns = {
        # step 1
        'file': fields.binary('File'),
        'filename': fields.char('Filename', size=128),

        # step 2
        'format': fields.char('Format', size=32, readonly=True),
        'name': fields.char('Name', size=64),
        'date': fields.date('Date'),
        'period_id': fields.many2one('account.period', 'Period'),
        'journal_id': fields.many2one('account.journal', 'Journal'),
#        'currency_id': fields.related('journal_id', 'currency', type='many2one', relation='res.currency', string='Currency', readonly=True),
        'currency_id': fields.function(_get_currency_id, type='many2one', relation='res.currency', string='Currency', method=True, readonly=True),
        'balance_start': fields.float('Balance Start'),
        'balance_end': fields.float('Balance End'),
        'balance_end_computed': fields.function(_compute_balance_end, type='float', string='Computed Balance End', readonly=True, method=True),
        'line_ids': fields.one2many('account.bank.statement.mt940e.import.wizard.line', 'wizard_id', 'Lines'),
        'error_msg': fields.text('Error Message', size=255),
        'state': fields.selection(_STATES, 'State', readonly=True),
    }

    _defaults = {
        'state': lambda *a: 'init',
    }

    _map_mt940e_base_fields = {
        'name': 'name',
        'date_start': 'date',
        'balance_start': 'balance_start',
        'balance_end': 'balance_end',
        'type': 'format',
    }

    _map_mt940e_line_fields = {
        'date': 'date',
        'reference': 'name',
        'details': 'note',
    }

    def check_iban(self, cr, uid, value):
        iban = value.strip()
        for c in iban:
            if not c.isalnum():
                return False
        iban = iban.lower()
        iban = iban[4:] + iban[:4]
        #letters have to be transformed into numbers (a = 10, b = 11, ...)
        iban2 = ""
        for char in iban:
            if char.isalpha():
                iban2 += str(ord(char)-87)
            else:
                iban2 += char
            #iban is correct if modulo 97 == 1
        try:
            iban2 = int(iban2)
        except ValueError, e:
            return False
        if not int(iban2) % 97 == 1:
            return False
        return True

    def extract_partner_name(self, cr, uid, details):
        return details

    def match_postalcode(self, cr, uid, line, values, context=None):
        regexps = [ '.*(F[ -]{1}[0-9]{5}).*', '.*(L[- ]{1}[0-9]{4}).*', '.*(D[- ]{1}[0-9]{5}).*' ]
        data = values.get('beneficiary', '')
        for exp in regexps:
            m = re.match(exp, data)
            if m:
                group = m.groups(0)[0]
                line['log'].append(_('found postal code %s') % (str(group)))
                pos = data.find(group)
                posr = pos+len(group)
                values['_postcode'] = group
                values['_beneficiary'] = data[:pos]
                values['_city'] = data[posr:]
                try:
                    if not data[pos-1].isspace() and not data[posr].isspace():
                        values['beneficiary'] = '%s %s %s' % (data[:pos], group, data[posr:])
                    elif not data[pos-1].isspace() and data[posr].isspace():
                        values['beneficiary'] = '%s %s%s' % (data[:pos], group, data[posr:])
                    elif data[pos-1].isspace():
                        if posr >= len(data):
                            data_posr = ''
                        else:
                            data_posr = data[posr:]
                        if len(data_posr) and not data_posr[0].isspace():
                            values['beneficiary'] = '%s%s %s' % (data[:pos], group, data_posr)
                except IndexError:
                    # malformated beneficiary content, skip
                    pass
                return
        values['_beneficiary'] = data

    def match_partner(self, cr, uid, line, values, context=None):
        l = line
        v = values
        line['log'].extend([_('Match Partner'),
                            _('=============')])
        if v.get('communication'):
            if self.check_iban(cr, uid, v['communication']):
                line['log'].append(_('found iban code, set type supplier'))
                # iban found, we should be able to dermine partner
                l['type'] = 'supplier'
                accounts = self.pool.get('res.partner.bank').search(cr, uid, [('iban','ilike',v['communication'])], context=context)
                if len(accounts) == 1:
                    a = self.pool.get('res.partner.bank').browse(cr, uid, accounts[0], context=context)
                    l['partner_id'] = a.partner_id.id
                    line['log'].append(_('found partner bank account, set partner'))
                    return
                elif len(accounts) > 1:
                    accounts2 = self.pool.get('res.partner.bank').search(cr, uid, [('id', 'in', accounts),('partner_id.name', 'ilike', self.extract_partner_name(cr, uid, v.get('beneficiary','')))], context=context)
                    if len(accounts2) == 1:
                        a = self.pool.get('res.partner.bank').browse(cr, uid, accounts2[0], context=context)
                        l['partner_id'] = a.partner_id.id
                        line['log'].append(_('found partner bank account from extended beneficiary, set partner'))
                        return
        if v.get('_beneficiary'):
            b = v.get('_beneficiary')
            #rexp = 'REGEXP:*%s*' % (v.get('_beneficiary').replace(' ','*'))
            #partner_ids = self.pool.get('res.partner').search(cr, uid, [('name','ilike',rexp)])
            partner_ids = self.pool.get('res.partner').search(cr, uid, [('name','ilike',b)], context=context)
            if len(partner_ids) == 1:
                l['partner_id'] = partner_ids[0]
                line['log'].append(_('found partner from beneficiary match'))
            #print("PARTNER IDS: %s" % (partner_ids))
            pass
        return

    def match_invoice(self, cr, uid, line, values, context=None):
        rexp = '20[0-9]{2}[/ .-]{1}[0-9]{5}'
        line['log'].extend([_('Match Invoice'),
                            _('=============')])
        for k in ('reference', 'details', 'beneficiary'):
            matches = re.findall(rexp, values.get(k, ''))
            if matches:
                line['log'].append(_('match found with invoice: %s') % (', '.join(matches)))
                total = 0.0
                partner_id = None
                invoices = []

                for match in matches:
                    match = match.replace(' ','/').replace('.','/')
                    invoice_ids = self.pool.get('account.invoice').search(cr, uid, [('number','=',match)], context=context)
                    line['log'].append(_('searching invoice with number = %s, found: %d') % (match, len(invoice_ids)))
                    if len(invoice_ids) == 1:
                        invoice = self.pool.get('account.invoice').browse(cr, uid, invoice_ids[0], context=context)
                        if partner_id is None:
                            partner_id = invoice.partner_id.id
                        elif partner_id != invoice.partner_id.id:
                            # invoices belongs to different partner_id
                            line['log'].append(_('cancelling, invoice belongs to differents partners'))
                            return False
                        mult = {
                            'out_invoice': 1,
                            'out_refund': -1,
                            'in_invoice': -1,
                            'in_refund': 1,
                        }[invoice.type]
                        total += invoice.amount_total * mult
                        invoices.append(invoice)

                if total - 0.00001 < values['amount'] < total + 0.00001:
                    line['log'].append(_('statement line amount match invoices sum'))
                    line['partner_id'] = partner_id
                    line['type'] = {
                        'in_invoice': 'supplier',
                        'out_invoice': 'customer',
                        'in_refund': 'supplier',
                        'out_refund': 'customer',
                    }[invoice.type]
                    line['log'].append(_('set partner from invoice match'))
                    line['log'].append(_('set type from invoice match'))
                    # TODO: mark invoice move lines to reconcile with this line
                    line_ids = []
                    for inv in invoices:
                        if inv.move_id:
                            for move_line in inv.move_id.line_id:
                                if move_line.reconcile_id:
                                    line['log'].append(_('reject move line %d from invoice %s because it\'s already reconciled') % (move_line.id, inv.number))
                                if not move_line.reconcile_id and move_line.account_id.reconcile == True:
                                    line_ids.append(move_line.id)
                    line['move_line_ids'] = [(6, 0, line_ids)]
                else:
                    line['log'].append(_('statement amount (%s) doesn\'t match invoices sum (%s)') % (values['amount'], total))
            else:
                line['log'].append(_('no matching invoice found'))
        return False

    def match_payment_reference(self, cr, uid, line, values, context=None):
        rexp = '.*(20[0-9]{2}[/ .]{1}[0-9]+-[0-9]+).*'
        line['log'].extend([_('Match Payment Reference'),
                            _('=======================')])
        for k in ('reference', 'details', 'beneficiary'):
            m = re.match(rexp, values.get(k, ''))
            if m:
                match = m.groups()[0]
                #print("MATCH PAYMENT REFERENCE: %s" % (match))
                payorder_ref, payline_ref = match.strip().split('-')
                line['log'].append(_('match found with payment order %s, line %s') % (payorder_ref, payline_ref))
                payorder_ids = self.pool.get('payment.order').search(cr, uid, [('reference','=',payorder_ref)], context=context)
                if len(payorder_ids) != 1:
                    line['log'].append(_('error: not exact corresponding payment found'))
                    return False
                payorder_id = payorder_ids[0]

                payline_ids = self.pool.get('payment.line').search(cr, uid, [('name','=',payline_ref),('order_id','=',payorder_id)], context=context)
                if len(payline_ids) != 1:
                    line['log'].append(_('error: not exact corresponding payment line found'))
                    continue
                payline = self.pool.get('payment.line').browse(cr, uid, payline_ids[0], context=context)
                if not line['amount'] == payline.amount_currency * -1.0:
                    line['log'].append(_('error: statement amount does not match payment order line'))
                    continue
                line['partner_id'] = payline.partner_id.id
                line['type'] = 'supplier'
                line['log'].append(_('set partner from payment order'))
                line['log'].append(_('set type from payment order'))
                # TODO: also update reconcile line ids
                if payline.move_line_id:
                    line['move_line_ids'] = [(6, 0, [payline.move_line_id.id])]
                    line['log'].append(_('add matching move line'))
                return True
        return False

    def button_import_file(self, cr, uid, ids, context=None):
        def fail_return(error_msg=''):
            return self.write(cr, uid, [ ids[0] ], {'state': 'import_failed', 'error_msg': error_msg}, context=context)
        if not ids:
            return {}
        k = self.read(cr, uid, ids[0], ['file', 'filename'], context=context)
        if not (k and k.get('file')):
            return {}

        # search for existing statement import for the same file
        existing_st_ids = self.pool.get('account.bank.statement').search(cr, uid, [('mt940e_filename','=',k['filename'])], context=context)
        if existing_st_ids:
            self.write(cr, uid, ids, {'state': 'already_imported'}, context=context)
            return False

        fraw = base64.decodestring(k.get('file'))
        f = StringIO(fraw)
        p = mt940e_parser()
        p.parse(f)

        values =  {}
        for f, key in self._map_mt940e_base_fields.iteritems():
            val = p.data.get(f)
            if val:
                values[key] = val
        # Get Journal
        st_iban = p.data['account_nb'].split('/')[1]
        st_iban = st_iban.strip()
        st_account_ids = self.pool.get('res.partner.bank').search(cr, uid, [('iban','ilike',st_iban)], context=context)
        if not st_account_ids:
            return fail_return('No IBAN found for: %s' % (st_iban))
        st_account = st_account_ids[0]
        st_payment_mode_ids = self.pool.get('payment.mode').search(cr, uid, [('bank_id','=',st_account)], context=context)
        if not st_payment_mode_ids:
            return fail_return('No payment mode found for bank account: %s' % (st_account))
        st_payment_mode = self.pool.get('payment.mode').read(cr, uid, st_payment_mode_ids[0], context=context)
        if not st_payment_mode:
            return fail_return()
        values['journal_id'] = st_payment_mode['journal'][0]

        # Get Period
        period_ids = self.pool.get('account.period').find(cr, uid, p.data['date_start'], context=context)
        if not period_ids:
            return fail_return()
        values['period_id'] = period_ids[0]

        # Check that the statement does not span on multiple periods
        line_periods = set()
        period_proxy = self.pool.get('account.period')
        for v in p.data['lines']:
            v_date = str(v['entry_date'])
            try:
                # NOTE: we do not consider period wihch have 'opening/closing' checked (=> special) !
                pids = period_proxy.search(cr, uid, [('date_start','<=',v_date),('date_stop','>=',v_date),('special','=',False)])
            except osv.except_osv:
                # FIXME: no period found?
                pass
            line_periods.update(pids)
        if len(line_periods) > 1:
            # more than one period, this is not allowed!
            return fail_return('The provided file contains moves on more than one fiscal period, we could not import this')

        # Insert lines
        values['line_ids'] = []
        for v in p.data['lines']:
            l = {
                'date': str(v['date']),
                'name': v.get('reference',''),
                'note': """
Communication: %s
Beneficiary: %s
Beneficiary Details: %s
Details: %s
                """ % (v.get('communication', ''), v.get('beneficiary',''), v.get('beneficiary_details', ''), v.get('details')),
            }
            afactor = v['amount'] >= 0 and 1 or -1
            l['amount'] = v['amount']
            if v['charges']:
                # deduce charges from amount
                l['amount'] -= v['charges'] * afactor
            l['log'] = []

            # try to dermine the partner
            self.match_invoice(cr, uid, l, v, context=context)
            self.match_payment_reference(cr, uid, l, v, context=context)
            self.match_postalcode(cr, uid, l, v, context=context)
            self.match_partner(cr, uid, l, v, context=context)


            if l.get('partner_id'):
                l['log'].append(_('partner previously found, update account and type from partner from'))
                partner = self.pool.get('res.partner').browse(cr, uid, l['partner_id'], context=context)
                if l.get('type','') not in ('supplier','customer'):
                    if l['amount'] < 0:
                        l['type'] = 'supplier'
                    else:
                        l['type'] = 'customer'
                if l['type'] == 'supplier':
                    l['account_id'] = partner.property_account_payable.id
                else:
                    l['account_id'] = partner.property_account_receivable.id

            l['log'] = '\n'.join(l['log'])
            values['line_ids'].append((0, 0, l))
            if v['charges']:
                # TODO: create a new line for the charges part
                acode = self.pool.get('ir.config').get(cr, uid, 'account.multiline.mt940e.charges.account')
                aids = self.pool.get('account.account').search(cr, uid, [('code','=',acode)], context=context)
                l = {
                    'name': 'FRAIS BANCAIRE',
                    'note': 'FRAIS BANCAIRE',
                    'type': 'general',
                    'amount': v['charges'] * -1,
                    'date': str(v['date']),
                    'account_id': aids[0],
                }
                values['line_ids'].append((0, 0, l))
                pass

        # write back values
        values['date'] = str(values['date'])
        values['state'] = 'check_import'

        self.write(cr, uid, [ ids[0] ], values, context=context)
        return False

    def button_create_real_statement(self, cr, uid, ids, context=None):
        if not ids:
            return {}
        wizard_id = ids[0]
        wizard = self.browse(cr, uid, ids[0], context=context)

        st_record = self.browse(cr, uid, wizard_id, context=context)
        st = {
            'name': st_record.name,
            'date': st_record.date,
            'journal_id': st_record.journal_id.id,
            'period_id': st_record.period_id.id,
            'balance_start': st_record.balance_start,
            'balance_end': st_record.balance_end,
            'balance_end_real': st_record.balance_end,
            'company_id': self.pool.get('res.company')._company_default_get(cr, uid, 'account.bank.statement', context=context),
            'mt940e_filename': wizard.filename,
            'line_ids': [],
        }

        statement_currency_id = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id.id
        if st_record.journal_id.currency:
            statement_currency_id = st_record.journal_id.currency.id

        wizard_stline_pool = self.pool.get('account.bank.statement.mt940e.import.wizard.line')
        move_line_obj = self.pool.get('account.move.line')
        voucher_obj = self.pool.get('account.voucher')
        voucher_line_obj = self.pool.get('account.voucher.line')

        lids = wizard_stline_pool.search(cr, uid, [('wizard_id','=',wizard_id)], context=context)
        for seq, stline in enumerate(wizard_stline_pool.read(cr, uid, lids, ['date','name','note','log', 'partner_id','account_id','amount','type','move_line_ids'], context=context)):

            stline['sequence'] = seq
            mvline_ids = stline.pop('move_line_ids', [])
            log_txt = stline.pop('log', '')
            stline['note'] += u'\n%s' % (log_txt)
            if mvline_ids:
                voucher_context = context.copy()
                voucher_context['date'] = stline['date'] # use payment date for currency computation

                voucher_amount = stline['amount']
                voucher_type = stline['amount'] < 0 and 'payment' or 'receipt'
    #
    #            if line.amount_currency:
    #                amount = currency_obj.compute(cr, uid, line.currency_id.id,
    #                    statement.currency.id, line.amount_currency, context=ctx)
    #            elif (line.invoice and line.invoice.currency_id.id <> statement.currency.id):
    #                amount = currency_obj.compute(cr, uid, line.invoice.currency_id.id,
    #                    statement.currency.id, amount, context=ctx)

                voucher_context.update({'move_line_ids': mvline_ids})

                default_voucher_lines = voucher_obj.onchange_partner_id(cr, uid, [],
                                                partner_id=stline['partner_id'] or False,
                                                journal_id=st['journal_id'],
                                                price=abs(voucher_amount),
                                                currency_id=statement_currency_id,
                                                ttype=voucher_type,
                                                date=stline['date'],
                                                context=voucher_context)


                if voucher_amount >= 0:
                    account_id = st_record.journal_id.default_credit_account_id.id
                else:
                    account_id = st_record.journal_id.default_debit_account_id.id

                voucher_data = {
                        'type': voucher_type,
                        'name': stline['name'],
                        'partner_id': stline['partner_id'] or False,
                        'period_id': st['period_id'],
                        'journal_id': st['journal_id'],
                        'account_id': account_id,
                        'company_id': st['company_id'],
                        'currency_id': statement_currency_id,
                        'date': stline['date'],
                        'amount': abs(voucher_amount),
                }
                voucher_id = voucher_obj.create(cr, uid, voucher_data, context=voucher_context)

                for line in default_voucher_lines.get('value',{}).get('line_ids',[]):
                    if line['move_line_id'] in mvline_ids:
                        line['voucher_id'] = voucher_id
                        voucher_line_obj.create(cr, uid, line, context=context)
                stline['voucher_id'] = voucher_id

            st['line_ids'].append((0, 0, stline))

        st_id = self.pool.get('account.bank.statement').create(cr, uid, st, context=context)
        print("ST: %s" % (st_id))
        if st_id:
            return {
                'res_model': 'account.bank.statement',
                'res_id': st_id,
                'view_type': 'form',
                'view_mode': 'form,tree',
                'target': 'new',
            }

        return False

    def button_choose_another_file(self, cr, uid, ids, context=None):
        if not ids:
            return False
        self.write(cr, uid, ids, {'state': 'init', 'file': False, 'filename': False}, context=context)
        return False


account_bank_statement_mt940_import_wizard()

class account_bank_statement_mt940e_import_wizard_line(osv.osv_memory):
    _name = 'account.bank.statement.mt940e.import.wizard.line'

    _columns = {
        'wizard_id': fields.many2one('account.bank.statement.mt940e.import.wizard', 'Wizard', required=True),
        'date': fields.date('Date', required=True),
        'name': fields.char('Name', size=64),
        'note': fields.text('Description'),
        'partner_id': fields.many2one('res.partner', 'Partner'),
        'account_id': fields.many2one('account.account', 'Account'),
        'amount': fields.float('Amount'),
        'type': fields.selection([('general','General'),('supplier','Supplier'),('customer','Customer')], 'Type'),
        'move_line_ids': fields.many2many('account.move.line', 'mt940e_wizard_line_move_line_rel', 'line_id', 'move_line_id', 'Reconciles'),
        'log': fields.text('Log'),
    }

    _defaults = {
        'type': lambda *a: 'general',
    }

    def onchange_partner_id(self, cr, uid, ids, partner_id, type, context=None):
        ocv = { 'value': {}}
        if not partner_id or not type:
            return ocv
        partner = self.pool.get('res.partner').browse(cr, uid, partner_id, context=context)
        if type == 'supplier' and partner.property_account_payable.id:
            ocv['value']['account_id'] = partner.property_account_payable.id
        if type == 'customer' and partner.property_account_receivable.id:
            ocv['value']['account_id'] = partner.property_account_receivable.id
        return ocv
account_bank_statement_mt940e_import_wizard_line()
