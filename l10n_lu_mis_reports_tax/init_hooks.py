# -*- coding: utf-8 -*-
# Copyright 2017 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


def update_tax_tags(cr, registry):
    from odoo.addons.account.models.chart_template \
        import migrate_tags_on_taxes
    migrate_tags_on_taxes(cr, registry)
