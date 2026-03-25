{
    'name': 'Club Access Control',
    'version': '18.0.1.0.0',
    'summary': 'Unified access control — validate affiliates, employees, guests, '
               'event attendees, tournament participants, and suppliers at entry points',
    'description': 'Unified access control for the club: validates affiliates, family members, '
                   'employees, guests, event/tournament attendees, and suppliers at entry points '
                   'via membership card, ID documents, access cards, or vehicle plates.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': [
        'club_core',
        'club_guests',
        'club_affiliate_employees',
        'club_events',
        'club_tournaments',
        'mail',
    ],
    'data': [
        'security/club_access_security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'views/club_access_vehicle_views.xml',
        'views/club_access_checkpoint_views.xml',
        'views/club_access_supplier_views.xml',
        'views/club_access_entry_views.xml',
        'views/club_access_lookup_wizard_views.xml',
        'views/club_access_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
