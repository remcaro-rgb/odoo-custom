{
    'name': 'Cash Flow Statement',
    'version': '18.0.1.0.0',
    'summary': 'Cash flow statement - direct method with PDF export',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_cash_flow_views.xml',
        'report/account_cash_flow_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
