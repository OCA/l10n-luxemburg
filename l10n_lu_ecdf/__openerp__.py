# -*- coding: utf-8 -*-

{
    "name": "eCDF annual reports",
    "version": "8.0.1.1.0",
    "author": "Odoo Community Association (OCA), ACSONE SA/NV",
    "license": "AGPL-3",
    "category": "Accounting & Finance",
    "website": "http://acsone.eu",
    "depends": ["l10n_lu_ext",
                "l10n_lu_mis_reports",
                "mis_builder"],
    "module": "",
    "summary": "Generates XML eCDF annual financial reports",
    "data": [
        "views/res_company.xml",
        "wizard/ecdf_report_view.xml",
    ],
    "installable": True,
}
