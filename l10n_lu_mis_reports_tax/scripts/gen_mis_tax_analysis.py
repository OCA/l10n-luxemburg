#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2017 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# pylint: disable=line-too-long

import csv
import os
from os.path import join as opj
import re


SECTIONS = (
    # Vente
    ('VB_PA', 'Vente - Biens - Pays'),
    ('VB_IC', 'Vente - Biens - Intracom'),
    ('VB_EC', 'Vente - Biens - Extracom'),
    ('VB_TR', 'Vente - Biens - Triangulaire'),
    ('VP_PA', 'Vente - Prestations - Pays'),
    ('VP_IC', 'Vente - Prestations - Intracom'),
    ('VP_EC', 'Vente - Prestations - Extracom'),
    # Achat
    ('AB_PA', 'Achat - Biens - Pays'),
    ('AB_IC', 'Achat - Biens - Intracom'),
    ('AB_EC', 'Achat - Biens - Extracom'),
    ('AB_ECP', 'Achat - Biens - Extracom - Fin privée'),
    ('AP_PA', 'Achat - Prestations - Pays'),
    ('AP_IC', 'Achat - Prestations - Intracom'),
    ('AP_EC', 'Achat - Prestations - Extracom'),
    # Frais
    ('FB_PA', 'Frais - Biens - Pays'),
    ('FB_IC', 'Frais - Biens - Intracom'),
    ('FB_EC', 'Frais - Biens - Extracom'),
    ('FB_ECP', 'Frais - Biens - Extracom - Fin privée'),
    ('FP_PA', 'Frais - Prestations - Pays'),
    ('FP_IC', 'Frais - Prestations - Intracom'),
    ('FP_EC', 'Frais - Prestations - Extracom'),
    # Invest
    ('IB_PA', 'Invest - Biens - Pays'),
    ('IB_IC', 'Invest - Biens - Intracom'),
    ('IB_EC', 'Invest - Biens - Extracom'),
    ('IB_ECP', 'Invest - Biens - Extracom - Fin privée'),
    ('IP_PA', 'Invest - Prestations - Pays'),
    ('IP_IC', 'Invest - Prestations - Intracom'),
    ('IP_EC', 'Invest - Prestations - Extracom'),
)

EXPRESSIONS = (
    ('base_deb', 'Base Deb',
     "deb[][('tax_ids.tag_ids', '=', ref('{tag_id}').id)]"),
    ('base_crd', 'Base Crd',
     "crd[][('tax_ids.tag_ids', '=', ref('{tag_id}').id)]"),
    ('base_bal', 'Base Bal',
     "bal[][('tax_ids.tag_ids', '=', ref('{tag_id}').id)]"),
    ('deb_bal', 'Tax Deb',
     "deb[][('tax_line_id.tag_ids', '=', ref('{tag_id}').id)]"),
    ('crd_bal', 'Tax Crd',
     "crd[][('tax_line_id.tag_ids', '=', ref('{tag_id}').id)]"),
    ('tax_bal', 'Tax Bal',
     "bal[][('tax_line_id.tag_ids', '=', ref('{tag_id}').id)]"),
)


def sorted_nicely(l):
    """ Sort the given iterable in the way that humans expect."""
    def convert(text):
        return int(text) if text.isdigit() else text

    def alphanum_key(key):
        return [convert(c) for c in re.split('([0-9]+)', key)]

    return sorted(l, key=alphanum_key)


print("""<?xml version="1.0" encoding="utf-8"?>
<!-- Copyright 2017 ACSONE SA/NV
     License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl). -->
<odoo>""")
print("""
    <record id="mis_tax_analysis" model="mis.report">
        <field name="name">Luxembourg Tax Analysis</field>
        <field name="style_id" ref="mis_report_style_l10n_lu_base_hide_empty"/>
    </record>
""")
for sk_seq, (sk, sk_descr, _) in enumerate(EXPRESSIONS):
    print("""
        <record id="mis_tax_analysis_sk_{sk}" model="mis.report.subkpi">
            <field name="report_id" ref="mis_tax_analysis"/>
            <field name="sequence">{sk_seq}</field>
            <field name="name">{sk}</field>
            <field name="description">{sk_descr}</field>
        </record>
    """.format(**locals()))

data_dir = opj(os.path.dirname(__file__), '..', 'data')
reader = csv.reader(open(opj(data_dir, 'account.account.tag-2015.csv')))
next(reader)
all_tags = {tag_id: tag_name for tag_id, tag_name, _ in reader}
tags_done = set()

for section_seq, (section_code, section_name) in enumerate(SECTIONS):
    section_seq *= 100
    tag_ids_for_section = []
    for tag_id in all_tags:
        if tag_id.startswith('l10n_lu.tag_' + section_code + '_') or \
                tag_id == 'l10n_lu.tag_' + section_code:
            tag_ids_for_section.append(tag_id)
    tag_ids_for_section = sorted_nicely(tag_ids_for_section)
    for tag_seq, tag_id in enumerate(reversed(tag_ids_for_section)):
        short_tag_id = tag_id[8:]
        tag_seq = section_seq + tag_seq + 1
        tag_name = all_tags[tag_id]
        # print(section_name, all_tags[tag_id])
        print("""
        <record id="mis_tax_analysis_kpi_{short_tag_id}" model="mis.report.kpi">
            <field name="report_id" ref="mis_tax_analysis"/>
            <field name="name">{short_tag_id}</field>
            <field name="description">{tag_name}</field>
            <field name="sequence">{tag_seq}</field>
            <field name="multi" eval="True"/>
            <field name="style_id" ref="mis_report_style_l10n_lu_3"/>
            <field name="auto_expand_accounts" eval="True"/>
            <field name="auto_expand_accounts_style_id" ref="mis_report_style_l10n_lu_4"/>
        </record>
        """.format(**locals()))  # noqa: E501
        for sk, _, expr in EXPRESSIONS:
            expr = expr.format(**locals())
            print("""
            <record id="mis_tax_analysis_kpi_{short_tag_id}_{sk}" model="mis.report.kpi.expression">
                <field name="kpi_id" ref="mis_tax_analysis_kpi_{short_tag_id}"/>
                <field name="subkpi_id" ref="mis_tax_analysis_sk_{sk}"/>
                <field name="name">{expr}</field>
            </record>
            """.format(**locals()))  # noqa: E501
    sumexpr = ' + '.join(t[8:] for t in tag_ids_for_section)
    print("""
    <record id="mis_tax_analysis_kpi_{section_code}" model="mis.report.kpi">
        <field name="report_id" ref="mis_tax_analysis"/>
        <field name="name">{section_code}</field>
        <field name="description">{section_name}</field>
        <field name="sequence">{section_seq}</field>
        <field name="multi" eval="False"/>
        <field name="expression">{sumexpr}</field>
        <field name="style_id" ref="mis_report_style_l10n_lu_2"/>
    </record>
    """.format(**locals()))

print("""</odoo>""")
