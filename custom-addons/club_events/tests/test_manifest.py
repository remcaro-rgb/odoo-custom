import ast

from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged('-at_install', 'post_install')
class TestManifest(TransactionCase):
    def test_maintainers_is_a_non_empty_list(self):
        with file_open('club_events/__manifest__.py', 'r') as fh:
            manifest = ast.literal_eval(fh.read())
        maintainers = manifest.get('maintainers')
        self.assertIsInstance(maintainers, list)
        self.assertTrue(maintainers, 'maintainers list must not be empty')
