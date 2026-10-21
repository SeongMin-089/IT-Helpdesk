# from odoo import models, fields, api


# class it_helpdesk(models.Model):
#     _name = 'it_helpdesk.it_helpdesk'
#     _description = 'it_helpdesk.it_helpdesk'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
