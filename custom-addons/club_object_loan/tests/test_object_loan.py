from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError
from datetime import timedelta


@tagged('club_object_loan', 'post_install', '-at_install')
class TestObjectLoan(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Category = self.env['club.object.category']
        self.Item = self.env['club.object.item']
        self.Loan = self.env['club.object.loan']
        self.Affiliate = self.env['club.affiliate']

        self.category = self.Category.create({
            'name': 'Test Category',
            'max_loan_days': 7,
        })
        self.item = self.Item.create({
            'name': 'Test Item',
            'category_id': self.category.id,
            'status': 'available',
            'quantity_total': 3,
        })
        self.affiliate = self.Affiliate.create({
            'name': 'Test Borrower',
            'membership_type': 'individual',
        })

    def test_loan_auto_sequence(self):
        """Loan name is auto-assigned from sequence on creation."""
        loan = self.Loan.create({
            'item_id': self.item.id,
            'affiliate_id': self.affiliate.id,
            'quantity': 1,
        })
        self.assertTrue(
            loan.name,
            'Loan name should be auto-assigned.',
        )
        self.assertTrue(
            loan.name.startswith('LOAN-'),
            'Loan name should start with LOAN- prefix.',
        )

    def test_return_action(self):
        """Return action sets return_date and status to returned."""
        loan = self.Loan.create({
            'item_id': self.item.id,
            'affiliate_id': self.affiliate.id,
            'quantity': 1,
        })
        self.assertEqual(loan.status, 'active')
        loan.action_return()
        self.assertEqual(loan.status, 'returned')
        self.assertTrue(
            loan.return_date,
            'Return date should be set after return action.',
        )

    def test_quantity_constraint(self):
        """Cannot loan more than available quantity."""
        self.Loan.create({
            'item_id': self.item.id,
            'affiliate_id': self.affiliate.id,
            'quantity': 3,
        })
        with self.assertRaises(ValidationError):
            self.Loan.create({
                'item_id': self.item.id,
                'affiliate_id': self.affiliate.id,
                'quantity': 1,
            })

    def test_item_availability_computed(self):
        """Item quantity_available decreases with active loans."""
        self.assertEqual(self.item.quantity_available, 3)
        loan = self.Loan.create({
            'item_id': self.item.id,
            'affiliate_id': self.affiliate.id,
            'quantity': 2,
        })
        self.item.invalidate_recordset()
        self.assertEqual(self.item.quantity_available, 1)
        loan.action_return()
        self.item.invalidate_recordset()
        self.assertEqual(self.item.quantity_available, 3)

    def test_maintenance_item_cannot_be_loaned(self):
        """Item in maintenance status cannot be loaned."""
        self.item.status = 'maintenance'
        with self.assertRaises(ValidationError):
            self.Loan.create({
                'item_id': self.item.id,
                'affiliate_id': self.affiliate.id,
                'quantity': 1,
            })

    def test_retired_item_cannot_be_loaned(self):
        """Item in retired status cannot be loaned."""
        self.item.status = 'retired'
        with self.assertRaises(ValidationError):
            self.Loan.create({
                'item_id': self.item.id,
                'affiliate_id': self.affiliate.id,
                'quantity': 1,
            })

    def test_due_date_computed(self):
        """Due date is computed from loan_date + category max_loan_days."""
        loan = self.Loan.create({
            'item_id': self.item.id,
            'affiliate_id': self.affiliate.id,
            'quantity': 1,
        })
        expected_due = loan.loan_date + timedelta(days=self.category.max_loan_days)
        self.assertEqual(loan.due_date, expected_due)

    def test_mark_lost(self):
        """Mark lost action sets status to lost."""
        loan = self.Loan.create({
            'item_id': self.item.id,
            'affiliate_id': self.affiliate.id,
            'quantity': 1,
        })
        loan.action_mark_lost()
        self.assertEqual(loan.status, 'lost')

    def test_item_code_auto_sequence(self):
        """Item code is auto-assigned from sequence on creation."""
        self.assertTrue(
            self.item.code,
            'Item code should be auto-assigned.',
        )
        self.assertTrue(
            self.item.code.startswith('ITEM-'),
            'Item code should start with ITEM- prefix.',
        )
