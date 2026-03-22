{
    'name': 'Aged Payable Report',
    'version': '18.0.1.0.0',
    'summary': 'Aged payable report with aging buckets and PDF export',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_aged_payable_views.xml',
        'report/account_aged_payable_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
