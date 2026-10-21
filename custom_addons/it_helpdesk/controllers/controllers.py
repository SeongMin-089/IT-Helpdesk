# from odoo import http


# class ItHelpdesk(http.Controller):
#     @http.route('/it_helpdesk/it_helpdesk', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/it_helpdesk/it_helpdesk/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('it_helpdesk.listing', {
#             'root': '/it_helpdesk/it_helpdesk',
#             'objects': http.request.env['it_helpdesk.it_helpdesk'].search([]),
#         })

#     @http.route('/it_helpdesk/it_helpdesk/objects/<model("it_helpdesk.it_helpdesk"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('it_helpdesk.object', {
#             'object': obj
#         })

