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

import base64
from StringIO import StringIO
from osv import osv
from osv import fields
import cPickle as pickle
from tools.misc import DEFAULT_SERVER_DATE_FORMAT as D_FORMAT

#from mt940e_parser import mt940e_parser
from .parser.ing_lux_pdf import INGBankStatementParser


class StatementImportError(Exception):
    pass

statement_parsers = {
    'ing_lux_pdf': INGBankStatementParser,
}


class account_bank_statement_import_wizard_line(osv.osv_memory):
    _name = 'account.bank.statement.import.wizard.line'
account_bank_statement_import_wizard_line()


class account_bank_statement_import_wizard(osv.osv_memory):
    _name = 'account.bank.statement.import.wizard'

    _STATES = [
        ('init', 'Choose File'),
        ('check_import', 'Check Imported Data'),
        ('already_imported', 'Already Imported'),
        ('create_statement', 'Create Statement'),
        ('import_failed', 'Import Failed'),
        ('done', 'Done'),
    ]

    _types_selection = [
        ('ing_lux_pdf', 'ING Luxembourg PDF Statement'),
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
        'type': fields.selection(_types_selection, 'Type', required=True),

        # step 2
        'format': fields.char('Format', size=32, readonly=True),
        'name': fields.char('Name', size=64),
        'date': fields.date('Date'),
        'period_id': fields.many2one('account.period', 'Period'),
        'journal_id': fields.many2one('account.journal', 'Journal'),
        #        'currency_id': fields.related('journal_id', 'currency', type='many2one', relation='res.currency', string='Currency', readonly=True),
        'currency_id': fields.many2one('res.currency', 'Currency', readonly=True),
        'balance_start': fields.float('Balance Start'),
        'balance_end': fields.float('Balance End'),
        'balance_end_computed': fields.function(_compute_balance_end, type='float', string='Computed Balance End', readonly=True, method=True),
        'line_ids': fields.one2many('account.bank.statement.import.wizard.line', 'wizard_id', 'Lines'),
        'error_msg': fields.text('Error Message', size=255),
        'state': fields.selection(_STATES, 'State', readonly=True),

        # internal
        'internal_state': fields.binary('Internal State'),
    }

    _defaults = {
        'state': 'init',
        'type': 'ing_lux_pdf',
    }

    def create(self, cr, uid, vals, context=None):
        wizard_id = super(account_bank_statement_import_wizard, self).create(
            cr, uid, vals, context=context)
        self.save_state(cr, uid, wizard_id, None, context=context)
        return wizard_id

    def save_state(self, cr, uid, id, state_value, context=None):
        if state_value is None:
            state_value = {
                'statements': [],
                'current': None,
                'new_statement_ids': [],
            }
        s = pickle.dumps(state_value, pickle.HIGHEST_PROTOCOL)
        self.write(cr, uid, [id], {'internal_state': s}, context=context)
        return True

    def load_state(self, cr, uid, id, context=None):
        s = self.browse(cr, uid, id, context=context).internal_state
        return pickle.loads(s)

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
        # letters have to be transformed into numbers (a = 10, b = 11, ...)
        iban2 = ""
        for char in iban:
            if char.isalpha():
                iban2 += str(ord(char) - 87)
            else:
                iban2 += char
            # iban is correct if modulo 97 == 1
        try:
            iban2 = int(iban2)
        except ValueError, e:
            return False
        if not int(iban2) % 97 == 1:
            return False
        return True

    def extract_partner_name(self, cr, uid, details):
        return details

