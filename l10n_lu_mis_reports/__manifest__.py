# -*- coding: utf-8 -*-
# Copyright 2015-2016 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': 'Luxembourg MIS Builder templates',
    'summary': """
        MIS Report templates for the Luxembourg P&L and Balance Sheets""",
    'author': 'ACSONE SA/NV,'
              'Odoo Community Association (OCA)',
    'website': 'http://acsone.eu',
    'category': 'Reporting',
    'version': '10.0.1.1.0',
    'license': 'AGPL-3',
    'depends': [
        'mis_builder',  # OCA/mis-builder
    ],
    'data': [
        'data/mis_report_styles.xml',
        'data/mis_report_pl.xml',
        'data/mis_report_pl_2016.xml',
        'data/mis_report_pl_2016_det.xml',
        'data/mis_report_bs.xml',
        'data/mis_report_bs_2016.xml',
        'data/mis_report_bs_2016_det.xml',
        'data/mis_report_ca.xml',
        'data/mis_report_abr_pl.xml',
        'data/mis_report_abr_bs.xml',
    ],
}
