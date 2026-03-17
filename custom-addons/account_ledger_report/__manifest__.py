{
    'name': 'Account Ledger Report',
    'version': '18.0.1.0.0',
    'summary': 'Live account ledger report with PDF and Excel export',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_ledger_report_views.xml',
        'report/account_ledger_report_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
