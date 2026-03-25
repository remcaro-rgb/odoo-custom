{
    'name': 'Club Affiliate Employees',
    'version': '18.0.1.0.0',
    'summary': 'Affiliate household staff — nannies, nurses, chauffeurs, etc. registered for club access',
    'description': 'Manage affiliate household employees with schedules, access cards, and entry logs.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['club_core'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/club_employee_type_views.xml',
        'views/club_affiliate_employee_views.xml',
        'views/club_affiliate_employee_access_log_views.xml',
        'views/club_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