#    def match_postalcode(self, cr, uid, line, values, context=None):
#        regexps = [ '.*(F[ -]{1}[0-9]{5}).*', '.*(L[- ]{1}[0-9]{4}).*', '.*(D[- ]{1}[0-9]{5}).*' ]
#        data = values.get('beneficiary', '')
#        for exp in regexps:
#            m = re.match(exp, data)
#            if m:
#                group = m.groups(0)[0]
#                line['log'].append(_('found postal code %s') % (str(group)))
#                pos = data.find(group)
#                posr = pos+len(group)
#                values['_postcode'] = group
#                values['_beneficiary'] = data[:pos]
#                values['_city'] = data[posr:]
#                try:
#                    if not data[pos-1].isspace() and not data[posr].isspace():
#                        values['beneficiary'] = '%s %s %s' % (data[:pos], group, data[posr:])
#                    elif not data[pos-1].isspace() and data[posr].isspace():
#                        values['beneficiary'] = '%s %s%s' % (data[:pos], group, data[posr:])
#                    elif data[pos-1].isspace():
#                        if posr >= len(data):
#                            data_posr = ''
#                        else:
#                            data_posr = data[posr:]
#                        if len(data_posr) and not data_posr[0].isspace():
#                            values['beneficiary'] = '%s%s %s' % (data[:pos], group, data_posr)
#                except IndexError:
# malformated beneficiary content, skip
#                    pass
#                return
#        values['_beneficiary'] = data
#
#    def match_partner(self, cr, uid, line, values, context=None):
#        l = line
#        v = values
#        line['log'].extend([_('Match Partner'),
#                            _('=============')])
#        if v.get('communication'):
#            if self.check_iban(cr, uid, v['communication']):
#                line['log'].append(_('found iban code, set type supplier'))
# iban found, we should be able to dermine partner
#                l['type'] = 'supplier'
#                accounts = self.pool.get('res.partner.bank').search(cr, uid, [('iban','ilike',v['communication'])], context=context)
#                if len(accounts) == 1:
#                    a = self.pool.get('res.partner.bank').browse(cr, uid, accounts[0], context=context)
#                    l['partner_id'] = a.partner_id.id
#                    line['log'].append(_('found partner bank account, set partner'))
#                    return
#                elif len(accounts) > 1:
#                    accounts2 = self.pool.get('res.partner.bank').search(cr, uid, [('id', 'in', accounts),('partner_id.name', 'ilike', self.extract_partner_name(cr, uid, v.get('beneficiary','')))], context=context)
#                    if len(accounts2) == 1:
#                        a = self.pool.get('res.partner.bank').browse(cr, uid, accounts2[0], context=context)
#                        l['partner_id'] = a.partner_id.id
#                        line['log'].append(_('found partner bank account from extended beneficiary, set partner'))
#                        return
#        if v.get('_beneficiary'):
#            b = v.get('_beneficiary')
# rexp = 'REGEXP:*%s*' % (v.get('_beneficiary').replace(' ','*'))
# partner_ids = self.pool.get('res.partner').search(cr, uid, [('name','ilike',rexp)])
#            partner_ids = self.pool.get('res.partner').search(cr, uid, [('name','ilike',b)], context=context)
#            if len(partner_ids) == 1:
#                l['partner_id'] = partner_ids[0]
#                line['log'].append(_('found partner from beneficiary match'))
# print("PARTNER IDS: %s" % (partner_ids))
#            pass
#        return
#
#    def match_invoice(self, cr, uid, line, values, context=None):
#        rexp = '20[0-9]{2}[/ .-]{1}[0-9]{5}'
#        line['log'].extend([_('Match Invoice'),
#                            _('=============')])
#        for k in ('reference', 'details', 'beneficiary'):
#            matches = re.findall(rexp, values.get(k, ''))
#            if matches:
#                line['log'].append(_('match found with invoice: %s') % (', '.join(matches)))
#                total = 0.0
#                partner_id = None
#                invoices = []
#
#                for match in matches:
#                    match = match.replace(' ','/').replace('.','/')
#                    invoice_ids = self.pool.get('account.invoice').search(cr, uid, [('number','=',match)], context=context)
#                    line['log'].append(_('searching invoice with number = %s, found: %d') % (match, len(invoice_ids)))
#                    if len(invoice_ids) == 1:
#                        invoice = self.pool.get('account.invoice').browse(cr, uid, invoice_ids[0], context=context)
#                        if partner_id is None:
#                            partner_id = invoice.partner_id.id
#                        elif partner_id != invoice.partner_id.id:
# invoices belongs to different partner_id
#                            line['log'].append(_('cancelling, invoice belongs to differents partners'))
#                            return False
#                        mult = {
#                            'out_invoice': 1,
#                            'out_refund': -1,
#                            'in_invoice': -1,
#                            'in_refund': 1,
#                        }[invoice.type]
#                        total += invoice.amount_total * mult
#                        invoices.append(invoice)
#
#                if total - 0.00001 < values['amount'] < total + 0.00001:
#                    line['log'].append(_('statement line amount match invoices sum'))
#                    line['partner_id'] = partner_id
#                    line['type'] = {
#                        'in_invoice': 'supplier',
#                        'out_invoice': 'customer',
#                        'in_refund': 'supplier',
#                        'out_refund': 'customer',
#                    }[invoice.type]
#                    line['log'].append(_('set partner from invoice match'))
#                    line['log'].append(_('set type from invoice match'))
# TODO: mark invoice move lines to reconcile with this line
#                    line_ids = []
#                    for inv in invoices:
#                        if inv.move_id:
#                            for move_line in inv.move_id.line_id:
#                                if move_line.reconcile_id:
#                                    line['log'].append(_('reject move line %d from invoice %s because it\'s already reconciled') % (move_line.id, inv.number))
#                                if not move_line.reconcile_id and move_line.account_id.reconcile == True:
#                                    line_ids.append(move_line.id)
#                    line['move_line_ids'] = [(6, 0, line_ids)]
#                else:
#                    line['log'].append(_('statement amount (%s) doesn\'t match invoices sum (%s)') % (values['amount'], total))
#            else:
#                line['log'].append(_('no matching invoice found'))
#        return False
#
#    def match_payment_reference(self, cr, uid, line, values, context=None):
#        rexp = '.*(20[0-9]{2}[/ .]{1}[0-9]+-[0-9]+).*'
#        line['log'].extend([_('Match Payment Reference'),
#                            _('=======================')])
#        for k in ('reference', 'details', 'beneficiary'):
#            m = re.match(rexp, values.get(k, ''))
#            if m:
#                match = m.groups()[0]
# print("MATCH PAYMENT REFERENCE: %s" % (match))
#                payorder_ref, payline_ref = match.strip().split('-')
#                line['log'].append(_('match found with payment order %s, line %s') % (payorder_ref, payline_ref))
#                payorder_ids = self.pool.get('payment.order').search(cr, uid, [('reference','=',payorder_ref)], context=context)
#                if len(payorder_ids) != 1:
#                    line['log'].append(_('error: not exact corresponding payment found'))
#                    return False
#                payorder_id = payorder_ids[0]
#
#                payline_ids = self.pool.get('payment.line').search(cr, uid, [('name','=',payline_ref),('order_id','=',payorder_id)], context=context)
#                if len(payline_ids) != 1:
#                    line['log'].append(_('error: not exact corresponding payment line found'))
#                    continue
#                payline = self.pool.get('payment.line').browse(cr, uid, payline_ids[0], context=context)
#                if not line['amount'] == payline.amount_currency * -1.0:
#                    line['log'].append(_('error: statement amount does not match payment order line'))
#                    continue
#                line['partner_id'] = payline.partner_id.id
#                line['type'] = 'supplier'
#                line['log'].append(_('set partner from payment order'))
#                line['log'].append(_('set type from payment order'))
# TODO: also update reconcile line ids
#                if payline.move_line_id:
#                    line['move_line_ids'] = [(6, 0, [payline.move_line_id.id])]
#                    line['log'].append(_('add matching move line'))
#                return True
#        return False

    def _statement_already_exist(self, cr, uid, wizard_record, context=None):
        statement_obj = self.pool.get('account.bank.statement')
        if len(statement_obj.search(cr, uid, [('imported_filename', '=', wizard_record.filename)], context=context)):
            return True
        return False

    def button_import_file(self, cr, uid, ids, context=None):
        def fail_return(error_msg=''):
            return self.write(cr, uid, [ids[0]], {'state': 'import_failed', 'error_msg': error_msg}, context=context)

        if not ids:
            return {}
        wizard_id = ids[0]
        wizard = self.browse(cr, uid, wizard_id, context=context)
        if not wizard.file:
            return {}

        wizard_state = self.load_state(cr, uid, wizard_id, context=context)

        if self._statement_already_exist(cr, uid, wizard, context):
            self.write(
                cr, uid, ids, {'state': 'already_imported'}, context=context)
            return False

        print("wizard_state: %s" % (wizard_state))


