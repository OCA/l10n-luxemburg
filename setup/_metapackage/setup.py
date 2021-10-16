import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo8-addons-oca-l10n-luxemburg",
    description="Meta package for oca-l10n-luxemburg Odoo addons",
    version=version,
    install_requires=[
        'odoo8-addon-l10n_lu_ecdf',
        'odoo8-addon-l10n_lu_ext',
        'odoo8-addon-l10n_lu_fin_rep_details',
        'odoo8-addon-l10n_lu_mis_reports',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 8.0',
    ]
)
