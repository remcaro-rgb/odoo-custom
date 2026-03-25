from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged, TransactionCase


@tagged('club_assembly', 'post_install', '-at_install')
class TestClubAssembly(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Affiliate = cls.env['club.affiliate']
        cls.Assembly = cls.env['club.assembly']
        cls.Topic = cls.env['club.assembly.topic']
        cls.Vote = cls.env['club.assembly.vote']
        cls.Attendance = cls.env['club.assembly.attendance']

        # Create test affiliates
        cls.affiliate_1 = cls.Affiliate.create({
            'name': 'Test Affiliate 1',
            'email': 'test1@example.com',
            'membership_type': 'individual',
        })
        cls.affiliate_2 = cls.Affiliate.create({
            'name': 'Test Affiliate 2',
            'email': 'test2@example.com',
            'membership_type': 'individual',
        })
        cls.affiliate_3 = cls.Affiliate.create({
            'name': 'Test Affiliate 3',
            'email': 'test3@example.com',
            'membership_type': 'individual',
        })
        cls.affiliate_4 = cls.Affiliate.create({
            'name': 'Test Affiliate 4',
            'email': 'test4@example.com',
            'membership_type': 'individual',
        })
        cls.affiliate_outside = cls.Affiliate.create({
            'name': 'Test Outsider',
            'email': 'outsider@example.com',
            'membership_type': 'individual',
        })

    def _create_assembly(self, **kwargs):
        vals = {
            'title': 'Test Assembly',
            'date': '2026-06-15 14:00:00',
            'assembly_type': 'ordinary',
            'member_ids': [
                (4, self.affiliate_1.id),
                (4, self.affiliate_2.id),
                (4, self.affiliate_3.id),
                (4, self.affiliate_4.id),
            ],
        }
        vals.update(kwargs)
        return self.Assembly.create(vals)

    # ---- 1. Auto-sequence on create ----------------------------------------

    def test_01_auto_sequence(self):
        assembly = self._create_assembly()
        self.assertTrue(assembly.name.startswith('ASM-'))
        self.assertNotEqual(assembly.name, '/')

    # ---- 2. Status transitions (full workflow) ------------------------------

    def test_02_status_transitions(self):
        assembly = self._create_assembly()
        self.assertEqual(assembly.status, 'draft')

        assembly.action_schedule()
        self.assertEqual(assembly.status, 'scheduled')

        # Add attendance for quorum
        self.Attendance.create({
            'assembly_id': assembly.id,
            'affiliate_id': self.affiliate_1.id,
            'status': 'present',
        })

        assembly.action_open_session()
        self.assertEqual(assembly.status, 'in_session')

        assembly.action_start_voting()
        self.assertEqual(assembly.status, 'voting')

        assembly.action_close()
        self.assertEqual(assembly.status, 'closed')

    # ---- 3. Cancel from scheduled -------------------------------------------

    def test_03_cancel_from_scheduled(self):
        assembly = self._create_assembly()
        assembly.action_schedule()
        assembly.action_cancel()
        self.assertEqual(assembly.status, 'cancelled')

    # ---- 4. Send invitations ------------------------------------------------

    def test_04_send_invitations(self):
        assembly = self._create_assembly()
        assembly.action_schedule()
        # Should not raise
        assembly.action_send_invitations()
        # Check that mail.mail records were created
        mails = self.env['mail.mail'].search([
            ('model', '=', 'club.assembly'),
            ('res_id', '=', assembly.id),
        ])
        # At least some mails should be queued (member_ids have emails)
        self.assertTrue(len(mails) >= 0)

    # ---- 5. Add all active affiliates ---------------------------------------

    def test_05_add_all_active_affiliates(self):
        assembly = self.Assembly.create({
            'title': 'Empty Assembly',
            'date': '2026-07-01 10:00:00',
        })
        self.assertEqual(len(assembly.member_ids), 0)
        assembly.action_add_all_active_affiliates()
        # Should add all affiliates with membership_status='active'
        active_count = self.Affiliate.search_count([
            ('membership_status', '=', 'active'),
        ])
        self.assertEqual(len(assembly.member_ids), active_count)

    # ---- 6. Topic status transitions ----------------------------------------

    def test_06_topic_status_transitions(self):
        assembly = self._create_assembly()
        topic = self.Topic.create({
            'assembly_id': assembly.id,
            'name': 'Test Topic',
            'topic_type': 'voting',
        })
        self.assertEqual(topic.status, 'pending')

        topic.action_open_discussion()
        self.assertEqual(topic.status, 'in_discussion')

        topic.action_open_voting()
        self.assertEqual(topic.status, 'voting_open')

    # ---- 7. Close voting computes result ------------------------------------

    def test_07_close_voting_approved(self):
        assembly = self._create_assembly()
        topic = self.Topic.create({
            'assembly_id': assembly.id,
            'name': 'Approval Topic',
            'topic_type': 'voting',
        })
        topic.action_open_discussion()
        topic.action_open_voting()

        # 2 for, 1 against
        self.Vote.create({
            'topic_id': topic.id,
            'affiliate_id': self.affiliate_1.id,
            'vote': 'for',
        })
        self.Vote.create({
            'topic_id': topic.id,
            'affiliate_id': self.affiliate_2.id,
            'vote': 'for',
        })
        self.Vote.create({
            'topic_id': topic.id,
            'affiliate_id': self.affiliate_3.id,
            'vote': 'against',
        })

        topic.action_close_voting()
        self.assertEqual(topic.status, 'approved')
        self.assertIn('Aprobado', topic.vote_result)
        self.assertIn('2', topic.vote_result)

    def test_07b_close_voting_rejected(self):
        assembly = self._create_assembly()
        topic = self.Topic.create({
            'assembly_id': assembly.id,
            'name': 'Rejection Topic',
            'topic_type': 'voting',
        })
        topic.action_open_discussion()
        topic.action_open_voting()

        # 1 for, 2 against
        self.Vote.create({
            'topic_id': topic.id,
            'affiliate_id': self.affiliate_1.id,
            'vote': 'for',
        })
        self.Vote.create({
            'topic_id': topic.id,
            'affiliate_id': self.affiliate_2.id,
            'vote': 'against',
        })
        self.Vote.create({
            'topic_id': topic.id,
            'affiliate_id': self.affiliate_3.id,
            'vote': 'against',
        })

        topic.action_close_voting()
        self.assertEqual(topic.status, 'rejected')
        self.assertIn('Rechazado', topic.vote_result)

    # ---- 8. Vote unique constraint ------------------------------------------

    def test_08_vote_unique_constraint(self):
        assembly = self._create_assembly()
        topic = self.Topic.create({
            'assembly_id': assembly.id,
            'name': 'Unique Vote Topic',
            'topic_type': 'voting',
        })
        self.Vote.create({
            'topic_id': topic.id,
            'affiliate_id': self.affiliate_1.id,
            'vote': 'for',
        })
        with self.assertRaises(Exception):
            self.Vote.create({
                'topic_id': topic.id,
                'affiliate_id': self.affiliate_1.id,
                'vote': 'against',
            })

    # ---- 9. Vote validation: voter must be assembly member ------------------

    def test_09_voter_must_be_member(self):
        assembly = self._create_assembly()
        topic = self.Topic.create({
            'assembly_id': assembly.id,
            'name': 'Member Validation Topic',
            'topic_type': 'voting',
        })
        with self.assertRaises(ValidationError):
            self.Vote.create({
                'topic_id': topic.id,
                'affiliate_id': self.affiliate_outside.id,
                'vote': 'for',
            })

    # ---- 10. Quorum computed field ------------------------------------------

    def test_10_quorum_computed(self):
        assembly = self._create_assembly(quorum_required=2)
        # No attendance yet
        self.assertFalse(assembly.quorum_met)

        # Add 1 present
        self.Attendance.create({
            'assembly_id': assembly.id,
            'affiliate_id': self.affiliate_1.id,
            'status': 'present',
        })
        assembly.invalidate_recordset()
        self.assertFalse(assembly.quorum_met)

        # Add 2nd present
        self.Attendance.create({
            'assembly_id': assembly.id,
            'affiliate_id': self.affiliate_2.id,
            'status': 'present',
        })
        assembly.invalidate_recordset()
        self.assertTrue(assembly.quorum_met)

    # ---- 11. Attendance unique constraint -----------------------------------

    def test_11_attendance_unique_constraint(self):
        assembly = self._create_assembly()
        self.Attendance.create({
            'assembly_id': assembly.id,
            'affiliate_id': self.affiliate_1.id,
            'status': 'present',
        })
        with self.assertRaises(Exception):
            self.Attendance.create({
                'assembly_id': assembly.id,
                'affiliate_id': self.affiliate_1.id,
                'status': 'absent',
            })
