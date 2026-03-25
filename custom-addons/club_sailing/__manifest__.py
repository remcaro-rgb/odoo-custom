{
    'name': 'Club Sailing',
    'version': '18.0.1.0.0',
    'summary': 'Social Country Club — Sailing Management',
    'description': 'Sailing module: boats, docks, bookings, crew.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['club_core'],
    'data': [
        'security/club_sailing_security.xml',
        'security/ir.model.access.csv',
        'views/club_sailing_boat_views.xml',
        'views/club_sailing_dock_views.xml',
        'views/club_sailing_booking_views.xml',
        'views/club_sailing_crew_views.xml',
        'views/club_sailing_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
