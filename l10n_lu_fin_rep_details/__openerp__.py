# -*- coding: utf-8 -*-
##############################################################################
#
#    Authors: Laetitia Gangloff
#    Copyright (c) 2014 Acsone SA/NV (http://www.acsone.eu)
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
    "name": "Luxembourg - Accounting - Financial Report Details",
    "version": "8.0.0.1.0",
    "author": "ACSONE SA/NV,Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "category": "Accounting & Finance",
    "website": "http://acsone.eu",
    "depends": ["l10n_lu_ext"],
    "description": """
    Luxemburg financial report details

    Display account details in the following Luxemburg financial reports
    * balance sheet
    * abbreviated balance sheet
    * profit and loss
    * abbreviated profit and loss
""",
    "data": [
        "account_financial_report.xml",
        "account_financial_report_abr.xml",
    ],
    "active": False,
    "installable": True
}
