# -*- coding: utf-8 -*-
##############################################################################
#
#    account_payment_import_multiline module for OpenERP, multiline bank statement import
#    Copyright (C) 2011 Thamini S.à.R.L (<http://www.thamini.com) Xavier ALT
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
{
    'name': 'account_payment_import_statement',
    'version': '0.1',
    'author': 'Thamini S.à.R.L',
    'website': 'http://www.thamini.com',
    'description': """
        Allow importation of electronic bank statement (format MT940e)
        exported from multiline

        A wizard allow you to easily import thoses electronic bank statements.
    """,
    'depends': [
        'account_payment',
    ],
    'init_xml': [
    ],
    'demo_xml': [
    ],
    'update_xml': [
        'account_bank_statement_view.xml',
        'account_bank_statement_import_view.xml',
    ],
    'active': False,
    'installable': True,
}
