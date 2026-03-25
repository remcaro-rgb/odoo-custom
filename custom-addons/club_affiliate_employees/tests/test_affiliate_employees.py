from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged('club_affiliate_employees', 'post_install', '-at_install')
class TestClubAffiliateEmployees(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Affiliate = cls.env['club.affiliate']
        cls.EmployeeType = cls.env['club.employee.type']
        cls.Employee = cls.env['club.affiliate.employee']
        cls.Schedule = cls.env['club.affiliate.employee.schedule']
        cls.AccessLog = cls.env['club.affiliate.employee.access.log']

        cls.affiliate = cls.Affiliate.create({
            'name': 'Test Affiliate',
            'membership_type': 'individual',
        })

        cls.emp_type_nanny = cls.EmployeeType.create({'name': 'Nanny'})
        cls.emp_type_chauffeur = cls.EmployeeType.create({'name': 'Chauffeur'})

    def test_employee_creation(self):
        """Employee is created with correct default status."""
        employee = self.Employee.create({
            'name': 'Maria Test',
            'affiliate_id': self.affiliate.id,
            'employee_type_id': self.emp_type_nanny.id,
            'identification_number': '12345678',
        })
        self.assertEqual(employee.status, 'active')
        self.assertEqual(employee.affiliate_id, self.affiliate)
        self.assertEqual(employee.employee_type_id, self.emp_type_nanny)
        self.assertEqual(employee.identification_number, '12345678')

    def test_access_card_uniqueness(self):
        """Two employees cannot share the same access card number."""
        self.Employee.create({
            'name': 'Employee A',
            'affiliate_id': self.affiliate.id,
            'employee_type_id': self.emp_type_nanny.id,
            'identification_number': '11111111',
            'access_card_number': 'CARD-001',
        })
        with self.assertRaises(Exception):
            self.Employee.create({
                'name': 'Employee B',
                'affiliate_id': self.affiliate.id,
                'employee_type_id': self.emp_type_chauffeur.id,
                'identification_number': '22222222',
                'access_card_number': 'CARD-001',
            })

    def test_identification_number_required(self):
        """Employee cannot be created with empty identification number."""
        with self.assertRaises(ValidationError):
            self.Employee.create({
                'name': 'No ID Employee',
                'affiliate_id': self.affiliate.id,
                'employee_type_id': self.emp_type_nanny.id,
                'identification_number': '   ',
            })

    def test_schedule_creation(self):
        """Schedule lines can be created for an employee."""
        employee = self.Employee.create({
            'name': 'Schedule Test',
            'affiliate_id': self.affiliate.id,
            'employee_type_id': self.emp_type_nanny.id,
            'identification_number': '33333333',
        })
        schedule = self.Schedule.create({
            'employee_id': employee.id,
            'day_of_week': '0',
            'time_from': 8.0,
            'time_to': 17.0,
            'notes': 'Monday shift',
        })
        self.assertEqual(schedule.employee_id, employee)
        self.assertEqual(schedule.day_of_week, '0')
        self.assertAlmostEqual(schedule.time_from, 8.0)
        self.assertAlmostEqual(schedule.time_to, 17.0)
        self.assertIn(schedule, employee.schedule_ids)

    def test_access_log_creation(self):
        """Access log entries can be created with default date."""
        employee = self.Employee.create({
            'name': 'Log Test',
            'affiliate_id': self.affiliate.id,
            'employee_type_id': self.emp_type_chauffeur.id,
            'identification_number': '44444444',
        })
        log = self.AccessLog.create({
            'employee_id': employee.id,
            'check_in': 8.0,
            'check_out': 17.0,
            'area': 'Main Entrance',
        })
        self.assertTrue(log.date)
        self.assertEqual(log.employee_id, employee)
        self.assertAlmostEqual(log.check_in, 8.0)
        self.assertAlmostEqual(log.check_out, 17.0)
        self.assertEqual(log.area, 'Main Entrance')

    def test_status_transitions(self):
        """Employee status can be changed between active, suspended, inactive."""
        employee = self.Employee.create({
            'name': 'Status Test',
            'affiliate_id': self.affiliate.id,
            'employee_type_id': self.emp_type_nanny.id,
            'identification_number': '55555555',
        })
        self.assertEqual(employee.status, 'active')

        employee.write({'status': 'suspended'})
        self.assertEqual(employee.status, 'suspended')

        employee.write({'status': 'inactive'})
        self.assertEqual(employee.status, 'inactive')

        employee.write({'status': 'active'})
        self.assertEqual(employee.status, 'active')
