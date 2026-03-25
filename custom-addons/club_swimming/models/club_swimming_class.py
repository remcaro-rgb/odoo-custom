from odoo import fields, models


class ClubSwimmingClass(models.Model):
    _name = 'club.swimming.class'
    _description = 'Swimming Class'
    _order = 'name'

    name = fields.Char(string='Class Name', required=True)
    pool_id = fields.Many2one(
        'club.swimming.pool', string='Pool',
    )
    instructor_id = fields.Many2one(
        'club.swimming.lifeguard', string='Instructor',
    )
    day_of_week = fields.Selection(
        [
            ('0', 'Monday'),
            ('1', 'Tuesday'),
            ('2', 'Wednesday'),
            ('3', 'Thursday'),
            ('4', 'Friday'),
            ('5', 'Saturday'),
            ('6', 'Sunday'),
        ],
        string='Day of Week',
    )
    time_slot = fields.Float(string='Start Time')
    duration = fields.Float(string='Duration (hours)')
    max_students = fields.Integer(string='Max Students')
    student_ids = fields.Many2many(
        'club.affiliate',
        'club_swimming_class_affiliate_rel',
        'class_id',
        'affiliate_id',
        string='Students',
    )
    level = fields.Selection(
        [
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
        ],
        string='Level',
        default='beginner',
    )
