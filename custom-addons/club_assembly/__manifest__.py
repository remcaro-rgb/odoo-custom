{
    'name': 'Club Assembly',
    'version': '18.0.1.0.0',
    'summary': 'Asamblea de Socios — schedule assemblies, voting, transcripts',
    'description': 'Schedule affiliate assemblies, manage members, send mass '
                   'invitations, define topics with voting, record votes, '
                   'generate transcripts and summaries.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['club_core', 'mail'],
    'data': [
        'security/club_assembly_security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/mail_template.xml',
        'views/club_assembly_views.xml',
        'views/club_assembly_topic_views.xml',
        'views/club_assembly_vote_views.xml',
        'views/club_assembly_attendance_views.xml',
        'views/club_assembly_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
