from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import UserError


@tagged('club_lost_found', 'post_install', '-at_install')
class TestLostFound(TransactionCase):

    def setUp(self):
        super().setUp()
        self.LostItem = self.env['club.lost.item']
        self.FoundItem = self.env['club.found.item']
        self.Affiliate = self.env['club.affiliate']

        self.affiliate_1 = self.Affiliate.create({
            'name': 'Test Reporter',
            'membership_type': 'individual',
        })
        self.affiliate_2 = self.Affiliate.create({
            'name': 'Test Claimer',
            'membership_type': 'individual',
        })

    # ── Auto-sequence tests ─────────────────────────────────────

    def test_lost_item_auto_sequence(self):
        """Lost item name is auto-assigned from sequence on creation."""
        lost = self.LostItem.create({
            'reporter_id': self.affiliate_1.id,
            'description': 'A lost wallet',
            'category': 'other',
        })
        self.assertTrue(
            lost.name,
            'Lost item name should be auto-assigned.',
        )
        self.assertTrue(
            lost.name.startswith('LOST-'),
            'Lost item name should start with LOST- prefix.',
        )

    def test_found_item_auto_sequence(self):
        """Found item name is auto-assigned from sequence on creation."""
        found = self.FoundItem.create({
            'description': 'A found wallet',
            'category': 'other',
        })
        self.assertTrue(
            found.name,
            'Found item name should be auto-assigned.',
        )
        self.assertTrue(
            found.name.startswith('FOUND-'),
            'Found item name should start with FOUND- prefix.',
        )

    def test_sequence_uniqueness(self):
        """Each item gets a unique sequence number."""
        lost_1 = self.LostItem.create({
            'reporter_id': self.affiliate_1.id,
            'description': 'Item 1',
            'category': 'electronics',
        })
        lost_2 = self.LostItem.create({
            'reporter_id': self.affiliate_1.id,
            'description': 'Item 2',
            'category': 'electronics',
        })
        self.assertNotEqual(
            lost_1.name,
            lost_2.name,
            'Two lost items must have different sequence numbers.',
        )

    # ── Match action tests ──────────────────────────────────────

    def test_match_action_links_items(self):
        """Match action links lost and found items correctly."""
        lost = self.LostItem.create({
            'reporter_id': self.affiliate_1.id,
            'description': 'Gold ring',
            'category': 'jewelry',
        })
        found = self.FoundItem.create({
            'description': 'Gold ring found near pool',
            'category': 'jewelry',
        })
        lost.action_match(found.id)
        self.assertEqual(lost.matched_found_id, found)
        self.assertEqual(lost.status, 'matched')
        self.assertEqual(found.status, 'matched')

    def test_match_only_reported_lost_item(self):
        """Cannot match a lost item that is not in 'reported' status."""
        lost = self.LostItem.create({
            'reporter_id': self.affiliate_1.id,
            'description': 'Already closed item',
            'category': 'other',
            'status': 'closed',
        })
        found = self.FoundItem.create({
            'description': 'Some item',
            'category': 'other',
        })
        with self.assertRaises(UserError):
            lost.action_match(found.id)

    def test_match_only_registered_found_item(self):
        """Cannot match to a found item that is not in 'registered' status."""
        lost = self.LostItem.create({
            'reporter_id': self.affiliate_1.id,
            'description': 'Some item',
            'category': 'other',
        })
        found = self.FoundItem.create({
            'description': 'Already disposed item',
            'category': 'other',
            'status': 'disposed',
        })
        with self.assertRaises(UserError):
            lost.action_match(found.id)

    # ── Claim action tests ──────────────────────────────────────

    def test_claim_action_sets_fields(self):
        """Claim action sets claimed_by_id, claim_date, and status."""
        found = self.FoundItem.create({
            'description': 'Found phone',
            'category': 'electronics',
        })
        found.action_claim(affiliate_id=self.affiliate_2.id)
        self.assertEqual(found.status, 'claimed')
        self.assertEqual(found.claimed_by_id, self.affiliate_2)
        self.assertTrue(
            found.claim_date,
            'Claim date should be set after claim action.',
        )

    def test_claim_without_affiliate(self):
        """Claim action works even without specifying an affiliate."""
        found = self.FoundItem.create({
            'description': 'Found hat',
            'category': 'clothing',
        })
        found.action_claim()
        self.assertEqual(found.status, 'claimed')
        self.assertTrue(found.claim_date)

    def test_claim_matched_item(self):
        """Matched found items can also be claimed."""
        found = self.FoundItem.create({
            'description': 'Matched keys',
            'category': 'other',
            'status': 'matched',
        })
        found.action_claim(affiliate_id=self.affiliate_2.id)
        self.assertEqual(found.status, 'claimed')

    def test_cannot_claim_disposed_item(self):
        """Cannot claim a disposed found item."""
        found = self.FoundItem.create({
            'description': 'Old item',
            'category': 'other',
            'status': 'disposed',
        })
        with self.assertRaises(UserError):
            found.action_claim(affiliate_id=self.affiliate_2.id)

    # ── Dispose action tests ────────────────────────────────────

    def test_dispose_action(self):
        """Dispose action sets status to 'disposed'."""
        found = self.FoundItem.create({
            'description': 'Unclaimed jacket',
            'category': 'clothing',
        })
        found.action_dispose()
        self.assertEqual(found.status, 'disposed')

    def test_cannot_dispose_claimed_item(self):
        """Cannot dispose an already claimed item."""
        found = self.FoundItem.create({
            'description': 'Claimed item',
            'category': 'other',
            'status': 'claimed',
        })
        with self.assertRaises(UserError):
            found.action_dispose()

    # ── Status transition tests ─────────────────────────────────

    def test_lost_item_default_status(self):
        """Lost item defaults to 'reported' status."""
        lost = self.LostItem.create({
            'reporter_id': self.affiliate_1.id,
            'description': 'New lost item',
            'category': 'other',
        })
        self.assertEqual(lost.status, 'reported')

    def test_found_item_default_status(self):
        """Found item defaults to 'registered' status."""
        found = self.FoundItem.create({
            'description': 'New found item',
            'category': 'other',
        })
        self.assertEqual(found.status, 'registered')

    def test_lost_item_close(self):
        """Close action sets lost item status to 'closed'."""
        lost = self.LostItem.create({
            'reporter_id': self.affiliate_1.id,
            'description': 'Item to close',
            'category': 'other',
        })
        lost.action_close()
        self.assertEqual(lost.status, 'closed')
