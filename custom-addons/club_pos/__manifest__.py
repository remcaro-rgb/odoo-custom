{
    'name': 'Club POS',
    'version': '18.0.1.0.0',
    'summary': 'POS integration for Club - Cargo a Socio payment, affiliate search, signed receipts',
    'description': (
        'Point of Sale integration for social country club management.\n'
        'Adds "Cargo a Socio" payment method that charges affiliate member accounts,\n'
        'affiliate customer search in POS, and signed receipt capture.'
    ),
    'category': 'Point of Sale',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'club_core'],
    'data': [
        'views/pos_payment_method_views.xml',
        'views/pos_order_views.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'club_pos/static/src/js/club_pos.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
