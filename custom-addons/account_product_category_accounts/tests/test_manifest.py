import ast
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged('-at_install', 'post_install')
class TestManifest(TransactionCase):
    def test_author_and_maintainers_are_set(self):
        with file_open(
            'account_product_category_accounts/__manifest__.py', 'r'
        ) as fh:
            manifest = ast.literal_eval(fh.read())
        assert manifest.get('author'), 'author must be set'
        maintainers = manifest.get('maintainers')
        self.assertIsInstance(maintainers, list)
        self.assertTrue(maintainers, 'maintainers list must not be empty')
