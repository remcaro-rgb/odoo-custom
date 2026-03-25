import datetime
from datetime import timedelta

from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import UserError


@tagged('club_pqr', 'post_install', '-at_install')
class TestClubPqr(TransactionCase):

    def setUp(self):
        super().setUp()
        self.affiliate = self.env['club.affiliate'].create({
            'name': 'Test PQR Affiliate',
            'membership_type': 'individual',
        })
        self.category = self.env['club.pqr.category'].create({
            'name': 'Test Category',
            'sla_days': 10,
        })

    def _create_request(self, **kwargs):
        vals = {
            'affiliate_id': self.affiliate.id,
            'category_id': self.category.id,
            'request_type': 'petition',
            'subject': 'Test PQR Subject',
        }
        vals.update(kwargs)
        return self.env['club.pqr.request'].create(vals)

    # ---- Sequence -----------------------------------------------------------

    def test_sequence_auto_generated(self):
        """PQR number is auto-generated on create."""
        request = self._create_request()
        self.assertTrue(request.name.startswith('PQR-'))
        self.assertNotEqual(request.name, '/')

    def test_sequence_unique(self):
        """Each PQR request gets a unique sequence number."""
        r1 = self._create_request()
        r2 = self._create_request(subject='Second request')
        self.assertNotEqual(r1.name, r2.name)

    # ---- Submit action ------------------------------------------------------

    def test_submit_sets_submit_date(self):
        """Submitting a request sets submit_date to today."""
        request = self._create_request()
        self.assertEqual(request.status, 'draft')
        self.assertFalse(request.submit_date)

        request.action_submit()

        self.assertEqual(request.status, 'submitted')
        self.assertEqual(request.submit_date, datetime.date.today())

    def test_submit_computes_due_date(self):
        """Submitting a request computes due_date from SLA days."""
        request = self._create_request()
        request.action_submit()

        expected_due = datetime.date.today() + timedelta(days=10)
        self.assertEqual(request.due_date, expected_due)

    def test_submit_only_from_draft(self):
        """Cannot submit a request that is not in draft status."""
        request = self._create_request()
        request.action_submit()
        with self.assertRaises(UserError):
            request.action_submit()

    # ---- Resolve action -----------------------------------------------------

    def test_resolve_sets_resolution_date(self):
        """Resolving a request sets resolution_date to today."""
        request = self._create_request()
        request.action_submit()
        request.action_assign()
        self.assertEqual(request.status, 'in_progress')

        request.action_resolve()

        self.assertEqual(request.status, 'resolved')
        self.assertEqual(request.resolution_date, datetime.date.today())

    # ---- Full workflow transitions ------------------------------------------

    def test_full_workflow_draft_to_closed(self):
        """Full happy-path workflow: draft -> submitted -> in_progress -> resolved -> closed."""
        request = self._create_request()
        self.assertEqual(request.status, 'draft')

        request.action_submit()
        self.assertEqual(request.status, 'submitted')

        request.action_assign()
        self.assertEqual(request.status, 'in_progress')

        request.action_resolve()
        self.assertEqual(request.status, 'resolved')

        request.action_close()
        self.assertEqual(request.status, 'closed')

    def test_reject_from_submitted(self):
        """Can reject a submitted request."""
        request = self._create_request()
        request.action_submit()
        request.action_reject()
        self.assertEqual(request.status, 'rejected')

    def test_reject_from_in_progress(self):
        """Can reject an in-progress request."""
        request = self._create_request()
        request.action_submit()
        request.action_assign()
        request.action_reject()
        self.assertEqual(request.status, 'rejected')

    def test_cannot_reject_draft(self):
        """Cannot reject a draft request."""
        request = self._create_request()
        with self.assertRaises(UserError):
            request.action_reject()

    def test_cannot_assign_draft(self):
        """Cannot assign a draft request directly."""
        request = self._create_request()
        with self.assertRaises(UserError):
            request.action_assign()

    def test_cannot_resolve_submitted(self):
        """Cannot resolve a submitted request (must be in_progress)."""
        request = self._create_request()
        request.action_submit()
        with self.assertRaises(UserError):
            request.action_resolve()

    def test_cannot_close_in_progress(self):
        """Cannot close an in-progress request (must be resolved)."""
        request = self._create_request()
        request.action_submit()
        request.action_assign()
        with self.assertRaises(UserError):
            request.action_close()

    # ---- is_overdue computed field ------------------------------------------

    def test_is_overdue_true(self):
        """Request is overdue when today > due_date and status is active."""
        request = self._create_request()
        request.write({
            'status': 'in_progress',
            'submit_date': datetime.date.today() - timedelta(days=20),
        })
        # Force recompute
        request.invalidate_recordset()
        self.assertTrue(request.is_overdue)

    def test_is_overdue_false_when_resolved(self):
        """Request is NOT overdue when status is resolved, even if past due."""
        request = self._create_request()
        request.write({
            'status': 'resolved',
            'submit_date': datetime.date.today() - timedelta(days=20),
            'resolution_date': datetime.date.today(),
        })
        request.invalidate_recordset()
        self.assertFalse(request.is_overdue)

    def test_is_overdue_false_when_closed(self):
        """Request is NOT overdue when status is closed."""
        request = self._create_request()
        request.write({
            'status': 'closed',
            'submit_date': datetime.date.today() - timedelta(days=20),
            'resolution_date': datetime.date.today() - timedelta(days=5),
        })
        request.invalidate_recordset()
        self.assertFalse(request.is_overdue)

    def test_is_overdue_false_when_not_yet_due(self):
        """Request is NOT overdue when due_date is in the future."""
        request = self._create_request()
        request.action_submit()
        # submit_date = today, due_date = today + 10 days
        self.assertFalse(request.is_overdue)
