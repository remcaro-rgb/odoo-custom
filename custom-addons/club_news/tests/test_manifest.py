import ast
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged('-at_install', 'post_install')
class TestManifest(TransactionCase):
    def test_website_is_set(self):
        with file_open('club_news/__manifest__.py', 'r') as fh:
            manifest = ast.literal_eval(fh.read())
        url = manifest.get('website', '')
        self.assertTrue(url, 'club_news manifest must declare a website URL')
        self.assertTrue(url.startswith('https://'),
                        'website URL must be https://')