#        k = self.read(cr, uid, ids[0], ['type', 'file', 'filename'], context=context)
#        if not (k and k.get('file')):
#            return {}

# search for existing statement import for the same file
#        existing_st_ids = self.pool.get('account.bank.statement').search(cr, uid, [('imported_filename','=',k['filename'])], context=context)
#        if existing_st_ids:

        wizard_rawfile = base64.decodestring(wizard.file)
        f = StringIO(wizard_rawfile)

        # parse the file
        statement_parser = statement_parsers[wizard.type]()
        print("statement parser: %s" % (statement_parser))
        sts = statement_parser.parse(f)

        import pprint
        pprint.pprint(sts)

        if not sts:
            # not statements, exist now
            # TODO: improve this!
            return {}

        wizard_state.update({
            'statements': sts,
            'current': 0,
        })
        self.save_state(cr, uid, wizard_id, wizard_state, context=context)

        self._wizard_fill_next_statement(cr, uid, wizard_id, context=context)

        print("IMPORT DONE")
        return False

    def _wizard_set_error(self, cr, uid, ids, error_msg, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        return self.write(cr, uid, ids, {'state': 'import_failed', 'error_msg': error_msg}, context=context)

    def _wizard_fill_next_statement(self, cr, uid, wizard_id, context=None):
        wizard_state = self.load_state(cr, uid, wizard_id, context=context)
        current_statement = wizard_state['current']
        if wizard_state['current'] >= len(wizard_state['statements']):
            # all statements done
            default_action = {
                'type': 'ir.actions.act_window',
                'res_model': 'account.bank.statement',
                'view_type': 'form',
                'view_mode': 'form,tree',
            }
            new_statement_ids = wizard_state['new_statement_ids']
            new_statement_count = len(new_statement_ids)
            if new_statement_count == 0:
                return {}  # simply close the wizard
            elif new_statement_count == 1:
                action = default_action.copy()
                action['res_id'] = new_statement_ids[0]
                return action
            else:
                action = default_action.copy()
                action['domain'] = str([('id', 'in', new_statement_ids)])
            return {}  # fallback: issue a close

        try:
            self._wizard_fill_from_statement(
                cr, uid, wizard_id, wizard_state['statements'][current_statement], context=context)
        except StatementImportError, e:
            self._wizard_set_error(
                cr, uid, wizard_id, e.args[0], context=context)
            return False

        wizard_state['current'] += current_statement + 1
        self.save_state(cr, uid, wizard_id, wizard_state, context=context)
        return True

    def _get_journal_from_statement(self, cr, uid, statement, context=None):
        account_type = statement['account_type']
        account_number = statement['account']

        if account_type == 'standard':
            account_field = 'acc_number'
        elif account_type == 'iban':
            account_field = 'iban'
        else:
            raise Exception(
                'Unknown bank account type of type = %s' % (account_type))

        partner_bank_obj = self.pool.get('res.partner.bank')
        payment_mode_obj = self.pool.get('payment.mode')

        partner_bank_domain = ['|', (account_field, '=', account_number.lower(
        )), (account_field, '=', account_number.upper())]
        partner_bank_ids = partner_bank_obj.search(
            cr, uid, partner_bank_domain, context=context)
        if not partner_bank_ids:
            raise StatementImportError(
                'No IBAN found for: %s [type: %s]' % (account_number, account_type))

        payment_mode_ids = payment_mode_obj.search(
            cr, uid, [('bank_id', '=', partner_bank_ids[0])], context=context)
        if not payment_mode_ids:
            raise StatementImportError(
                'No Payment Mode found for: %s [type: %s]' % (account_number, account_type))
        payment_mode = payment_mode_obj.browse(
            cr, uid, payment_mode_ids[0], context=context)
        return payment_mode.journal.id

#        st_iban = p.data['account_nb'].split('/')[1]
#        st_iban = st_iban.strip()
#        st_account_ids = self.pool.get('res.partner.bank').search(cr, uid, [('iban','ilike',st_iban)], context=context)
#        if not st_account_ids:
#            return fail_return('No IBAN found for: %s' % (st_iban))
#        st_account = st_account_ids[0]
#        st_payment_mode_ids = self.pool.get('payment.mode').search(cr, uid, [('bank_id','=',st_account)], context=context)
#        if not st_payment_mode_ids:
#            return fail_return('No payment mode found for bank account: %s' % (st_account))
#        st_payment_mode = self.pool.get('payment.mode').read(cr, uid, st_payment_mode_ids[0], context=context)
#        if not st_payment_mode:
#            return fail_return()
#        values['journal_id'] = st_payment_mode['journal'][0]

    def _get_currency_from_statement(self, cr, uid, statement, context=None):
        statement_currency = statement['currency']
        currency_obj = self.pool.get('res.currency')
        currency_ids = currency_obj.search(cr, uid, [
                                           '|', ('code', '=', statement_currency), ('name', '=', statement_currency)], context=context)
        if not currency_ids:
            raise StatementImportError(
                'No Currency found for currency %s' % (statement_currency))
        return currency_ids[0]

    def _get_period_from_statement(self, cr, uid, statement, context=None):
        start = statement['period_start'].strftime(D_FORMAT)
        end = statement['period_end'].strftime(D_FORMAT)

        period_obj = self.pool.get('account.period')
        period_ids = period_obj.search(cr, uid, [(
            'date_start', '<=', start), ('date_stop', '>=', end), ('special', '=', False)], context=context)
        if not period_ids:
            raise StatementImportError(
                'No period found between %s and %s' % (start, end))
        # FIXME: We do not check if we get multiple periods (span multiple periodd and/or fiscal years)
        #        Currently we have a ``hack`` in the parsers to split per month
        return period_ids[0]

    def _wizard_fill_from_statement(self, cr, uid, wizard_id, statement, context=None):
        pass
        #p = mt940e_parser()
        # p.parse(f)
        wizard = self.browse(cr, uid, wizard_id, context=context)
        values = {}
#        for f, key in self._map_mt940e_base_fields.iteritems():
#            val = p.data.get(f)
#            if val:
#                values[key] = val

        # Get Journal
        values.update({
            'name': statement['name'],
            'date': statement['date'].strftime(D_FORMAT),
            'balance_start': statement['amount_start'],
            'balance_end': statement['amount_end'],
            'currency_id': self._get_currency_from_statement(cr, uid, statement, context=context),
            'journal_id': self._get_journal_from_statement(cr, uid, statement, context=context),
            'period_id': self._get_period_from_statement(cr, uid, statement, context=context),
        })

# Check that the statement does not span on multiple periods
#        line_periods = set()
#        period_proxy = self.pool.get('account.period')
#        for v in p.data['lines']:
#            v_date = str(v['entry_date'])
#            try:
# NOTE: we do not consider period wihch have 'opening/closing' checked (=> special) !
#                pids = period_proxy.search(cr, uid, [('date_start','<=',v_date),('date_stop','>=',v_date),('special','=',False)])
#            except osv.except_osv:
# FIXME: no period found?
#                pass
#            line_periods.update(pids)
#        if len(line_periods) > 1:
# more than one period, this is not allowed!
# return fail_return('The provided file contains moves on more than one
# fiscal period, we could not import this')

        values['line_ids'] = []
        # remove all existing lines
        for line in wizard.line_ids:
            values['line_ids'].append((2, line.id))

        # Insert lines
        for line in statement['lines']:
            line_data = {
                'date': line['maturity_date'].strftime(D_FORMAT),
                'ref': line['reference'],
                'name': line['name'],
                'amount': line['amount'],
                'note': line['note'],
                'log': [],  # for internal logging mecanism
            }

#        for v in p.data['lines']:
#            l = {
#                'date': str(v['date']),
#                'name': v.get('reference',''),
#                'note': """
# Communication: %s
# Beneficiary: %s
# Beneficiary Details: %s
# Details: %s
#                """ % (v.get('communication', ''), v.get('beneficiary',''), v.get('beneficiary_details', ''), v.get('details')),
#            }
#            afactor = v['amount'] >= 0 and 1 or -1
#            l['amount'] = v['amount']
#            if v['charges']:
# deduce charges from amount
#                l['amount'] -= v['charges'] * afactor
#            l['log'] = []
#
# try to dermine the partner
#            self.match_invoice(cr, uid, l, v, context=context)
#            self.match_payment_reference(cr, uid, l, v, context=context)
#            self.match_postalcode(cr, uid, l, v, context=context)
#            self.match_partner(cr, uid, l, v, context=context)
#
#
#            if l.get('partner_id'):
#                l['log'].append(_('partner previously found, update account and type from partner from'))
#                partner = self.pool.get('res.partner').browse(cr, uid, l['partner_id'], context=context)
#                if l.get('type','') not in ('supplier','customer'):
#                    if l['amount'] < 0:
#                        l['type'] = 'supplier'
#                    else:
#                        l['type'] = 'customer'
#                if l['type'] == 'supplier':
#                    l['account_id'] = partner.property_account_payable.id
#                else:
#                    l['account_id'] = partner.property_account_receivable.id
#
            line_data['log'] = '\n'.join(line_data['log'])
            values['line_ids'].append((0, 0, line_data))
#            if v['charges']:
# TODO: create a new line for the charges part
#                acode = self.pool.get('ir.config').get(cr, uid, 'account.multiline.mt940e.charges.account')
#                aids = self.pool.get('account.account').search(cr, uid, [('code','=',acode)], context=context)
#                l = {
#                    'name': 'FRAIS BANCAIRE',
#                    'note': 'FRAIS BANCAIRE',
#                    'type': 'general',
#                    'amount': v['charges'] * -1,
#                    'date': str(v['date']),
#                    'account_id': aids[0],
#                }
#                values['line_ids'].append((0, 0, l))
#                pass

        # write back values
#        values['date'] = str(values['date'])
        values['state'] = 'check_import'

        self.write(cr, uid, [wizard_id], values, context=context)
        return True

    def button_create_real_statement(self, cr, uid, ids, context=None):
        if not ids:
            return {}
        wizard_id = ids[0]
        wizard = self.browse(cr, uid, wizard_id, context=context)

        st_record = self.browse(cr, uid, wizard_id, context=context)
        st = {
            'name': wizard.name,
            'date': wizard.date,
            'journal_id': wizard.journal_id.id,
            'currency_id': wizard.currency_id.id,
            'period_id': wizard.period_id.id,
            'balance_start': wizard.balance_start,
            'balance_end': wizard.balance_end,
            'balance_end_real': wizard.balance_end,
            'company_id': self.pool.get('res.company')._company_default_get(cr, uid, 'account.bank.statement', context=context),
            'imported_filename': wizard.filename,
            'line_ids': [],
        }

        wizard_stline_pool = self.pool.get(
            'account.bank.statement.import.wizard.line')
        voucher_obj = self.pool.get('account.voucher')
        voucher_line_obj = self.pool.get('account.voucher.line')

        lids = wizard_stline_pool.search(
            cr, uid, [('wizard_id', '=', wizard_id)], context=context)
        for seq, line in enumerate(wizard.line_ids):
            line_data = {
                'sequence': seq,
                'date': line.date,
                'name': line.name,
                'ref': line.ref,
                'note': line.note,
                'partner_id': line.partner_id.id,
                'type': line.type,
                'account_id': line.account_id.id,
                'amount': line.amount,
            }
            log_txt = line.log
            if log_txt:
                line_data['note'] += u'\n%s' % (log_txt,)

            if line.move_line_ids:
                mvline_ids = [l.id for l in line.move_line_ids]
                voucher_context = context.copy()
                # use payment date for currency computation
                voucher_context['date'] = line_data['date']

                voucher_amount = line.amount
                voucher_type = line.amount < 0 and 'payment' or 'receipt'
    #
    #            if line.amount_currency:
    #                amount = currency_obj.compute(cr, uid, line.currency_id.id,
    #                    statement.currency.id, line.amount_currency, context=ctx)
    #            elif (line.invoice and line.invoice.currency_id.id <> statement.currency.id):
    #                amount = currency_obj.compute(cr, uid, line.invoice.currency_id.id,
    #                    statement.currency.id, amount, context=ctx)

                voucher_context.update({'move_line_ids': mvline_ids})

                default_voucher_lines = voucher_obj.onchange_partner_id(cr, uid, [],
                                                                        partner_id=line.partner_id.id,
                                                                        journal_id=wizard.journal_id.id,
                                                                        price=abs(
                                                                            voucher_amount),
                                                                        currency_id=wizard.currency_id.id,
                                                                        ttype=voucher_type,
                                                                        date=line_data[
                                                                            'date'],
                                                                        context=voucher_context)

                if voucher_amount >= 0:
                    account_id = wizard.journal_id.default_credit_account_id.id
                else:
                    account_id = wizard.journal_id.default_debit_account_id.id

                voucher_data = {
                    'type': voucher_type,
                    'name': line.name,
                    'partner_id': line.partner_id.id,
                    'period_id': wizard.period_id.id,
                    'journal_id': wizard.journal_id.id,
                    'account_id': account_id,
                    'company_id': st['company_id'],
                    'currency_id': wizard.currency_id.id,
                    'date': line.date,
                    'amount': abs(voucher_amount),
                }
                voucher_id = voucher_obj.create(
                    cr, uid, voucher_data, context=voucher_context)

                for line in default_voucher_lines.get('value', {}).get('line_ids', []):
                    if line['move_line_id'] in mvline_ids:
                        line['voucher_id'] = voucher_id
                        voucher_line_obj.create(cr, uid, line, context=context)
                line_data['voucher_id'] = voucher_id


#        for seq, stline in enumerate(wizard_stline_pool.read(cr, uid, lids, ['date','name','note','log', 'partner_id','account_id','amount','type','move_line_ids'], context=context)):
#
#            stline['sequence'] = seq
#            mvline_ids = stline.pop('move_line_ids', [])
            st['line_ids'].append((0, 0, line_data))

        st_id = self.pool.get('account.bank.statement').create(
            cr, uid, st, context=context)
        print("ST: %s" % (st_id))
        if st_id:
            wizard_state = self.load_state(cr, uid, wizard_id, context=context)
            wizard_state['new_statement_ids'].append(st_id)
            self.save_state(cr, uid, wizard_id, wizard_state, context=context)
        return self._wizard_fill_next_statement(cr, uid, wizard_id, context=context)
        return False

    def button_choose_another_file(self, cr, uid, ids, context=None):
        if not ids:
            return False
        self.write(cr, uid, ids, {
                   'state': 'init', 'file': False, 'filename': False}, context=context)
        return False


account_bank_statement_import_wizard()


class account_bank_statement_import_wizard_line(osv.osv_memory):
    _name = 'account.bank.statement.import.wizard.line'

    _columns = {
        'wizard_id': fields.many2one('account.bank.statement.import.wizard', 'Wizard', required=True),
        'date': fields.date('Date', required=True),
        'ref': fields.char('Reference', size=32),
        'name': fields.char('Name', size=64),
        'note': fields.text('Description'),
        'partner_id': fields.many2one('res.partner', 'Partner'),
        'account_id': fields.many2one('account.account', 'Account'),
        'amount': fields.float('Amount'),
        'type': fields.selection([('general', 'General'), ('supplier', 'Supplier'), ('customer', 'Customer')], 'Type'),
        'move_line_ids': fields.many2many('account.move.line', 'account_bank_statement_import_move_line_rel', 'import_line_id', 'move_line_id', 'Reconcile'),
        'log': fields.text('Log'),
    }

    _defaults = {
        'type': lambda *a: 'general',
    }

    def onchange_partner_id(self, cr, uid, ids, partner_id, type, amount, context=None):
        ocv = {'value': {}}
        if not partner_id or not type:
            return ocv
        partner = self.pool.get('res.partner').browse(
            cr, uid, partner_id, context=context)
        if type == 'general':
            if all([partner.customer, partner.supplier]):
                type = amount > 0.0 and 'customer' or 'supplier'
            else:
                type = partner.customer and 'customer' or 'supplier'
            ocv['value']['type'] = type
        if type == 'supplier' and partner.property_account_payable.id:
            ocv['value']['account_id'] = partner.property_account_payable.id
        if type == 'customer' and partner.property_account_receivable.id:
            ocv['value']['account_id'] = partner.property_account_receivable.id
        return ocv

account_bank_statement_import_wizard_line()
