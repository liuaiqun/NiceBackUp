from openerp import api, models, fields
from openerp.exceptions import ValidationError, Warning
import logging
import base64
import math
from openerp.tools import amount_to_text_en
from datetime import date

_logger = logging.getLogger(__name__)


PAYMENT_MODE = [("tp", "To Pay"),
		("cca", "To Pay(CCA)"),
		("p","Paid"),
		("pdd", "Paid Delivery"),
		("pcca", "Paid (CCA)"),
		("dd", "Door Delivery")
		]
DISPATCH_MODE = [("tl", "Parcel Service"),
		("rail", "Rail Freight"),
		("van", "Van"),
		("shipping", "Shipping"),
		("air","Air Freight")]

class LrDoc(models.Model):

	_name = "lr.doc"
	_inherit = ['mail.thread']
	_order = "name desc, id desc"

	@api.depends("invoice_id")
	def _compute_amount(self):
		res = {}
		for line in self:
			res[line.id] = {
				"total_amount":0.0,
			}
			total_amount = 0
			for invoice in line.invoice_id:
				total_amount += invoice.amount_total
			line.total_amount = total_amount
	
	@api.one
	def _amount_in_words(self):
		amount_in_words = amount_to_text_en.amount_to_text(math.floor(self.total_amount), lang='en', currency='')
		amount_in_words = amount_in_words.replace(' and Zero Cent', '') + ' Rupees'
		decimals = self.total_amount % 1
		if decimals >= 10**-2:
			amount_in_words += ' and '+ amount_to_text_en.amount_to_text(math.floor(decimals*100), lang='en', currency='')
			amount_in_words = amount_in_words.replace(' and Zero Cent', '') + ' Paise'
		amount_in_words += ' Only'
		self.amount_in_words = amount_in_words


	name = fields.Char("Name", track_visibility='onchange')
	partner_id = fields.Many2one("res.partner", string="Customer", required=True, readonly=True, domain=[("customer", "=", True)], states={"draft":[('readonly',False)]})
	invoice_id = fields.Many2many("account.invoice", "partner_invoices_rel", "partner_id", "invoice_id", string="Invoices", required=True, readonly=True, states={"draft":[('readonly',False)], "confirm":[('readonly',False)]})
	date = fields.Datetime("Date", required=True, select=True, readonly=True, default=lambda x: date.today(), states={"draft":[('readonly', False)]})
	docket_no = fields.Char(string="Docket No")
	docket_date = fields.Datetime("Docket Date", readonly=True, states={"draft":[('readonly',False)], "confirm":[('readonly',False)]})
	freight_payment_type = fields.Selection(PAYMENT_MODE, string="Mode Of Dispatch", readonly=True, states={"draft":[('readonly',False)], "confirm":[('readonly',False)]})
	dispatch_mode = fields.Selection(DISPATCH_MODE, string="Transport", readonly=True, states={"draft":[('readonly',False)], "confirm":[('readonly',False)]})
	freight_amount = fields.Float("Freight Amount")
	articles = fields.Text(string="Articles")
	driver_name = fields.Char(string="Driver Name")
	courier_name = fields.Char(string="Courier Name")
	freight_no = fields.Char(string="Number Plate")
	contact_no = fields.Char(string="Contact No")
	state = fields.Selection([('draft', 'Draft'),
		("confirm", "Confirm"),
		("validate", "Done"),
		], string="State", default="draft",track_visibility='onchange')
	total_amount = fields.Float("Total Amount", compute="_compute_amount")
	amount_in_words = fields.Char("Amount in Words", compute="_amount_in_words")
	port_id = fields.Many2one("port.code" ,string="Port Code" )
	city_id = fields.Many2one("res.city", string="City")
	company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.user.company_id, readonly=True)

	@api.model
	def create(self, val):
		if val.get("name", "/") == '/':
			val["name"] = self.env["ir.sequence"].next_by_code("lr.doc")
		return super(LrDoc, self).create(val)

	@api.multi
	def lr_doc_confirm(self):
		self.state = "confirm"
		data = {}
		data['dispatch_id'] = self.name
		for invoice in self.invoice_id:
			account_obj = self.env['account.invoice'].browse(invoice.id)
			account_obj.write(data)

	@api.multi
	def lr_doc_validate(self):
		self.state = "validate"
		data = {}
		
		if self.driver_name:
			data['driver_name'] = self.driver_name
		if self.courier_name:
			data['courier_name'] = self.courier_name
		if self.freight_no:
			data['licence_number'] = self.freight_no
		if self.contact_no:
			data['contact_number'] = self.contact_no
		if self.docket_no:
			data['docket_number'] = self.docket_no
		if self.docket_date:
			data['docket_date'] = self.docket_date
		if self.port_id:
			data['port_id'] = self.port_id
		if self.dispatch_mode:
			data['dispatch_type'] = dict(DISPATCH_MODE)[self.dispatch_mode]
		for invoice in self.invoice_id:
			account_obj = self.env['account.invoice'].browse(invoice.id)
			account_obj.write(data)
	
	def mail_dispatch(self, cr, uid, ids, context=None):
		ir_model_data = self.pool.get('ir.model.data')
		try:
			template_id = ir_model_data.get_object_reference(cr, uid, 'lr_doc', 'lr_doc_mail_template')[1]
		except ValueError:
			template_id = False
		try:
			compose_form_id = ir_model_data.get_object_reference(cr, uid, 'mail', 'email_compose_message_wizard_form')[1]
		except ValueError:
			compose_form_id = False

		pdf = []
		lr_doc = self.browse(cr, uid, ids[0], context=context)
		
		for invoice in lr_doc.invoice_id:
			pdf_temp = self.pool.get('report').get_pdf(cr, uid, [invoice.id], 'nice_gst.report_invoice_gst', context=context)
			pdf_attachment = {
			    'name': invoice.number + ".pdf",
			    'datas_fname': invoice.number + ".pdf",
			    'type': 'binary',
			    'datas': base64.encodestring(pdf_temp),
			    'res_model': 'lr.doc',
			    'res_id': lr_doc.id,
			    'mimetype': 'application/x-pdf'
			}
			pdf.append(pdf_attachment)

		if template_id:
			template_id = self.pool.get('email.template').browse(cr, uid, template_id, context=context)
			template_id.write({'attachment_ids':[(5,)]})
			template_id.write({'attachment_ids':[(0, 0, pdf_attach)for pdf_attach in pdf]})

		# _logger.info("The attachment = " +str(template_id.attachment_ids))

		# val = {'attachment_ids': [(6, 0, pdf)]}

		ctx = dict()
		ctx.update({
			'default_model': 'lr.doc',
			'default_res_id': ids[0],
			'default_use_template': bool(template_id),
			'default_template_id': template_id.id,
			'default_composition_mode': 'comment',
			'mark_so_as_sent': True,
		})

		return {
			'type': 'ir.actions.act_window',
			'view_type': 'form',
			'view_mode': 'form',
			'res_model': 'mail.compose.message',
			'views': [(compose_form_id, 'form')],
			'view_id': compose_form_id,
			'target': 'new',
			'context': ctx,
		}

	@api.multi
	def unlink(self):
		for lr in self:
			if lr.state != "draft":
				raise ValidationError("Unable to delete record")
		return super(LrDoc, self).unlink()

	@api.multi
	def lr_doc_print(self):
		invoices = []
		count = 0
		datas = {}
		for data in self.invoice_id:
			count += 1
			ids = "id"+str(count)
			datas[ids] = data.id
		datas["doc_id"] = self.id
		
		return self.env['report'].get_action(self, "lr_doc.report_lr_doc", data=datas)

	@api.multi
	def print_envolope(self):
		datas = {"doc_id":self.id}

		return self.env['report'].get_action(self, "lr_doc.print_on_envolope", data=datas)
	





	
