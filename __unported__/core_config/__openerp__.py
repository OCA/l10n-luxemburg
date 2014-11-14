# -*- coding: utf-8 -*-
##############################################################################
#
#    core_config module for OpenERP, Core Configuration Options
#    Copyright (C) 2010 Thamini S.à.R.L (<http://www.thamini.com>) Xavier ALT
#
#    This file is a part of core_config
#
#    core_config is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    core_config is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    "name": "Core Config",
    "version": "0.1",
    "author": "Thamini",
    "category": "Generic Modules/Others",
    "website": "http://www.thamini.com",
    "description": "",
    "depends": ['base'],
    "init_xml": [
    ],
    "update_xml": [
        "ir_config_view.xml",
        "security/ir.model.access.csv"
    ],
    "active": False,
    "installable": False
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
