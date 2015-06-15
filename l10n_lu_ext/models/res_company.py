# -*- coding: utf-8 -*-
##############################################################################
#
# This file is part of l10n_lu_ext,
# an Odoo module.
#
# Authors: ACSONE SA/NV (<http://acsone.eu>)
#
# l10n_lu_ext is free software:
# you can redistribute it and/or modify it under the terms of the GNU
# Affero General Public License as published by the Free Software
# Foundation,either version 3 of the License, or (at your option) any
# later version.
#
# l10n_lu_ext is distributed
# in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE. See the GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with l10n_lu_ext.
# If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields


class ResCompany(models.Model):

    _inherit = "res.company"

    l10n_lu_matricule = fields.Char(
        string='Luxembourg Matricule', size=13,
        help='Identification Number delivered by the Luxembourg authorities '
             'as soon as the company is registered')
