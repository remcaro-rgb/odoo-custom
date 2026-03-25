{
    'name': 'Club PQR',
    'version': '18.0.1.0.0',
    'summary': 'PQR — Petitions, Complaints & Claims for Club Affiliates',
    'description': 'Request/complaint/claim management (Peticiones, Quejas, Reclamos) for club affiliates.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['club_core', 'mail'],
    'data': [
        'security/club_pqr_security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'views/club_pqr_category_views.xml',
        'views/club_pqr_request_views.xml',
        'views/club_pqr_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
