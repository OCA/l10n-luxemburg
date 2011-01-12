# -*- coding: utf-8 -*-

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

account_bank_statement_line_i()


