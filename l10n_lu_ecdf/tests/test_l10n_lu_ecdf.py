# -*- coding: utf-8 -*-

from openerp.tests import common
from lxml import etree
from datetime import datetime
from openerp.addons.mis_builder.models.accounting_none import AccountingNone
import re as re
from openerp.exceptions import ValidationError


class TestL10nLuEcdf(common.TransactionCase):

    def setUp(self):
        super(TestL10nLuEcdf, self).setUp()

        self.ecdf_report = self.env['ecdf.report']
        self.res_company = self.env['res.company']
        self.account_fiscalyear = self.env['account.fiscalyear']

        # Company instance
        self.company = self.res_company.create({'name': 'eCDF Company'})

        # Current fiscal year instance
        self.current_fiscal_year = self.account_fiscalyear.create({
            'company_id': self.company.id,
            'name': 'current_fiscalyear',
            'code': '123456',
            'date_start': datetime.strptime('01012016', "%d%m%Y").date(),
            'date_stop': datetime.strptime('31122016', "%d%m%Y").date()})

        # Previous fiscal year instance
        self.previous_fiscal_year = self.account_fiscalyear.create({
            'company_id': self.company.id,
            'name': 'previous_fiscalyear',
            'code': '654321',
            'date_start': datetime.strptime('01012015', "%d%m%Y").date(),
            'date_stop': datetime.strptime('31122015', "%d%m%Y").date()})

        # eCDF report instance
        self.report = self.env['ecdf.report'].create({
            'language': 'FR',
            'target_move': 'posted',
            'with_pl': True,
            'with_bs': False,
            'with_ac': False,
            'reports_type': 'full',
            'current_fiscyear': self.current_fiscal_year.id,
            'prev_fiscyear': self.previous_fiscal_year.id,
            'remarks': "comment",
            'matricule': '1111111111111',
            'vat': 'LU12345678',
            'company_registry': 'L123456'})

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
        self.report.matricule = '11111111111'
        try:
            self.report.check_matr()
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
        self.report.company_registry = 'L123456'
        try:
            self.report.check_rcs()
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
        self.report.vat = 'LU12345678'
        try:
            self.report.check_vat()
        except ValidationError:
            self.fail()

    def test_compute_file_name(self):
        '''
        File name must match the following pattern : 000000XyyyymmddThhmmssNN
        '''
        # Regular expression of the expected file name
        exp = r"""^\d{6}X\d{8}T\d{8}$"""
        rexp = re.compile(exp, re.X)

        self.report._compute_file_name()

        self.assertIsNotNone(rexp.match(self.report.file_name))

    def test_compute_full_file_name(self):
        '''
        Full file name must be the computed file name with ".xml" at the end
        '''
        self.report._compute_full_file_name()
        expected = self.report.file_name + '.xml'
        self.assertEqual(self.report.full_file_name, expected)

    def test_get_ecdf_file_version(self):
        report_file_version = self.report.get_ecdf_file_version()
        file_version = '1.1'

        self.assertEqual(report_file_version, file_version)

    def test_get_interface(self):
        report_interface = self.report.get_interface()
        interface = 'COPL3'

        self.assertEquals(report_interface, interface)

    def test_append_num_field(self):
        # Initial data : code not in KEEP_ZERO
        ecdf = '123'
        comment = "A comment"

        # Test with valid float value
        element = etree.Element('FormData')
        val = 5.5
        self.report._append_num_field(element, ecdf, val, False, comment)
        expected = '<FormData><!--A comment--><NumericField id="123">\
5,50</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

        # Test with None value, code not in KEEP_ZERO
        element = etree.Element('FormData')
        val = None
        self.report._append_num_field(element, ecdf, val, False, comment)
        expected = '<FormData/>'
        self.assertEqual(etree.tostring(element), expected)

        # Test with AccountingNone value, code not in KEEP_ZERO
        element = etree.Element('FormData')
        val = AccountingNone
        self.report._append_num_field(element, ecdf, val, False, comment)
        expected = '<FormData/>'
        self.assertEqual(etree.tostring(element), expected)

        # Data : code in KEEP_ZERO
        ecdf = '639'

        # Test with None value, code in KEEP_ZERO
        element = etree.Element('FormData')
        val = None
        self.report._append_num_field(element, ecdf, val, False, comment)
        expected = '<FormData><!--A comment--><NumericField id="639">0,00\
</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

        # Test with AccountingNone value, code in KEEP_ZERO
        element = etree.Element('FormData')
        val = AccountingNone
        self.report._append_num_field(element, ecdf, val, False, comment)
        expected = '<FormData><!--A comment--><NumericField id="639">0,00\
</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

        # Test with None value, code not in KEEP_ZERO
        element = etree.Element('FormData')
        val = None
        self.report._append_num_field(element, ecdf, val, True, comment)
        expected = '<FormData><!--A comment--><NumericField id="639">0,00\
</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

        # Test with AccountingNone value, code not in KEEP_ZERO
        element = etree.Element('FormData')
        val = AccountingNone
        self.report._append_num_field(element, ecdf, val, True, comment)
        expected = '<FormData><!--A comment--><NumericField id="639">0,00\
</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

        # Test with valid float value
        element = etree.Element('FormData')
        val = 5.5
        self.report._append_num_field(element, ecdf, val, True, comment)
        expected = '<FormData><!--A comment--><NumericField id="639">0,00\
</NumericField></FormData>'
        self.assertEqual(etree.tostring(element), expected)

        # Test without comment
        element = etree.Element('FormData')
        val = 5.5
        self.report._append_num_field(element, ecdf, val, True)
        expected = '<FormData><NumericField id="639">0,00</NumericField>\
</FormData>'
        self.assertEqual(etree.tostring(element), expected)

    def test_append_fr_lines(self):
        data_current = {'content': [{
            'kpi_name': 'A. CHARGES',
            'kpi_technical_name': 'ecdf_642_641',
            'cols': [{'suffix': '\u20ac',
                      'prefix': False,
                      'period_id': None,
                      'drilldown': False,
                      'is_percentage': False,
                      'dp': 0,
                      'style': None,
                      'val': 123,
                      'val_r': '\u202f724\xa0747\xa0\u20ac',
                      'expr': 'ecdf_602_601 + ecdf_604_603'}]}]}

        data_previous = {'content': [{
            'kpi_name': 'A. CHARGES',
            'kpi_technical_name': 'ecdf_642_641',
            'cols': [{'suffix': '\u20ac',
                      'prefix': False,
                      'period_id': None,
                      'drilldown': False,
                      'is_percentage': False,
                      'dp': 0,
                      'style': None,
                      'val': 321,
                      'val_r': '\u202f724\xa0747\xa0\u20ac',
                      'expr': 'ecdf_602_601 + ecdf_604_603'}]}]}

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
