{
    'name': 'Club Job Offers',
    'version': '18.0.1.0.0',
    'summary': 'Job marketplace among club affiliates',
    'description': 'Affiliates post job offers and other affiliates apply or recommend candidates.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['club_core', 'mail'],
    'data': [
        'security/club_job_security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'views/club_job_category_views.xml',
        'views/club_job_offer_views.xml',
        'views/club_job_application_views.xml',
        'views/club_job_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
