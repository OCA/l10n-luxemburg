# -*- coding: utf-8 -*-

from osv import osv
from osv import fields


class account_bank_statement_i(osv.osv):
    _inherit = 'account.bank.statement'
    _columns = {
        'imported_filename': fields.char('Imported Filename', size=255, readonly=True),
    }
account_bank_statement_i()
