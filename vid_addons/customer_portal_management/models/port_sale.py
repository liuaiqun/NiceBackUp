
from openerp import models, api, fields, _
from openerp.exceptions import ValidationError
from datetime import date
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class PortalSale(models.Model):

	_name = "portal.sale"
	_inherit = ['mail.thread','ir.needaction_mixin']
	_description = "Portal Order"
	_order = "id desc"


	def _amount_line_tax(self, line):

		val = 0.0
		price = line.product_price
		price = price * (1 - (line.normal or 0.0) / 100.0)
		price = price * (1 - (line.extra or 0.0) / 100.0)
		qty = line.product_qty
		for c in line.product_taxes.compute_all(price, qty, line.product_id, line.partner_id)['taxes']:
			val += c.get('amount', 0.0)
		return val

	@api.depends("line_id.product_taxes", "line_id.product_subtotal")
	def _calculate_amount(self):
		res = {}
		for stock in self:
			res[stock.id] = {
				'amount_taxable': 0.0,
				'amount_taxes': 0.0,
				'amount_total': 0.0,
			}
			val = val1 =  0.0
			for line in stock.line_id:
				val1 += line.product_subtotal
				val += self._amount_line_tax(line)
			stock.update({
                'amount_taxable': val1,
                'amount_taxes': val,
                'amount_total':val + val1,
                })

	@api.depends("product_categ_id", "order_type")
	def _get_discount(self):
		for order in self:
			if order.order_type == "normal":
				discount_id = self.env["partner.discount"].search([('partner_id', '=', order.partner_id.id), ('category_id', '=', order.product_categ_id.id)])
				if discount_id:
					order.normal = discount_id.normal_disc
					order.extra = discount_id.additional_disc
			else:
				order.normal = 0
				order.extra = 0

	name = fields.Char("name")
	partner_id = fields.Many2one("res.partner", string="Partner", track_visibility="onchange", default=lambda self:self.env.user.partner_id.id)
	order_type = fields.Selection([('normal', 'Normal'),
									('special', 'Special')], string="Type", default="normal", track_visibility="onchange")
	state = fields.Selection([('draft', 'Draft'),
								('confirm', 'Confirm'),
								('order', 'Order Taken'),
								('cancel', 'Cancel')], string="Status", default="draft", track_visibility="onchange")
	gst_type = fields.Many2one("sale.order.type", string="Gst Type", default=lambda self:self.env.user.partner_id.sale_type.id)
	gst_sub_type = fields.Many2one("sale.order.sub.type", string="Gst Sub Type", default=lambda self:self.env.user.partner_id.sale_sub_type_id.id)
	order_date = fields.Date(string="Order Date", default=lambda x:date.today(), track_visibility="onchange")
	order_no = fields.Char(string="Order No", track_visibility="onchange")
	product_categ_id = fields.Many2one("product.brand", string="Product Category", track_visibility="onchange")
	line_id = fields.One2many("portal.sale.line", "sale_id", string="Line Ref", copy=True)
	company_id = fields.Many2one("res.company", string="Company", default=lambda self:self.env.user.company_id.id)
	amount_taxable = fields.Float(string="Taxable Value", compute='_calculate_amount', store=True, track_visibility="onchange")
	amount_taxes = fields.Float(string="Taxes", compute='_calculate_amount', store=True, track_visibility="onchange")
	amount_total = fields.Float(string="Total", compute='_calculate_amount', store=True, track_visibility="onchange")
	normal = fields.Float(string="Normal", compute=_get_discount, store="True")
	extra = fields.Float(string="Extra", compute=_get_discount, store="True")
	sale_order = fields.Many2one("sale.order", string="Sale Order ref")

	@api.multi
	def action_confirm(self):
		self.write({"state":"confirm"})

	@api.multi
	def action_cancel(self):
		self.write({"state":"cancel"})


	@api.multi
	def action_quotation(self):
		
		sale_obj = self.env['sale.order']
		sale_line_obj = self.env['sale.order.line']

		vals = {
			'partner_id':self.partner_id.id,
			'partner_invoice_id':self.partner_id.id,
			'partner_shipping_id':self.partner_id.id,
			'type_id':self.gst_type.id,
			'sub_type_id':self.gst_sub_type.id,
			'user_id':self.partner_id.user_id.id,
			'date_order':datetime.now(),
			'client_order_ref':self.order_no,
			'brand_id':self.product_categ_id.id,
			'partner_selling_type':self.order_type,
			'normal_disc':self.normal,
			'extra_discount':self.extra,
			'section_id':self.partner_id.section_id.id,
			'fiscal_position':self.partner_id.property_account_position.id
		}
		sale_id = sale_obj.create(vals)
		for line in self.line_id:
			context = {
				'sub_type_id':self.gst_sub_type.id,
				'partner_type':self.order_type
			}
			line_val = {
				'order_id':sale_id.id,
				'product_id':line.product_id.id,
				'product_uom_qty':line.product_qty,
				'ordered_qty':line.product_qty,
				'order_partner_id':self.partner_id.id
			}

			sale_line_obj.with_context(context).create(line_val)

		self.write({'state':'order', 'sale_order':sale_id.id})

	@api.model
	def create(self, val):
		if val.get('name', '/') == '/':
			val['name'] = self.env['ir.sequence'].next_by_code("customer.portal")
		return super(PortalSale, self).create(val)

