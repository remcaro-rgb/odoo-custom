{
    'name': 'Aged Receivable Report',
    'version': '18.0.1.0.0',
    'summary': 'Aged receivable report with aging buckets and PDF export',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_aged_receivable_views.xml',
        'report/account_aged_receivable_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
