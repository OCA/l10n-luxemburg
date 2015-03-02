# -*- coding: utf-8 -*-
##############################################################################
#
#    WARNING: This program as such is intended to be used by professional
#    programmers who take the whole responsibility of assessing all potential
#    consequences resulting from its eventual inadequacies and bugs.
#    End users who are looking for a ready-to-use solution with commercial
#    guarantees and support are strongly advised to contact a Free Software
#    Service Company.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    "name": "Multiline Payment Export",
    "version": "1.1",
    'author': "Thamini S.à.R.L,Odoo Community Association (OCA)",
    "maintainer": "ACSONE SA/NV",
    "website": "http://www.acsone.eu",
    "images": [],
    "category": "Generic Modules/Accounting",
    "complexity": "normal",
    "depends": ["account_payment"],
    "description":  """
Accounting Payment Orders Multiline Export
==========================================

This module allows to export payment orders into ABBL VIR 2000 Multiline Format.

TODO:
- IBLC info (cfr. code multiline 77B)
- Translations, images, demo and sample
- go through native payment.line_ids structure instead of rereading payment lines into an alternate structure
""",
    "init_xml": ["account_multiline_payment_data.xml"],
    "update_xml": [
        "account_multiline_payment_view.xml",
        "wizard/account_multiline_payment_export_view.xml",
        "security/ir.model.access.csv",
    ],
    "demo_xml": [],
    "test": [],
    "active": False,
    "licence": "AGPL-3",
    "installable": True,
    "auto_install": False,
    "application": False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
