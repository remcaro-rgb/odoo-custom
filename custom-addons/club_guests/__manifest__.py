{
    'name': 'Club Guests',
    'version': '18.0.1.0.0',
    'summary': 'Affiliate guest management — registration, visit tracking, access control',
    'description': 'Guest management for social country club: guest registration, visit tracking, '
                   'check-in/check-out, policy enforcement, and guest limits per affiliate.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['club_core', 'mail'],
    'data': [
        'security/club_guests_security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/mail_template.xml',
        'views/club_guest_policy_views.xml',
        'views/club_guest_views.xml',
        'views/club_guest_visit_views.xml',
        'views/club_guests_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
