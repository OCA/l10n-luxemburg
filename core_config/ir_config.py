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

from osv import fields, osv
from tools.translate import _
from tools.misc import cache

class ir_config(osv.osv):
    _name = 'ir.config'
    _description = 'Database Config Options'

    def _get_type_selection(self, cr, uid, context=None):
        return  [
            ('str','String'),
            ('int','Integer'),
            ('float', 'Float'),
            ('bool','Boolean'),
            ('ref', 'Reference'),
            ('python','Python Code'),
        ]

    _columns = {
        'name': fields.char('Name', size=255, select=1, readonly=True),
        'type': fields.selection(_get_type_selection, 'Type', select=1, required=True, readonly=True),
        'value': fields.char('Value', size=64, select=1),
        'default_value': fields.char('Default Value', size=64, readonly=True),
        'description': fields.text('Description', readonly=True, translate=True),
    }

    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'The name already exists.'),
    ]

    _defaults = {
        'type': lambda *a: 'str',
    }

    def _get_value(self, option, value):
        type_dict = {
            'str': str,
            'int': int,
            'bool': bool,
            'float': float,
        }
        type_option = type_dict[option]
        if option == 'ref':
            ref_model, ref_id = value.strip().split(',')[:2]
            ref_pool = self.pool.get(ref_model).browse(cr, uid, int(ref_id))
            return ref_pool
        if value is None:
            return None
        return type_option(value)

    @cache(skiparg=2)
    def get(self, cr, uid, option_name):
        cr.sql_log = True
        cr.execute("SELECT value, default_value, type FROM ir_config WHERE name = %s LIMIT 1", (option_name,))
        data = cr.dictfetchone()
        cr.sql_log = False
        if data:
            # specific case for Python options
            if data['type'] == 'python':
                try:
                    fnct = getattr(self, 'get_value_'+option_name.replace('.','_'))
                    return fnct(cr, uid, option_name)
                except AttributeError:
                    return False
                except TypeError:
                    return False

            # get value, or as fallback default value
            if data['value']:
                res = self._get_value(data['type'], data['value'])
            else:
                res = self._get_value(data['type'], data['default_value'])
            return res
        return False

    def reset_default_values(self, cr, uid, ids, context=None):
        default_values = self.read(cr, uid, ids, ['default_value'])
        for default_value in default_values:
            self.write(cr, uid, [default_value['id']],
                       {'value': default_value['default_value']})

    def write(self, cr, uid, ids, vals, context=None):
        if 'value' in vals.keys():
            for option in self.read(cr, uid, ids, []):
                optname_validate = 'validate_'+option['name'].replace('.','_')
                opttype_validate = 'validate_type_'+option['type']
                try:
                    validate_fnct = getattr(self, optname_validate)
                    validate_fnct(cr, uid, option, vals, context=context)
                except AttributeError:
                    # getattr failed, fallback to option type validation
                    # here we don't catch AttributeError, because option type
                    # validation MUST exist!
                    type_validate_fnct = getattr(self, opttype_validate)
                    type_validate_fnct(cr, uid, option, vals, context=context)
        # overwrite the cache with new values
        cache.clean_caches_for_db(cr.dbname)
        # all options are valid with those vals
        return super(ir_config, self).write(cr, uid, ids, vals, context=context)

    def validate_type_str(self, cr, uid, option, vals, context=None):
        """default validation methods for string option
           @raise osv.except_osv in case of an error
        """
        #raise osv.except_osv(_('Error'), _('Invalid value for this type'))
        pass

    def validate_type_int(self, cr, uid, option, vals, context=None):
        """default validation methods for integer option
           @raise osv.except_osv in case of an error
        """
        if 'default_value' in vals.keys():
            if not vals['default_value'].isdigit():
                raise osv.except_osv(_('Error'), _('The dafault value must be a integer.'))
        if 'value' in vals.keys():
            if not vals['value'].isdigit():
                raise osv.except_osv(_('Error'), _('The value must be a integer.'))

    def validate_type_float(self, cr, uid, option, vals, context=None):
        """default validation methods for float option
           @raise osv.except_osv in case of an error
        """
        if 'default_value' in vals.keys():
            try:
                float(vals['default_value'])
            except ValueError:
                raise osv.except_osv(_('Error'), _('The default value must be a float.'))
        if 'value' in vals.keys():
            try:
                float(vals['value'])
            except ValueError:
                raise osv.except_osv(_('Error'), _('The value must be a float.'))

    def validate_type_boolean(self, cr, uid, option, vals, context=None):
        """default validation methods for boolean option
           @raise osv.except_osv in case of an error
        """
        if 'default_value' in vals.keys():
            if not vals['default_value'] in ['0', '1', '']:
                raise osv.except_osv(_('Error'), _('The dafault value must be a boolean.'))
        if 'value' in vals.keys():
            if not vals['value'] in ['0', '1', '']:
                raise osv.except_osv(_('Error'), _('The value must be a boolean.'))


ir_config()

