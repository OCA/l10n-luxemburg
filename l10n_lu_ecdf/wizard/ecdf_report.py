# -*- coding: utf-8 -*-
'''
This module provides a wizard able to generate XML annual financial reports
Generated files are ready for eCDF
Reports :
 - Profit & Loss (P&L)
 - Profit & Loss Abbreviated (P&L)
 - Balance Sheet (BS)
 - Balance Sheet Abbreviated (BS)
 - Chart of Accounts (CA)

Generation is based on MIS Builder
'''

from datetime import datetime
from datetime import timedelta
from cStringIO import StringIO
import re as re
import base64

from lxml import etree
from openerp import models, fields, api, tools
from openerp.exceptions import ValidationError
from openerp.exceptions import Warning as UserError
from openerp.tools.translate import _
from openerp.addons.mis_builder.models.aep import\
    AccountingExpressionProcessor as AEP
from openerp.addons.mis_builder.models.accounting_none import AccountingNone


class EcdfReport(models.TransientModel):
    '''
    This wizard allows to generate three types of financial reports :
        - Profit & Loss (P&L)
        - Balance Sheet (BS)
        - Chart of Accounts (CA)
    P&L and BS can be generated in abbreviated version or not
    The selected reports (max. 3) are written in a downloadable XML file
    '''
    _name = 'ecdf.report'
    _description = 'eCDF Report Wizard'
    _inherit = "account.common.report"

    # Main info
    language = fields.Selection(
        (('FR', 'FR'), ('DE', 'DE'), ('EN', 'EN')),
        'Language',
        required=True
    )
    target_move = fields.Selection(
        [('posted', 'All Posted Entries'), ('all', 'All Entries')],
        string='Target Moves',
        required=True,
        default='posted'
    )
    # Reports types
    with_pl = fields.Boolean('Profit & Loss',
                             default=True)
    with_bs = fields.Boolean('Balance Sheet',
                             default=True)
    with_ac = fields.Boolean('Chart of Accounts', default=True)
    reports_type = fields.Selection((('full', 'Full'),
                                     ('abbreviated', 'Abbreviated')),
                                    'Reports Type',
                                    default='full',
                                    required=True)
    # Fiscal years
    current_fiscyear = fields.Many2one('account.fiscalyear',
                                       'Current Fiscal Year',
                                       required=True)
    prev_fiscyear = fields.Many2one('account.fiscalyear',
                                    'Previous Fiscal Year')
    # Comments
    remarks = fields.Text('Comments')
    # Agent
    matricule = fields.Char('Matricule',
                            size=13)
    vat = fields.Char("Tax ID",
                      size=10)
    company_registry = fields.Char('Company Registry',
                                   size=7)
    # File name (computed)
    file_reference = fields.Char('File name',
                                 size=24,
                                 compute='_compute_file_reference')
    full_file_name = fields.Char('Full file name',
                                 size=28)
    # File
    xml_file = fields.Binary('XML File', readonly=True)

    @api.multi
    @api.constrains('matricule')
    def check_matr(self):
        '''
        Constraint : lenght of Matricule must be 11 or 13
        '''
        for record in self:
            if not record.matricule:
                return
            if len(record.matricule) not in [11, 13]:
                raise ValidationError(_('Matricule must be 11 or 13 \
                characters long.'))

    @api.multi
    @api.constrains('company_registry')
    def check_rcs(self):
        '''
        Constraint : regex validation on RCS Number
        '''
        exp = r"""^[A-Z][^0]\d{1,5}$"""
        rexp = re.compile(exp, re.X)
        for record in self:
            if not record.company_registry:
                return
            if not rexp.match(record.company_registry):
                raise ValidationError(_('RCS number must begin with an \
                uppercase letter followed by 2 to 6 digits. \
                The first digit must not be 0.'))

    @api.multi
    @api.constrains('vat')
    def check_vat(self):
        '''
        Constraint : regex validation on VAT Number
        '''
        exp = r"""^[A-Z]{2}\d{8}$"""
        rexp = re.compile(exp, re.X)
        for record in self:
            if not record.vat:
                return
            if not rexp.match(record.vat):
                raise ValidationError(_('VAT number must begin with two \
                uppercase letters followed by 8 digits.'))

    @api.depends('chart_account_id.company_id.ecdf_prefixe')
    @api.multi
    def _compute_file_reference(self):
        '''
        000000XyyyymmddThhmmssNN
        Position 1 - 6: eCDF prefix of the user's company
        Position 7: file type (X for XML files)
        Position 8 - 15: creation date of the file, format yyyymmdd
        Position 16: the character « T » (Time)
        Position 17 - 22: creation time of the file, format hhmmss
        Position 23 - 24: sequence number (NN) in range (01 - 99)
        for the unicity of the names of the files created in the same second
        '''
        for record in self:
            nbr = 1
            dtf = "X%Y%m%dT%H%M%S"
            prefixe = record.chart_account_id.company_id.ecdf_prefixe
            if not prefixe:
                prefixe = '000000'
            res = prefixe + datetime.now().strftime(dtf) + str("%02d" % nbr)
            record.file_reference = res

    @api.multi
    @api.onchange('chart_account_id')
    def _onchange_company(self):
        '''
        On Change : 'chart_account_id'
        Fields 'current_fiscyear' and 'prev_fiscyear' are reset
        '''
        for record in self:
            record.current_fiscyear = False
            record.prev_fiscyear = False

    @api.multi
    @api.onchange('current_fiscyear')
    def _onchange_current_fiscal_year(self):
        '''
        On Change : 'current_fiscyear'
        The field 'prev_fiscyear' is set with the year before current_fiscyear
        '''
        for rec in self:
            rec.prev_fiscyear = False
            if rec.current_fiscyear:
                # get the date stop
                previous_date_stop = datetime.strftime(
                    datetime.strptime(
                        rec.current_fiscyear.date_start,
                        "%Y-%m-%d"
                    ) - timedelta(days=1),
                    "%Y-%m-%d"
                )
                # search fiscal year with the previous date stop as date stop
                rec.prev_fiscyear = rec.env['account.fiscalyear'].search(
                    [('date_stop', '=', previous_date_stop),
                     ('company_id', '=', rec.current_fiscyear.company_id.id)]
                )

    @api.multi
    @api.constrains('prev_fiscyear')
    def _check_prev_fiscyear(self):
        '''
        Constraint : prev_fiscyear < current_fiscyear
        '''
        for record in self:
            prev_fiscyear_date_stop = record.prev_fiscyear.date_stop
            current_fiscyear_date_start = record.current_fiscyear.date_start

            if prev_fiscyear_date_stop > current_fiscyear_date_start:
                raise ValidationError(
                    _('Previous fiscal year must be before the current one'))

    @staticmethod
    def get_ecdf_file_version():
        '''
        :returns: the XML file version
        '''
        return '1.1'

    @staticmethod
    def get_interface():
        '''
        :returns: eCDF interface ID (provided by eCDF)
        '''
        return 'COPL3'

    @api.multi
    def get_matr_declarer(self):
        '''
        :returns: Luxemburg matricule of the company
        If no matricule, ValueError exception is raised
        '''
        for record in self:
            matr = record.chart_account_id.company_id.l10n_lu_matricule
            if not matr:
                raise ValueError(_('Matricule not present'))
            return matr

    @api.multi
    def get_rcs_declarer(self):
        '''
        :returns: RCS number of the company, 7 characters
        If no RCS number, default value 'NE' is returned
        (RCS : 'Numéro de registre de Commerce et des Sociétés')
        '''
        for record in self:
            rcs = record.chart_account_id.company_id.company_registry
            if rcs:
                return rcs
            else:
                return 'NE'

    @api.multi
    def get_vat_declarer(self):
        '''
        :returns: VAT number of the company, 8 characters, without the two\
        uppercase letters 'LU'
        If no VAT number, default value 'NE' is returned
        '''
        for record in self:
            vat = record.chart_account_id.company_id.vat
            if vat:
                if vat.startswith('LU'):
                    vat = vat[2:]
                return vat
            else:
                return 'NE'

    @api.multi
    def get_matr_agent(self):
        '''
        :returns: Agent matricule provided in the form
        If no agent matricule provided, the company one is returned
        '''
        for record in self:
            if record.matricule:
                return record.matricule
            else:
                return record.get_matr_declarer()

    @api.multi
    def get_rcs_agent(self):
        '''
        :returns: RCS number (Numéro de registre de Commerce et des Sociétés)\
        provided in the form.
        If no RCS number has been provided, the company one is returned
        If no RCS number of the company, default value 'NE' is returned
        '''
        for record in self:
            if record.company_registry:
                return record.company_registry
            else:
                return record.get_rcs_declarer()

    @api.multi
    def get_vat_agent(self):
        '''
        :returns: VAT number provided in the form. If no VAT number has been\
        provided, the VAT number of the company is returned, without the two\
        uppercase letters 'LU'.
        If no VAT number of the company, default value 'NE' is returned
        '''
        for record in self:
            if record.vat:
                vat = record.vat
                if vat.startswith('LU'):
                    vat = vat[2:]
                return vat
            else:
                return record.get_vat_declarer()

    @api.multi
    def get_language(self):
        '''
        :returns: the selected language in the form. Values can be :
                    - "FR" for french
                    - "DE" for german
                    - "EN" for english
        '''
        for record in self:
            return record.language

    # 12. Profit/Perte de l'exercice are mandatory even if there are no moves
    KEEP_ZERO = (
        # CA_PLANCOMPTA
        "639", "640", "735", "736",
    )

    def _append_num_field(self, element, ecdf, val, comment=None):
        '''
        A numeric field's value can be a integer or a float
        The only decimal separator accepted is the coma (",")
        The point (".") is not accepted as a decimal separator nor as a \
        thousands separator
        :param element: XML node
        :param ecdf: eCDF technical code
        :param val: value to add in the XML node
        :param comment: Optional comment
        '''
        if val is None or val is AccountingNone:
            if ecdf in self.KEEP_ZERO:
                val = 0.0
            else:
                return
        value = round(val, 2) or 0.0
        if comment:
            element.append(etree.Comment(comment))
        child = etree.Element('NumericField', id=ecdf)
        child.text = ("%.2f" % value).replace('.', ',')
        element.append(child)

    @api.multi
    def _append_fr_lines(self, data_curr, form_data, data_prev=None):
        '''
        Appends lines "NumericField" in the "form_data" node
        :param data_curr: data of the previous year
        :param form_data: XML node "form_data"
        :param data_prev: date of the previous year
        '''
        # Regex : group('current') : ecdf_code for current year
        #         group('previous') : ecdf_code for previous year
        exp = r"""^ecdf\_(?P<previous>\d*)\_(?P<current>\d*)"""
        rexp = re.compile(exp, re.X)
        for record in self:
            for report in data_curr:
                line_match = rexp.match(report['kpi_technical_name'])
                if line_match:
                    ecdf_code = line_match.group('current')
                    record._append_num_field(
                        form_data,
                        ecdf_code,
                        report['val'],
                        comment=" current - %s " % report['kpi_name']
                    )
            if data_prev:
                # Previous fiscal year
                for report in data_prev:
                    line_match = rexp.match(report['kpi_technical_name'])
                    if line_match:
                        ecdf_code = line_match.group('previous')
                        record._append_num_field(
                            form_data,
                            ecdf_code,
                            report['val'],
                            comment=" previous - %s " % report['kpi_name']
                        )
            else:
                # No Previous fical year: we must output 0.0 for
                # items where we have a value in current fiscal year
                form_data.append(etree.Comment(" no previous year"))
                for report in data_curr:
                    line_match = rexp.match(report['kpi_technical_name'])
                    if line_match:
                        ecdf_code = line_match.group('previous')
                        if report['val'] not in (AccountingNone, None):
                            record._append_num_field(form_data,
                                                     ecdf_code,
                                                     0.0)

    @api.multi
    def _get_finan_report(self, data_current, report_type, data_previous=None):
        '''
        Generates a financial report (P&L or Balance Sheet) in XML format
        :param data_current: dictionary of data of the current year
        :param report_type: technical name of the report type
        :param data_previous: dictionary of data of the previous year
        :returns: XML node called "declaration"
        '''
        self.ensure_one()
        period_ids = (self.env['account.period'].search(
            [('special', '=', False),
                ('fiscalyear_id', '=', self.current_fiscyear.id)]
        )).sorted(key=lambda r: r.date_start)

        if not period_ids:
            return

        period_from = period_ids[0]
        period_to = period_ids[-1]
        currency = self.chart_account_id.company_id.currency_id
        declaration = etree.Element('Declaration',
                                    type=report_type,
                                    language=self.get_language(),
                                    model='1')
        year = etree.Element('Year')
        year.text = datetime.strptime(period_from.date_start,
                                      "%Y-%m-%d").strftime("%Y")
        period = etree.Element('Period')
        period.text = '1'
        form_data = etree.Element('FormData')
        tfid = etree.Element('TextField', id='01')
        tfid.text = datetime.strptime(period_from.date_start,
                                      "%Y-%m-%d").strftime("%d/%m/%Y")
        form_data.append(tfid)
        tfid = etree.Element('TextField', id='02')
        tfid.text = datetime.strptime(period_to.date_stop,
                                      "%Y-%m-%d").strftime("%d/%m/%Y")
        form_data.append(tfid)
        tfid = etree.Element('TextField', id='03')
        tfid.text = currency.name
        form_data.append(tfid)

        self._append_fr_lines(data_current,
                              form_data,
                              data_previous)

        declaration.append(year)
        declaration.append(period)
        declaration.append(form_data)

        return declaration

    @api.multi
    def _get_chart_ac(self, data, report_type):
        '''
        Generates the chart of accounts in XML format
        :param data: Dictionary of values (name, technical name, value)
        :param report_type: Technical name of the report type
        :returns: XML node called "declaration"
        '''
        self.ensure_one()
        # Regex : group('debit') : ecdf_code for debit column
        #         group('credit') ecdf_code for credit column
        exp = r"""^ecdf\_(?P<debit>\d*)\_(?P<credit>\d*)"""
        rexp = re.compile(exp, re.X)

        period_ids = (self.env['account.period'].search(
            [('special', '=', False),
                ('fiscalyear_id', '=', self.current_fiscyear.id)]
        )).sorted(key=lambda r: r.date_start)

        if not period_ids:
            return

        period_from = period_ids[0]
        period_to = period_ids[-1]
        declaration = etree.Element('Declaration',
                                    type=report_type,
                                    language=self.get_language(),
                                    model='1')
        year = etree.Element('Year')
        year.text = datetime.strptime(period_from.date_start,
                                      "%Y-%m-%d").strftime("%Y")
        period = etree.Element('Period')
        period.text = '1'
        form_data = etree.Element('FormData')
        tfid = etree.Element('TextField', id='01')
        tfid.text = datetime.strptime(period_from.date_start,
                                      "%Y-%m-%d").strftime("%d/%m/%Y")
        form_data.append(tfid)
        tfid = etree.Element('TextField', id='02')
        tfid.text = datetime.strptime(period_to.date_stop,
                                      "%Y-%m-%d").strftime("%d/%m/%Y")
        form_data.append(tfid)
        tfid = etree.Element('TextField', id='03')
        tfid.text = self.chart_account_id.company_id.currency_id.name
        form_data.append(tfid)

        if self.remarks:  # add remarks in chart of accounts
            fid = etree.Element('TextField', id='2385')
            fid.text = self.remarks
            form_data.append(fid)

        for report in data:
            line_match = rexp.match(report['kpi_technical_name'])
            if line_match:
                if report['val'] not in (AccountingNone, None):
                    balance = round(report['val'], 2)
                    if balance <= 0:  # 0.0 must be in the credit column
                        ecdf_code = line_match.group('credit')
                        balance = abs(balance)
                        comment = 'credit'
                    else:
                        ecdf_code = line_match.group('debit')
                        comment = 'debit'

                    # code 106 appears 2 times in the chart of accounts
                    # with different ecdf codes
                    # so we hard-code it here:
                    # this is the only exception to the general algorithm
                    # TODO why not have 2 kpi's which return the same result
                    #      so the algorithm remains generic?
                    if report['kpi_name'][:5] == '106 -':
                        if balance <= 0.0:
                            ecdf_codes = ['0118', '2260']
                        else:
                            ecdf_codes = ['0117', '2259']

                        self._append_num_field(
                            form_data, ecdf_codes[0], balance,
                            comment=" %s - %s " % (comment,
                                                   report['kpi_name'])
                        )
                        self._append_num_field(
                            form_data, ecdf_codes[1], balance,
                            comment=" %s - %s " % (comment,
                                                   report['kpi_name'])
                        )

                    self._append_num_field(
                        form_data, ecdf_code, balance,
                        comment=" %s - %s " % (comment, report['kpi_name'])
                    )

        declaration.append(year)
        declaration.append(period)
        declaration.append(form_data)

        return declaration

    @api.multi
    def compute(self, mis_template, fiscal_year):
        '''
        Compute the values for a fiscal year, using the MIS Buildter template.

        :param mis_template: template MIS Builder of the report
        :param fiscal_year: fiscal year to compute
        :returns: list of dict(kpi_name, kpi_technical_name, val)
        '''
        self.ensure_one()

        # prepare AccountingExpressionProcessor
        aep = AEP(self.env)
        for kpi in mis_template.kpi_ids:
            aep.parse_expr(kpi.expression)
        aep.done_parsing(self.chart_account_id)

        # Search periods
        period_from = None
        period_to = None
        period_ids = self.env['account.period'].search(
            [('special', '=', False),
                ('fiscalyear_id', '=', fiscal_year.id)])
        period_ids = period_ids.sorted(key=lambda r: r.date_start)
        if period_ids:
            period_from = period_ids[0]
            period_to = period_ids[-1]

        # Compute KPI values
        kpi_values = mis_template._compute(self.env.lang, aep,
                                           fiscal_year.date_start,
                                           fiscal_year.date_stop,
                                           period_from,
                                           period_to,
                                           self.target_move)
        # prepare result
        res = []
        for kpi in mis_template.kpi_ids:
            res.append({
                'kpi_name': kpi.description,
                'kpi_technical_name': kpi.name,
                'val': kpi_values[kpi.name]['val'],
            })

        return res

    @api.multi
    def print_xml(self):
        '''
        Generates the selected financial reports in XML format
        The string is written in the base64 field "xml_file"
        '''
        self.ensure_one()
        ecdf_namespace = "http://www.ctie.etat.lu/2011/ecdf"
        nsmap = {None: ecdf_namespace}  # the default namespace(no prefix)

        root = etree.Element("eCDFDeclarations", nsmap=nsmap)

        # File Reference
        ref = self.file_reference
        self.full_file_name = ref + '.xml'  # for the download widget
        file_reference = etree.Element('FileReference')
        file_reference.text = ref
        root.append(file_reference)
        # File Version
        file_version = etree.Element('eCDFFileVersion')
        file_version.text = self.get_ecdf_file_version()
        root.append(file_version)
        # Interface
        interface = etree.Element('Interface')
        interface.text = self.get_interface()
        root.append(interface)
        # Agent
        agent = etree.Element('Agent')
        matr_agent = etree.Element('MatrNbr')
        matr_agent.text = self.get_matr_agent()
        rcs_agent = etree.Element('RCSNbr')
        rcs_agent.text = self.get_rcs_agent()
        vat_agent = etree.Element('VATNbr')
        vat_agent.text = self.get_vat_agent()
        agent.append(matr_agent)
        agent.append(rcs_agent)
        agent.append(vat_agent)
        root.append(agent)
        # Declarations
        declarations = etree.Element('Declarations')
        declarer = etree.Element('Declarer')
        matr_declarer = etree.Element('MatrNbr')
        matr_declarer.text = self.get_matr_declarer()
        rcs_declarer = etree.Element('RCSNbr')
        rcs_declarer.text = self.get_rcs_declarer()
        vat_declarer = etree.Element('VATNbr')
        vat_declarer.text = self.get_vat_declarer()
        declarer.append(matr_declarer)
        declarer.append(rcs_declarer)
        declarer.append(vat_declarer)

        reports = []
        templ = {
            'CA_PLANCOMPTA': 'l10n_lu_mis_reports.mis_report_ca',
            'CA_BILAN': 'l10n_lu_mis_reports.mis_report_bs',
            'CA_BILANABR': 'l10n_lu_mis_reports.mis_report_abr_bs',
            'CA_COMPP': 'l10n_lu_mis_reports.mis_report_pl',
            'CA_COMPPABR': 'l10n_lu_mis_reports.mis_report_abr_pl',
        }

        # Report
        if self.with_ac:  # Chart of Accounts
            reports.append({'type': 'CA_PLANCOMPTA',
                            'templ': templ['CA_PLANCOMPTA']})
        if self.with_bs:  # Balance Sheet
            if self.reports_type == 'full':
                reports.append({'type': 'CA_BILAN',
                                'templ': templ['CA_BILAN']})
            else:  # Balance Sheet abreviated
                reports.append({'type': 'CA_BILANABR',
                                'templ': templ['CA_BILANABR']})
        if self.with_pl:  # Profit and Loss
            if self.reports_type == 'full':
                reports.append({'type': 'CA_COMPP',
                                'templ': templ['CA_COMPP']})
            else:  # Profit and Loss abreviated
                reports.append({'type': 'CA_COMPPABR',
                                'templ': templ['CA_COMPPABR']})

        if not reports:
            raise UserError(_('No report type selected'),
                            _('Please, select a report type'))

        error_not_found = ""
        for report in reports:
            # Search MIS template by XML ID
            mis_env = self.env['mis.report']
            id_mis_report = self.env.ref(report['templ']).id
            mis_report = mis_env.search([('id', '=', id_mis_report)])

            # If the MIS template has not been found
            if not mis_report or not len(mis_report):
                error_not_found += '\n\t - ' + report['templ']

            data_current = self.compute(mis_report,
                                        self.current_fiscyear)
            data_previous = None

            if report['type'] != 'CA_PLANCOMPTA':
                if self.prev_fiscyear:  # Previous year
                    data_previous = self.compute(mis_report,
                                                 self.prev_fiscyear)
                financial_report = self._get_finan_report(data_current,
                                                          report['type'],
                                                          data_previous)
                if financial_report is not None:
                    declarer.append(financial_report)
            else:  # Chart of accounts
                chart_of_account = self._get_chart_ac(data_current,
                                                      report['type'])
                if chart_of_account is not None:
                    declarer.append(chart_of_account)

        # Warning message if template(s) not found
        if error_not_found:
            raise UserError(
                _('MIS Template(s) not found :'),
                error_not_found)

        # Declarer
        declarations.append(declarer)
        root.append(declarations)

        # Write the xml
        xml = etree.tostring(root, encoding='UTF-8', xml_declaration=True)
        # Validate the generated XML schema
        xsd = tools.file_open('l10n_lu_ecdf/xsd/ecdf-v1.1.xsd')
        xmlschema_doc = etree.parse(xsd)
        xmlschema = etree.XMLSchema(xmlschema_doc)
        # Reparse only to have line numbers in error messages?
        xml_to_validate = StringIO(xml)
        parse_result = etree.parse(xml_to_validate)
        # Validation
        if xmlschema.validate(parse_result):
            self.xml_file = base64.encodestring(xml)
            return {
                'name': 'eCDF Report',
                'type': 'ir.actions.act_window',
                'res_model': 'ecdf.report',
                'view_mode': 'form',
                'view_type': 'form',
                'res_id': self.id,
                'views': [(False, 'form')],
                'target': 'new',
            }
        else:
            error = xmlschema.error_log[0]
            raise UserError(
                _('The generated file doesn\'t fit the required schema !'),
                error.message)
