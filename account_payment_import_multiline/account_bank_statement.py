# -*- coding: utf-8 -*-

import time
from osv import osv
from osv import fields

class account_bank_statement_i(osv.osv):
    _inherit = 'account.bank.statement'
    _columns = {
        'mt940e_filename': fields.char('MT940E Filename', size=255, readonly=True),
    }
account_bank_statement_i()

class account_bank_statement_line_i(osv.osv):
    _inherit = 'account.bank.statement.line'
    _order = 'sequence ASC'
    _columns = {
    }

    def _get_default_date(self, cr, uid, context=None):
        print("default_date context: %s" % (str(context)))
        cdate = context.get('date', '')
        if cdate:
            return cdate
        return time.strftime('%Y-%m-%d')

    _defaults = {
        'date': _get_default_date,
    }

account_bank_statement_line_i()


