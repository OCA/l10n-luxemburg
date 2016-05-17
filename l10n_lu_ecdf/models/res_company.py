# -*- coding: utf-8 -*-

from openerp import models, fields


class res_company(models.Model):
    _inherit = "res.company"
    ecdf_prefixe = fields.Char("eCDF Prefix", size=6)
