{
    'name': 'Club Affiliate Billing',
    'version': '18.0.1.0.0',
    'summary': 'Facturacion Masiva de Socios — Monthly batch invoicing for Cargo a Socio charges',
    'description': (
        'Monthly batch invoicing for all POS "Cargo a Socio" charges.\n'
        'Generates consolidated invoices per affiliate for all POS orders\n'
        'paid via Cargo a Socio during a billing period.'
    ),
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['club_core', 'club_pos', 'account', 'mail'],
    'data': [
        'security/club_affiliate_billing_security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/cron.xml',
        'views/club_affiliate_billing_run_views.xml',
        'views/club_affiliate_billing_invoice_views.xml',
        'views/club_affiliate_billing_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'auto_install': False,
}
