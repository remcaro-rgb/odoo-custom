{
    'name': 'Club FAQ',
    'version': '19.0.1.0.0',
    'summary': 'FAQ system with multilanguage support for the Club',
    'description': 'FAQ system with categories, Q&A, ordering, and EN/ES multilanguage support.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'maintainers': ['Manuel Caro'],
    'license': 'LGPL-3',
    'depends': ['club_core'],
    'data': [
        'security/club_faq_security.xml',
        'security/ir.model.access.csv',
        'views/club_faq_category_views.xml',
        'views/club_faq_item_views.xml',
        'views/club_faq_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
