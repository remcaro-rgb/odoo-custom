{
    'name': 'Club Events',
    'version': '18.0.1.0.0',
    'summary': 'Social Country Club — Event Management',
    'description': 'Club events module: internal/external events, member pricing, registration with affiliate linking.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['club_core', 'event', 'website_event', 'payment'],
    'data': [
        'security/club_events_security.xml',
        'security/ir.model.access.csv',
        'views/club_event_views.xml',
        'views/club_event_registration_views.xml',
        'views/club_events_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
