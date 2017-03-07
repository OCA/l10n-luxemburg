# -*- coding: utf-8 -*-
# Copyright 2015-2017 ACSONE SA/NV (<http://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields


class ResCompany(models.Model):

    _inherit = "res.company"

    l10n_lu_matricule = fields.Char(
        string='Luxembourg Matricule', size=13,
        help='Identification Number delivered by the Luxembourg authorities '
             'as soon as the company is registered')
