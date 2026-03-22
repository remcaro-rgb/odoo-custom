{
    'name': 'General Ledger Report',
    'version': '18.0.1.0.0',
    'summary': 'General ledger with running balance per account and PDF export',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_general_ledger_views.xml',
        'report/account_general_ledger_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
