from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('club_faq', 'post_install', '-at_install')
class TestClubFaq(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Category = self.env['club.faq.category']
        self.FaqItem = self.env['club.faq.item']

        self.cat_memberships = self.Category.create({
            'name': 'Memberships',
            'sequence': 10,
        })
        self.cat_billing = self.Category.create({
            'name': 'Billing',
            'sequence': 20,
        })

    def test_category_faq_count_computed(self):
        """Category faq_count reflects the number of linked FAQ items."""
        self.assertEqual(self.cat_memberships.faq_count, 0)

        self.FaqItem.create({
            'category_id': self.cat_memberships.id,
            'question': 'How do I join?',
            'answer': '<p>Visit our office.</p>',
        })
        self.cat_memberships.invalidate_recordset()
        self.assertEqual(self.cat_memberships.faq_count, 1)

        self.FaqItem.create({
            'category_id': self.cat_memberships.id,
            'question': 'What are the plans?',
            'answer': '<p>Individual, Family, Corporate.</p>',
        })
        self.cat_memberships.invalidate_recordset()
        self.assertEqual(self.cat_memberships.faq_count, 2)

    def test_publish_unpublish_toggle(self):
        """FAQ item can be published and unpublished."""
        item = self.FaqItem.create({
            'category_id': self.cat_memberships.id,
            'question': 'Is this published?',
            'answer': '<p>Yes by default.</p>',
        })
        self.assertTrue(item.is_published, 'FAQ item should be published by default.')

        item.is_published = False
        self.assertFalse(item.is_published, 'FAQ item should be unpublished after toggle.')

        item.is_published = True
        self.assertTrue(item.is_published, 'FAQ item should be published again.')

    def test_sequence_ordering(self):
        """FAQ items are ordered by sequence within a category."""
        item_c = self.FaqItem.create({
            'category_id': self.cat_memberships.id,
            'question': 'Third question',
            'answer': '<p>C</p>',
            'sequence': 30,
        })
        item_a = self.FaqItem.create({
            'category_id': self.cat_memberships.id,
            'question': 'First question',
            'answer': '<p>A</p>',
            'sequence': 10,
        })
        item_b = self.FaqItem.create({
            'category_id': self.cat_memberships.id,
            'question': 'Second question',
            'answer': '<p>B</p>',
            'sequence': 20,
        })

        ordered = self.FaqItem.search([
            ('category_id', '=', self.cat_memberships.id),
        ])
        self.assertEqual(
            ordered.ids,
            [item_a.id, item_b.id, item_c.id],
            'FAQ items must be ordered by sequence ascending.',
        )

    def test_translate_fields_are_translatable(self):
        """Translatable fields on category and item have translate=True."""
        cat_name_field = self.Category._fields['name']
        self.assertTrue(
            cat_name_field.translate,
            'Category name field must be translatable.',
        )

        question_field = self.FaqItem._fields['question']
        self.assertTrue(
            question_field.translate,
            'FAQ item question field must be translatable.',
        )

        answer_field = self.FaqItem._fields['answer']
        self.assertTrue(
            answer_field.translate,
            'FAQ item answer field must be translatable.',
        )

    def test_category_faq_count_after_delete(self):
        """Category faq_count decreases when an FAQ item is deleted."""
        item = self.FaqItem.create({
            'category_id': self.cat_billing.id,
            'question': 'Payment methods?',
            'answer': '<p>Cash, card, transfer.</p>',
        })
        self.cat_billing.invalidate_recordset()
        self.assertEqual(self.cat_billing.faq_count, 1)

        item.unlink()
        self.cat_billing.invalidate_recordset()
        self.assertEqual(self.cat_billing.faq_count, 0)

    def test_default_values(self):
        """FAQ item defaults: is_published=True, helpful_count=0, sequence=10."""
        item = self.FaqItem.create({
            'category_id': self.cat_memberships.id,
            'question': 'Defaults test',
            'answer': '<p>Testing defaults.</p>',
        })
        self.assertTrue(item.is_published)
        self.assertEqual(item.helpful_count, 0)
        self.assertEqual(item.sequence, 10)

    def test_author_defaults_to_current_user(self):
        """FAQ item author defaults to the current user."""
        item = self.FaqItem.create({
            'category_id': self.cat_memberships.id,
            'question': 'Who wrote this?',
            'answer': '<p>The current user.</p>',
        })
        self.assertEqual(
            item.author_id, self.env.user,
            'Author should default to the current user.',
        )
