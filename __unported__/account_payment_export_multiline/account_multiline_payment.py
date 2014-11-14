# -*- coding: utf-8 -*-
##############################################################################
#
#    WARNING: This program as such is intended to be used by professional
#    programmers who take the whole responsibility of assessing all potential
#    consequences resulting from its eventual inadequacies and bugs.
#    End users who are looking for a ready-to-use solution with commercial
#    guarantees and support are strongly advised to contact a Free Software
#    Service Company.
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

from osv import osv, fields


class multiline_payment_export_history(osv.Model):
    _name = "multiline.payment.export.history"
    _description = "Multiline Payment Export History"
    _rec_name = 'payment_order_id'

    _columns = {
        'payment_order_id': fields.many2one('payment.order', 'Payment Order', readonly=True),
        'content': fields.binary('Multiline Content', readonly=True),
        'note': fields.text('Export Log', readonly=True),
        'state': fields.selection([('failed', 'Failed'), ('succeeded', 'Succeeded')], 'Status', readonly=True),

        'create_date': fields.datetime('Creation Date', required=True, readonly=True),
        'create_uid': fields.many2one('res.users', 'Creation User', required=True, readonly=True),
    }

    _order = "create_date desc"


class multiline_payment_charge_code(osv.Model):
    _name = "multiline.payment.charge.code"
    _description = "Multiline Payment Charge Code"
    _rec_name = 'code'

    _columns = {
        'code': fields.char('Charge Code', size=3, required=True),
        'description': fields.text('Description'),
    }


class multiline_payment_instruction_code(osv.Model):
    _name = "multiline.payment.instruction.code"
    _description = "Multiline Payment Instruction Code"

    _columns = {
        'name': fields.char('Name', size=64, required=True),
        'code': fields.char('Code', size=34, required=True),
    }


class payment_order_multiline_type(osv.Model):
    _inherit = "payment.order"

    _columns = {
        'grouped_payment': fields.boolean('Grouped Payment', states={'done': [('readonly', True)]}),
    }


class payment_line_instruction_code(osv.Model):
    _inherit = "payment.line"

    _columns = {
        'instruction_code_id': fields.many2one('multiline.payment.instruction.code', 'Instruction Code'),
    }


class payment_mode_multiline_ident(osv.Model):
    _inherit = "payment.mode"

    _columns = {
        'multiline_ident': fields.char('Multiline Ident', size=16, help="Multiline identification matricule"),
    }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
