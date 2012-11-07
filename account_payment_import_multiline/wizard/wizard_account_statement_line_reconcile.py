# -*- coding: utf-8 -*-
# Copyright 2012 Thamini S.à.R.L    This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from osv import osv
from osv import fields

class account_voucher(osv.osv):
    _inherit = 'account.voucher'

    def name_get(self, cr, uid, ids, context=None):
        if not ids:
            return []
        if context is None: context = {}
        def _sum_moveline_ids(cr, uid, move_line_ids, context=None):
            debit = credit = 0.0
            for line in self.pool.get('account.voucher.line').browse(cr, uid, move_line_ids, context=context):
                move_line = line.move_line_id
                if move_line.debit:
                    debit += move_line.debit
                elif move_line.credit:
                    credit += move_line.credit
            return abs(credit - debit)
        return [(r['id'], (str("%.2f (%.2f)" % (r['amount'], _sum_moveline_ids(cr, uid, r['line_ids'], context=context)) or ''))) \
                                for r in self.read(cr, uid, ids, ['amount', 'line_ids'], context, load='_classic_write')]

account_voucher()

class wizard_account_bank_statement_line_reconcile(osv.osv_memory):
    _name = 'account.bank.statement.line.reconcile.wizard'
    _columns = {
        'state': fields.selection([('choose_lines','Choose Lines'),('voucher_exist','Voucher Exist')], 'State', required=True),
        'statement_line_id': fields.many2one('account.bank.statement.line', 'Statement Line', required=True),
        'partner_id': fields.many2one('res.partner', 'Partner'),
        'move_line_ids': fields.many2many('account.move.line', 'wizard_id', 'line_id', 'Move Lines'),
    }

    def _default_get_state(self, cr, uid, context=None):
        if context is None:
            context = {}
        statement_line_id = context.get('active_id')
        statement_line_obj = self.pool.get('account.bank.statement.line')
        line = statement_line_obj.browse(cr, uid, statement_line_id, context=context)
        if line.voucher_id and not context.get('force_continue'):
            return 'voucher_exist'
        return 'choose_lines'

    def _default_get_statement_line_id(self, cr, uid, context=None):
        if context is None:
            context = {}
        return context.get('active_id',False)

    def _default_get_partner_id(self, cr, uid, context=None):
        if context is None:
            context = {}
        return context.get('partner_id',False)

    _defaults = {
        'state': _default_get_state,
        'statement_line_id': _default_get_statement_line_id,
        'partner_id': _default_get_partner_id,
    }

    def populate_continue(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state': 'choose_lines'}, context=context)

        (act_model, act_id) = self.pool.get('ir.model.data').get_object_reference(cr, uid,
                                                                'account_payment_import_multiline',
                                                                'action_account_bank_statement_line_reconcile_wizard')
        action = self.pool.get(act_model).read(cr, uid, act_id, [], context=context)
        action['context'] = {'force_continue': 1}
        return action

    def populate_statement(self, cr, uid, ids, context=None):
        if not ids:
            return {}
        voucher_obj = self.pool.get('account.voucher')
        voucher_line_obj = self.pool.get('account.voucher.line')

        wizard = self.browse(cr, uid, ids[0], context=context)
        line = wizard.statement_line_id
        statement = line.statement_id

        statement_currency_id = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id.id
        if statement.journal_id.currency:
            statement_currency_id = statement.journal_id.currency.id

        voucher_context = context.copy()
        voucher_context['date'] = line.date # use payment date for currency computation
        voucher_amount = line.amount
        voucher_type = line.amount < 0 and 'payment' or 'receipt'

    # TODO: ... implement this for currency!
    #            if line.amount_currency:
    #                amount = currency_obj.compute(cr, uid, line.currency_id.id,
    #                    statement.currency.id, line.amount_currency, context=ctx)
    #            elif (line.invoice and line.invoice.currency_id.id <> statement.currency.id):
    #                amount = currency_obj.compute(cr, uid, line.invoice.currency_id.id,
    #                    statement.currency.id, amount, context=ctx)

        mvline_ids = [ x.id for x in wizard.move_line_ids ]
        voucher_context.update({'move_line_ids': mvline_ids})

        default_voucher_lines = voucher_obj.onchange_partner_id(cr, uid, [],
                                        partner_id=line.partner_id.id or False,
                                        journal_id=statement.journal_id.id,
                                        price=abs(voucher_amount),
                                        currency_id=statement_currency_id,
                                        ttype=voucher_type,
                                        date=line.date,
                                        context=voucher_context)

        if line.amount >= 0:
            account_id = statement.journal_id.default_credit_account_id.id
        else:
            account_id = statement.journal_id.default_debit_account_id.id

        voucher_data = {
                'type': voucher_type,
                'name': line.name,
                'pre_line': True,
                'partner_id': line.partner_id.id or False,
                'period_id': statement.period_id.id,
                'journal_id': statement.journal_id.id,
                'account_id': account_id,
                'company_id': statement.company_id.id,
                'currency_id': statement_currency_id,
                'date': line.date,
                'amount': abs(voucher_amount),
        }
        voucher_id = voucher_obj.create(cr, uid, voucher_data, context=voucher_context)

        for voucher_line in default_voucher_lines.get('value',{}).get('line_ids',[]):
            if voucher_line['move_line_id'] in mvline_ids:
                voucher_line['voucher_id'] = voucher_id
                voucher_line_obj.create(cr, uid, voucher_line, context=context)

        self.pool.get('account.bank.statement.line').write(cr, uid, [line.id], {'voucher_id': voucher_id})
        return {}

wizard_account_bank_statement_line_reconcile()
