# -*- coding: utf-8 -*-
# Copyright 2017 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Luxemburg MIS Builder tax reports',
    'summary': """
        Luxemburg tax reports based on MIS Builder""",
    'version': '10.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'ACSONE SA/NV,Odoo Community Association (OCA)',
    'website': 'https://acsone.eu/',
    'depends': [
        'l10n_lu',
        'mis_builder',
    ],
    'data': [
        'data/mis_report_styles.xml',
        'data/account.account.tag-2015.csv',
        'data/account.tax.template-2015.xml',
        'data/mis_tax_analysis.xml',
    ],
    'post_init_hook': 'update_tax_tags',
}
