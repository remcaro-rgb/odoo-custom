from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo import fields


@tagged('club_news', 'post_install', '-at_install')
class TestClubNewsArticle(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Article = self.env['club.news.article']
        self.Category = self.env['club.news.category']
        self.Tag = self.env['club.news.tag']
        self.category = self.Category.create({'name': 'Test Category'})
        self.tag = self.Tag.create({'name': 'Test Tag'})

    def test_auto_sequence(self):
        """Article name is auto-assigned from sequence on creation."""
        article = self.Article.create({
            'title': 'Test Article',
            'content': '<p>Test content</p>',
        })
        self.assertTrue(
            article.name,
            'Article reference should be auto-assigned.',
        )
        self.assertTrue(
            article.name.startswith('NEWS-'),
            'Article reference should start with NEWS- prefix.',
        )

    def test_auto_sequence_increments(self):
        """Each article receives a unique sequential reference."""
        a1 = self.Article.create({
            'title': 'First', 'content': '<p>1</p>',
        })
        a2 = self.Article.create({
            'title': 'Second', 'content': '<p>2</p>',
        })
        self.assertNotEqual(
            a1.name, a2.name,
            'Two articles must have different reference numbers.',
        )

    def test_publish_sets_date(self):
        """Publishing an article sets publish_date to today."""
        article = self.Article.create({
            'title': 'Publish Me',
            'content': '<p>Body</p>',
        })
        self.assertEqual(article.status, 'draft')
        self.assertFalse(article.publish_date)
        article.action_publish()
        self.assertEqual(article.status, 'published')
        self.assertEqual(
            article.publish_date,
            fields.Date.context_today(article),
        )

    def test_archive_transition(self):
        """Published article can be archived."""
        article = self.Article.create({
            'title': 'Archive Me',
            'content': '<p>Body</p>',
        })
        article.action_publish()
        self.assertEqual(article.status, 'published')
        article.action_archive_article()
        self.assertEqual(article.status, 'archived')

    def test_draft_transition_from_archived(self):
        """Archived article can be reset to draft for re-editing."""
        article = self.Article.create({
            'title': 'Re-edit Me',
            'content': '<p>Body</p>',
        })
        article.action_publish()
        article.action_archive_article()
        self.assertEqual(article.status, 'archived')
        article.action_draft()
        self.assertEqual(article.status, 'draft')

    def test_featured_toggle(self):
        """Featured flag can be toggled."""
        article = self.Article.create({
            'title': 'Feature Me',
            'content': '<p>Body</p>',
        })
        self.assertFalse(article.is_featured)
        article.is_featured = True
        self.assertTrue(article.is_featured)
        article.is_featured = False
        self.assertFalse(article.is_featured)

    def test_default_status_is_draft(self):
        """New articles default to draft status."""
        article = self.Article.create({
            'title': 'New Article',
            'content': '<p>Body</p>',
        })
        self.assertEqual(article.status, 'draft')

    def test_default_author_is_current_user(self):
        """Author defaults to the current user."""
        article = self.Article.create({
            'title': 'Author Test',
            'content': '<p>Body</p>',
        })
        self.assertEqual(article.author_id, self.env.user)
