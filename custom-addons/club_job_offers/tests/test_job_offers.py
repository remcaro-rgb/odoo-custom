from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged('club_job_offers', 'post_install', '-at_install')
class TestClubJobOffers(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Offer = self.env['club.job.offer']
        self.Application = self.env['club.job.application']
        self.Category = self.env['club.job.category']
        self.affiliate = self.env['club.affiliate'].create({
            'name': 'Test Affiliate Jobs',
            'membership_type': 'individual',
        })
        self.category = self.Category.create({'name': 'Test Category'})

    def test_auto_sequence(self):
        """Job offer gets auto-sequence JOB-XXXXX on creation."""
        offer = self.Offer.create({
            'title': 'Test Job',
            'affiliate_id': self.affiliate.id,
            'category_id': self.category.id,
        })
        self.assertTrue(offer.name, 'Offer name should be auto-assigned.')
        self.assertTrue(
            offer.name.startswith('JOB-'),
            'Offer name should start with JOB- prefix.',
        )

    def test_publish_sets_date(self):
        """Publishing an offer sets the publish_date to today."""
        offer = self.Offer.create({
            'title': 'Publish Test',
            'affiliate_id': self.affiliate.id,
        })
        self.assertEqual(offer.status, 'draft')
        self.assertFalse(offer.publish_date)
        offer.action_publish()
        self.assertEqual(offer.status, 'published')
        self.assertTrue(
            offer.publish_date,
            'Publish date should be set after publishing.',
        )

    def test_status_transitions(self):
        """Status transitions draft -> published -> filled and any -> closed."""
        offer = self.Offer.create({
            'title': 'Transition Test',
            'affiliate_id': self.affiliate.id,
        })
        self.assertEqual(offer.status, 'draft')

        offer.action_publish()
        self.assertEqual(offer.status, 'published')

        offer.action_fill()
        self.assertEqual(offer.status, 'filled')

        offer.action_close()
        self.assertEqual(offer.status, 'closed')

    def test_close_from_draft(self):
        """Closing from draft status works."""
        offer = self.Offer.create({
            'title': 'Close Draft Test',
            'affiliate_id': self.affiliate.id,
        })
        offer.action_close()
        self.assertEqual(offer.status, 'closed')

    def test_application_count_computed(self):
        """Application count is correctly computed."""
        offer = self.Offer.create({
            'title': 'Count Test',
            'affiliate_id': self.affiliate.id,
        })
        self.assertEqual(offer.application_count, 0)

        self.Application.create({
            'offer_id': offer.id,
            'applicant_name': 'Applicant One',
        })
        self.Application.create({
            'offer_id': offer.id,
            'applicant_name': 'Applicant Two',
        })
        offer.invalidate_recordset()
        self.assertEqual(
            offer.application_count, 2,
            'Application count should equal number of applications.',
        )

    def test_application_default_status(self):
        """New application defaults to submitted status with today date."""
        offer = self.Offer.create({
            'title': 'Default Status Test',
            'affiliate_id': self.affiliate.id,
        })
        application = self.Application.create({
            'offer_id': offer.id,
            'applicant_name': 'Default Test',
        })
        self.assertEqual(application.status, 'submitted')
        self.assertTrue(application.submit_date)
