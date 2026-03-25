{
    'name': 'Club News',
    'version': '18.0.1.0.0',
    'summary': 'Club news & announcements — articles, categories, publish/draft workflow',
    'description': 'Manage club news articles with categories, tags, featured/pinned flags, and publish lifecycle.',
    'category': 'Club Management',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['club_core', 'mail'],
    'data': [
        'security/club_news_security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'views/club_news_category_views.xml',
        'views/club_news_tag_views.xml',
        'views/club_news_article_views.xml',
        'views/club_news_menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