class PortalSaleLine(models.Model):

	_name = "portal.sale.line"
	_order = "id desc"

	# @api.depends("product_id", "sale_id.gst_sub_type")
	# def _get_product(self):
	# 	for line in self:
	# 		gst, igst, formstate, forminter = False, False, False, False
	# 		taxes_ids = []
	# 		sub_type_id = None
	# 		if not line.product_id:
	# 			return None
	# 		if line._context.get("sale_sub_type", "/") != '/':
	# 			sub_type_id = line.sale_sub_type
	# 		if sub_type_id:
	# 			if sub_type_id.tax_categ == 'gst':
	# 				gst = True
	# 				igst, formstate, forminter = False, False, False
	# 			elif sub_type_id.tax_categ == 'igst':
	# 				gst, formstate, forminter = False, False, False
	# 				igst = True
	# 			elif sub_type_id.tax_categ == 'formstate':
	# 				gst, igst, forminter = False, False, False
	# 				formstate = True
	# 			elif sub_type_id.tax_categ == 'forminter':
	# 				gst, igst, formstate = False, False, False
	# 				forminter = True
	# 			else:
	# 				gst, igst, formstate, forminter = False, False, False, False
	# 		# fpos = line.order_id.partner_id.property_account_position
	# 		if gst or igst:
	# 			for prod_tax in line.product_id.taxes_id:
	# 				if prod_tax.company_id.id == line.company_id.id:
	# 					if gst:
	# 						if prod_tax.tax_categ == 'gst':
	# 							taxes_ids.append(prod_tax.id)
	# 					elif igst:
	# 						if prod_tax.tax_categ == 'igst':
	# 							taxes_ids.append(prod_tax.id)

	# 		if sub_type_id and sub_type_id.taxes_id:
	# 			for tax in sub_type_id.taxes_id:
	# 				taxes_ids.append(tax.id)

	# 		line.product_taxes = taxes_ids
	# 		_logger.info("The taxes are = "+str(line.product_taxes))
	# 		line.product_price = line.product_id.lst_price


	@api.depends("product_price", "product_qty", "product_id", "sale_id.order_type", "sale_id.product_categ_id")
	def _get_subtotal(self):
		for line in self:
			line.normal = line.sale_id.normal
			line.extra = line.sale_id.extra
			product_subtotal = line.product_price * line.product_qty
			product_subtotal = product_subtotal * (1 - (line.normal or 0.0) / 100.0)
			product_subtotal = product_subtotal * (1 - (line.extra or 0.0) / 100.0)
			line.product_subtotal = product_subtotal

	@api.depends("product_id")
	def _get_price(self):
		for line in self:
			line.product_price = line.product_id.lst_price

	# @api.depends()
	# def _get_discount(self):
	# 	for line in self:


	product_id = fields.Many2one("product.product", string="Product")
	product_qty = fields.Float(string="Quantity")
	product_price = fields.Float(string="Price", compute=_get_price, store=True)
	product_taxes = fields.Many2many("account.tax", "rel_product_taxes_id", "product_taxes", "sale_id", string="Taxes")
	product_subtotal = fields.Float(string="Subtotal", store=True, compute=_get_subtotal)
	sale_id = fields.Many2one("portal.sale", string="Portal reference")
	company_id = fields.Many2one("res.company", related="sale_id.company_id")
	partner_id = fields.Many2one("res.partner", related="sale_id.partner_id")
	sale_sub_type = fields.Many2one("sale.order.sub.type", related="sale_id.gst_sub_type")
	normal = fields.Float(string="Normal", compute=_get_subtotal, store=True)
	extra = fields.Float(string="Extra", compute=_get_subtotal, store=True)

	@api.onchange("product_id", "order_id.order_type")
	def on_change_product_id(self):
		for line in self:
			
			if line.product_id.price_list and line.sale_id.order_type != "special":
				raise ValidationError("This product cannot be quoted in NORMAL order please change the Type to SPECIAL")
			gst, igst, formstate, forminter = False, False, False, False
			taxes_ids = []
			sub_type_id = None
			if not line.product_id:
				return None
			if line._context.get("sale_sub_type", "/") != '/':
				sub_type_id = line.sale_sub_type
			if sub_type_id:
				if sub_type_id.tax_categ == 'gst':
					gst = True
					igst, formstate, forminter = False, False, False
				elif sub_type_id.tax_categ == 'igst':
					gst, formstate, forminter = False, False, False
					igst = True
				elif sub_type_id.tax_categ == 'formstate':
					gst, igst, forminter = False, False, False
					formstate = True
				elif sub_type_id.tax_categ == 'forminter':
					gst, igst, formstate = False, False, False
					forminter = True
				else:
					gst, igst, formstate, forminter = False, False, False, False
			# fpos = line.order_id.partner_id.property_account_position
			if gst or igst:
				for prod_tax in line.product_id.taxes_id:
					if prod_tax.company_id.id == line.company_id.id:
						if gst:
							if prod_tax.tax_categ == 'gst':
								taxes_ids.append(prod_tax.id)
						elif igst:
							if prod_tax.tax_categ == 'igst':
								taxes_ids.append(prod_tax.id)



		line.product_taxes = taxes_ids
		line.product_price = line.product_id.lst_price