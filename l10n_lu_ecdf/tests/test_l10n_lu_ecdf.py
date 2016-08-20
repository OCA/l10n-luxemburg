# -*- coding: utf-8 -*-

from datetime import datetime
import logging
import re as re

from lxml import etree
from openerp.addons.mis_builder.models.accounting_none import AccountingNone
from openerp.exceptions import ValidationError
from openerp.exceptions import Warning as UserError
from openerp.tests import common

_logger = logging.getLogger(__name__)


class TestL10nLuEcdf(common.TransactionCase):

    def setUp(self):
        super(TestL10nLuEcdf, self).setUp()

        self.ecdf_report = self.env['ecdf.report']
        self.res_company = self.env['res.company']
        self.account_fiscalyear = self.env['account.fiscalyear']
        self.account_account = self.env['account.account']

        # Company instance
        self.company = self.env.ref('base.main_company')
        self.company.l10n_lu_matricule = '0000000000000'
        self.company.company_registry = 'L654321'
        self.company.vat = 'LU12345613'

        # 'Chart of account' instance
        self.chart_of_account = self.account_account.search([('parent_id',
                                                              '=',
                                                              False)])

        # Current fiscal year instance
        self.current_fiscal_year = self.account_fiscalyear.create({
            'company_id': self.company.id,
            'name': 'current_fiscalyear',
            'code': '123456',
            'date_start': datetime.strptime('01012015', "%d%m%Y").date(),
            'date_stop': datetime.strptime('31122015', "%d%m%Y").date()})

        # Previous fiscal year instance
        self.previous_fiscal_year = self.account_fiscalyear.create({
            'company_id': self.company.id,
            'name': 'previous_fiscalyear',
            'code': '654321',
            'date_start': datetime.strptime('01012014', "%d%m%Y").date(),
            'date_stop': datetime.strptime('31122014', "%d%m%Y").date()})

        # Fiscal year : 2008
        self.fiscal_year_2008 = self.account_fiscalyear.create({
            'company_id': self.company.id,
            'name': 'fiscalyear_2008',
            'code': '214365',
            'date_start': datetime.strptime('01012008', "%d%m%Y").date(),
            'date_stop': datetime.strptime('31122008', "%d%m%Y").date()})

        # Fiscal year : 2007
        self.fiscal_year_2007 = self.account_fiscalyear.create({
            'company_id': self.company.id,
            'name': 'fiscalyear_2007',
            'code': '563412',
            'date_start': datetime.strptime('01012007', "%d%m%Y").date(),
            'date_stop': datetime.strptime('31122007', "%d%m%Y").date()})

        # eCDF report instance
        self.report = self.env['ecdf.report'].create({
            'language': 'FR',
            'target_move': 'posted',
            'with_pl': True,
            'with_bs': True,
            'with_ac': True,
            'reports_type': 'full',
            'current_fiscyear': self.current_fiscal_year.id,
            'prev_fiscyear': self.previous_fiscal_year.id,
            'remarks': "comment",
            'matricule': '1111111111111',
            'vat': 'LU12345678',
            'company_registry': 'L123456',
            'chart_account_id': self.chart_of_account.id})

    def test_check_matr(self):
        '''
        Matricule must be 11 or 13 characters long
        '''
        # Matricule too short (10)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.report.matricule = '1111111111'

        # Matricule's length not 11 nor 13 characters (12)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.report.matricule = '111111111112'

        # Matricule OK
        try:
            self.report.matricule = '11111111111'
        except ValidationError:
            self.fail()

        # No matricule
        try:
            self.report.matricule = None
        except ValidationError:
            self.fail()

    def test_check_rcs(self):
        '''
        RCS number must begin with an uppercase letter\
        followed by 2 to 6 digits. The first digit must not be 0
        '''
        # RCS doesn't begin with an upercase letter (lowercase letter instead)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.report.company_registry = 'l123456'

        # First digit is a zero
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.report.company_registry = 'L0234567'

        # RCS too short
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.report.company_registry = 'L1'

        # RCS dont begin with a letter
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.report.company_registry = '1123456'

        # RCS OK
        try:
            self.report.company_registry = 'L123456'
        except ValidationError:
            self.fail()

        # No RCS
        try:
            self.report.company_registry = None
        except ValidationError:
            self.fail()

    def test_check_vat(self):
        '''
        VAT number must begin with two uppercase letters followed by 8 digits.
        '''
        # VAT doesn't begin with two upercase letters (lowercase instead)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.report.vat = 'lu12345678'

        # VAT doesn't begin with two letters
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.report.vat = '0912345678'

        # VAT too short (missing digits)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.report.vat = 'LU1234567'

        # VAT OK
        try:
            self.report.vat = 'LU12345678'
        except ValidationError:
            self.fail()

        # No VAT
        try:
            self.report.vat = None
        except ValidationError:
            self.fail()

    def check_prev_fiscyear(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.report.previous_fiscal_year = self.current_fiscal_year

    def test_compute_file_reference(self):
        '''
        File ref must match the following pattern : 000000XyyyymmddThhmmssNN
        '''
        # Regular expression of the expected file name
        exp = r"""^\d{6}X\d{8}T\d{8}$"""
        rexp = re.compile(exp, re.X)

        self.report._compute_file_reference()

        self.assertIsNotNone(rexp.match(self.report.file_reference))

    def test_get_ecdf_file_version(self):
        report_file_version = self.report.get_ecdf_file_version()
        file_version = '1.1'

        self.assertEqual(report_file_version, file_version)

    def test_get_interface(self):
        report_interface = self.report.get_interface()
        interface = 'COPL3'

        self.assertEqual(report_interface, interface)

    def test_get_language(self):
        language = self.report.get_language()
        expected = 'FR'

        self.assertEqual(language, expected)

    # GETTERS AGENT

    def test_get_matr_agent(self):
        # With a matricule set to the agent
        report_matr = self.report.get_matr_agent()
        expected = '1111111111111'
        self.assertEqual(report_matr, expected)

        # With no matricule set to the agent
        self.report.matricule = False
        report_matr = self.report.get_matr_agent()
        # The excpected matricule is the company one
        expected = '0000000000000'
        self.assertEqual(report_matr, expected)

    def test_get_rcs_agent(self):
        # With a rcs number set to the agent
        report_rcs = self.report.get_rcs_agent()
        expected = 'L123456'
        self.assertEqual(report_rcs, expected)

        # With no rcs number set to the agent
        self.report.company_registry = False
        report_rcs = self.report.get_rcs_agent()
        # The expected rcs is the company one
        expected = 'L654321'
        self.assertEqual(report_rcs, expected)

    def test_get_vat_agent(self):
        # With a vat number set to the agent, without the two letters
        report_vat = self.report.get_vat_agent()
        expected = '12345678'
        self.assertEqual(report_vat, expected)

        # With no vat number set to the agent
        self.report.vat = False
        report_vat = self.report.get_vat_agent()
        # The expected vat is the company one, without the two letters
        expected = '12345613'
        self.assertEqual(report_vat, expected)

    # GETTERS DECLARER

    def test_get_matr_declarer(self):
        # With a matricule set to the company
        declarer_matr = self.report.get_matr_declarer()
        expected = '0000000000000'
        self.assertEqual(declarer_matr, expected)

        # With no matricule set to the company
        self.company.l10n_lu_matricule = False
        with self.assertRaises(ValueError), self.cr.savepoint():
            declarer_matr = self.report.get_matr_declarer()

    def test_get_rcs_declarer(self):
        # With a rcs number set to the company
        declarer_rcs = self.report.get_rcs_declarer()
        expected = 'L654321'
        self.assertEqual(declarer_rcs, expected)

        # With no rcs number set to the company
        self.company.company_registry = False
        declarer_rcs = self.report.get_rcs_declarer()
        expected = 'NE'
        self.assertEqual(declarer_rcs, expected)

    def test_get_vat_declarer(self):
        # With a vat number set to the company
        declarer_vat = self.report.get_vat_declarer()
        expected = '12345613'
        self.assertEqual(declarer_vat, expected)

        # With no vat number set to the company
        self.company.vat = False
        declarer_vat = self.report.get_vat_declarer()
        expected = 'NE'
        self.assertEqual(declarer_vat, expected)

    def test_append_num_field(self):
        '''
        Test of bordeline cases of the method append_num_field
        '''
        # Initial data : code not in KEEP_ZERO
        ecdf = '123'
        comment = "A comment"

        # Test with valid float value
        element = etree.Element('FormData')
        val = 5.5
        self.report._append_num_field(element, ecdf, val, comment)
        expected = '<FormData><!--A comment--><NumericField id="123">\
5,50</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

        # Test with None value, code not in KEEP_ZERO
        element = etree.Element('FormData')
        val = None
        self.report._append_num_field(element, ecdf, val, comment)
        expected = '<FormData/>'
        self.assertEqual(etree.tostring(element), expected)

        # Test with AccountingNone value, code not in KEEP_ZERO
        element = etree.Element('FormData')
        val = AccountingNone
        self.report._append_num_field(element, ecdf, val, comment)
        expected = '<FormData/>'
        self.assertEqual(etree.tostring(element), expected)

        # Data : code in KEEP_ZERO
        ecdf = '639'

        # Test with None value, code in KEEP_ZERO
        element = etree.Element('FormData')
        val = None
        self.report._append_num_field(element, ecdf, val, comment)
        expected = '<FormData><!--A comment--><NumericField id="639">0,00\
</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

        # Test with AccountingNone value, code in KEEP_ZERO
        element = etree.Element('FormData')
        val = AccountingNone
        self.report._append_num_field(element, ecdf, val, comment)
        expected = '<FormData><!--A comment--><NumericField id="639">0,00\
</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

        # Test without comment
        element = etree.Element('FormData')
        val = 5.5
        self.report._append_num_field(element, ecdf, val)
        expected = '<FormData><NumericField id="639">5,50</NumericField>\
</FormData>'
        self.assertEqual(etree.tostring(element), expected)

    def test_append_fr_lines(self):
        '''
        Test of method 'append_fr_lines' with and without previous year
        '''
        data_current = [{
            'kpi_name': 'A. CHARGES',
            'kpi_technical_name': 'ecdf_642_641',
            'val': 123},
            {'kpi_name': 'empty',
             'kpi_technical_name': '',
             'val': None}]

        data_previous = [{
            'kpi_name': 'A. CHARGES',
            'kpi_technical_name': 'ecdf_642_641',
            'val': 321},
            {'kpi_name': 'empty',
             'kpi_technical_name': '',
             'cols': None}]

        # Test with no previous year
        element = etree.Element('FormData')
        self.report._append_fr_lines(data_current, element)
        expected = '<FormData><!-- current - A. CHARGES -->\
<NumericField id="641">123,00</NumericField><!-- no previous year-->\
<NumericField id="642">0,00</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

        # Test with previous year
        element = etree.Element('FormData')
        self.report._append_fr_lines(data_current, element, data_previous)
        expected = '<FormData><!-- current - A. CHARGES -->\
<NumericField id="641">123,00</NumericField><!-- previous - A. CHARGES -->\
<NumericField id="642">321,00</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

    def test_onchange_current_fiscal_year(self):
        self.report.current_fiscyear = self.fiscal_year_2008.id
        self.report._onchange_current_fiscal_year()
        if self.report.prev_fiscyear != self.fiscal_year_2007:
            self.fail()

    def test_print_xml(self):
        '''
        Main test : generation of all types of reports
        Chart of account, Profit and Loss, Balance Sheet
        '''
        # Financial reports : Fiscal years with no period
        self.report.with_ac = False
        with self.assertRaises(UserError), self.cr.savepoint():
            self.report.print_xml()

        # Chart of account : Fiscal years with no period
        self.report.with_ac = True
        self.report.with_bs = False
        self.report.with_pl = False
        with self.assertRaises(UserError), self.cr.savepoint():
            self.report.print_xml()

        # Periods of fiscal years
        self.current_fiscal_year.create_period()
        self.previous_fiscal_year.create_period()

        # No report selected
        self.report.with_ac = False
        with self.assertRaises(UserError), self.cr.savepoint():
            self.report.print_xml()

        self.report.with_ac = True
        self.report.with_bs = True
        self.report.with_pl = True

        # Type : full
        self.report.print_xml()

        # Type abbreviated
        self.report.reports_type = 'abbreviated'
        self.report.print_xml()

        # With no previous fiscal year, abbreaviated
        self.report.prev_fiscyear = False
        self.report.print_xml()

        # With no previous year, full
        self.report.reports_type = 'full'
        self.report.print_xml()
