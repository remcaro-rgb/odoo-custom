{
    'name': 'Club Lost & Found',
    'version': '18.0.1.0.0',
    'summary': 'Social Country Club — Lost & Found Item Management',
    'description': 'Track lost and found items within the club, match them, and manage claims.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['club_core', 'mail'],
    'data': [
        'security/club_lost_found_security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'views/club_lost_item_views.xml',
        'views/club_found_item_views.xml',
        'views/club_lost_found_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
