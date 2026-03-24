from odoo import fields, models


class ClubGolfCourse(models.Model):
    _name = 'club.golf.course'
    _description = 'Golf Course'
    _rec_name = 'name'

    name = fields.Char(string='Course Name', required=True)
    holes = fields.Integer(string='Holes', required=True, default=18)
    par = fields.Integer(string='Par', required=True, default=72)
    slope_rating = fields.Float(string='Slope Rating', digits=(5, 1))
    course_rating = fields.Float(string='Course Rating', digits=(5, 1))
