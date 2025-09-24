from odoo import models, fields, api

class MemoOverBudget(models.Model):
    _name = 'memo.over.budget'
    _description = 'Memo Over Budget'
    _rec_name = 'name'

    name = fields.Char(string="Name", readonly=True, copy=False)
    purchase_order_id = fields.Many2one(
        'purchase.order', string='Reference', required=True, ondelete='cascade')
    date = fields.Date(string="Date", default=fields.Date.today)
    reason = fields.Text(string="Reason")

    line_ids = fields.One2many('memo.over.budget.line', 'memo_id', string='Detail Over Budget')

    @api.model
    def create(self, vals):
        if not vals.get('name') or vals.get('name') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('memo.over.budget') or 'New'
        return super(MemoOverBudget, self).create(vals)

    def action_confirm_memo(self):
        for memo in self:
            memo.purchase_order_id.memo_over_budget_done = True
        return {'type': 'ir.actions.act_window_close'}

class MemoOverBudgetLine(models.Model):
    _name = 'memo.over.budget.line'
    _description = 'Memo Over Budget Line'

    memo_id = fields.Many2one('memo.over.budget', string='Memo', ondelete='cascade')
    description = fields.Char(string="Deskripsi")
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    budget_item_id = fields.Many2one('budget.item', string='Budget Item', readonly=True)
    request_qty = fields.Float(string='Request Qty', readonly=True)
    budget_qty = fields.Float(string='Budget Qty', readonly=True)
    request_price = fields.Float(string='Request Price', readonly=True)
    budget_price = fields.Float(string='Budget Price', readonly=True)
    request_amount = fields.Float(string='Request Amount', readonly=True)
    budget_amount = fields.Float(string='Budget Amount', readonly=True)
    over_amount = fields.Float(string='Over', compute='_compute_over_amount', store=True)
    # posisi_over = fields.Selection([
    #     ('amount', 'Over Quantity'),
    #     ('price', 'Over Price'),
    #     ('both', 'Over Quantity & Price')
    # ], string='Posisi Over', readonly=True)
    posisi_over = fields.Selection([
       ('amount', 'Purchase Order'),
       ('price', 'Purchase Order'),
       ('both', 'Purchase Order')
    ], string='Posisi Over', readonly=True)

    @api.depends('request_amount', 'budget_amount')
    def _compute_over_amount(self):
        for line in self:
            line.over_amount = (line.request_amount or 0.0) - (line.budget_amount or 0.0)
