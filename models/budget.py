from odoo import models, fields, api

class Budget(models.Model):
    _name = 'budget.budget'
    _description = 'Budget'
    _rec_name = 'budget_number'

    budget_number = fields.Char(string="Budget Number", default='New', readonly=True)
    date = fields.Date(string="Date", required=True)
    budget_type = fields.Char(string="Budget Type", required=True)
    start_periode = fields.Date(string="Start Periode", required=True)
    end_periode = fields.Date(string="End Periode", required=True)
    currency_id = fields.Many2one('res.currency', string="Currency", default=lambda self: self.env.company.currency_id.id)
    notes = fields.Text(string="Notes")
    template_id = fields.Many2one('budget.template', string="Budget Template", ondelete="cascade")
    item_ids = fields.One2many('budget.item', 'budget_id', string="Item List")

    def _generate_items_from_template(self):
        """Generate parent-child items from template_id."""
        for budget in self:
            if not budget.template_id:
                continue

            parents = {}
            # Parent items
            for detail in budget.template_id.detail_ids.filtered(lambda d: not d.parent_id):
                parent_item = self.env['budget.item'].create({
                    'budget_id': budget.id,
                    'name': detail.name,
                    'type': detail.type,
                    'check_detail': detail.check_detail,
                    'is_parent': detail.is_parent,
                })
                parents[detail.id] = parent_item

            # Child items
            for detail in budget.template_id.detail_ids.filtered(lambda d: d.parent_id):
                parent_item = parents.get(detail.parent_id.id)
                if parent_item:
                    self.env['budget.item'].create({
                        'budget_id': budget.id,
                        'parent_id': parent_item.id,
                        'name': detail.name,
                        'type': detail.type,
                        'check_detail': detail.check_detail,
                        'is_parent': detail.is_parent,
                    })

    @api.model
    def create(self, vals):
        if vals.get('budget_number', 'New') == 'New':
            seq = self.env['ir.sequence'].next_by_code('budget.budget') or '0000'
            year = fields.Date.today().year
            vals['budget_number'] = f"{seq}/RAB-FO/ISAT-02/ENGR-PD/VII/FSI/{year}"

        vals.pop('item_ids', None)
        budget = super().create(vals)
        budget._generate_items_from_template()
        return budget

    def write(self, vals):
        template_changed = 'template_id' in vals
        res = super().write(vals)
        if template_changed:
            for rec in self:
                rec.item_ids.unlink()
                rec._generate_items_from_template()
        return res

    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Preview item list dari template tanpa create ke DB."""
        if self.template_id:
            # Buat record virtual (new) agar muncul di form view
            preview_items = self.env['budget.item']
            for detail in self.template_id.detail_ids:
                preview_items += self.env['budget.item'].new({
                    'budget_id': self.id or False,
                    'parent_id': False,  # biarkan kosong → hanya preview
                    'name': detail.name,
                    'type': detail.type,
                    'check_detail': detail.check_detail,
                    'is_parent': detail.is_parent,
                })
            self.item_ids = preview_items
        else:
            self.item_ids = False

class BudgetItem(models.Model):
    _name = 'budget.item'
    _description = 'Budget Item'
    _order = 'code'
    _rec_name = 'display_name'

    budget_id = fields.Many2one('budget.budget', string="Budget", required=True, ondelete="cascade")
    code = fields.Char(string="Code", default='New', readonly=True)
    name = fields.Char(string="Budget Item", required=True)
    parent_id = fields.Many2one('budget.item', string="Parent", domain="[('parent_id', '=', False), ('budget_id', '=', budget_id)]", ondelete="cascade")
    child_ids = fields.One2many('budget.item', 'parent_id', string="Children")

    budget_plan = fields.Float(string="Budget Plan", compute="_compute_budget_plan", store=True)
    request = fields.Float(string="Request", digits=(16, 2), compute="_compute_request", store=True)
    remaining = fields.Float(string="Remaining", compute="_compute_remaining", store=True)
    over_budget = fields.Float(string="Over Budget", compute="_compute_over_budget", store=True)
    actual = fields.Float(string="Actual", digits=(16, 2), compute="_compute_actual", store=True)

    type = fields.Char(string="Type", required=True)
    approved = fields.Boolean('Need Approve', default=False)
    check_detail = fields.Boolean('Check Detail', default=False)
    is_parent = fields.Boolean(compute="_compute_is_parent", store=True)

    display_name = fields.Char(
        compute="_compute_display_name",
        store=True
    )

    line_ids = fields.One2many("budget.item.line", "item_id", string="Lines")
    memo_over_budget_ids = fields.Many2many('memo.over.budget', compute="_compute_memo_over_budget_ids", string="Budget Revision", store=False)
    purchase_line_ids = fields.One2many(
        'purchase.order.line', 'budget_item_id',
        string="Purchase Lines"
    )

    request_purchase_ids = fields.One2many(
        'purchase.order.line', compute="_compute_request_purchase_ids",
        string="Request Detail"
    )

    actual_purchase_ids = fields.One2many(
        'purchase.order.line', compute="_compute_actual_purchase_ids",
        string="Actual Detail"
    )

    @api.depends('purchase_line_ids')
    def _compute_memo_over_budget_ids(self):
        """Cari memo dari purchase order lines yang mengacu ke budget item ini."""
        for item in self:
            # Ambil semua purchase order yang mengacu ke budget item ini
            purchase_orders = item.purchase_line_ids.mapped('order_id')

            # Ambil semua memo over budget dari purchase orders tsb
            memos = purchase_orders.mapped('memo_over_budget_id')

            # Tambahkan juga memo yang lewat memo.over.budget.line langsung
            memo_lines = self.env['memo.over.budget.line'].search([
                ('budget_item_id', '=', item.id)
            ])
            memos |= memo_lines.mapped('memo_id')

            item.memo_over_budget_ids = memos

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.code} - {rec.name}" if rec.code else rec.name

    def _compute_request_purchase_ids(self):
        for rec in self:
            rec.request_purchase_ids = rec.purchase_line_ids.filtered(
                lambda l: l.order_id.state in ['draft', 'sent', 'to approve', 'purchase']
            )

    def _compute_actual_purchase_ids(self):
        for rec in self:
            rec.actual_purchase_ids = rec.purchase_line_ids.filtered(
                lambda l: any(inv.payment_state == 'paid' for inv in l.order_id.invoice_ids)
            )

    @api.depends('parent_id')
    def _compute_is_parent(self):
        for rec in self:
            rec.is_parent = not bool(rec.parent_id)

    @api.model
    def create(self, vals):
        if vals.get('code', 'New') == 'New':
            budget_id = vals.get('budget_id')
            if not budget_id:
                return super().create(vals)

            budget = self.env['budget.budget'].browse(budget_id)
            prefix = budget.budget_number.split('/')[0] if budget.budget_number else '0000'

            if not vals.get('parent_id'):
                last_parent = self.search([
                    ('budget_id', '=', budget.id),
                    ('parent_id', '=', False)
                ], order='code desc', limit=1)

                if last_parent and last_parent.code:
                    try:
                        last_num = int(last_parent.code.split('-')[-1])
                    except ValueError:
                        last_num = 0
                    new_num = last_num + 100
                else:
                    new_num = 100

                vals['code'] = f"{prefix}/RAB-FO-{new_num:04d}"
            else:
                parent = self.env['budget.item'].browse(vals['parent_id'])
                last_child = self.search([('parent_id', '=', parent.id)], order='code desc', limit=1)

                if last_child and last_child.code:
                    try:
                        last_num = int(last_child.code.split('-')[-1])
                    except ValueError:
                        last_num = int(parent.code.split('-')[-1])
                    new_num = last_num + 1
                else:
                    new_num = int(parent.code.split('-')[-1]) + 1

                vals['code'] = f"{prefix}/RAB-FO-{new_num:04d}"

        return super().create(vals)

    @api.depends('child_ids.request', 'purchase_line_ids.price_subtotal', 'purchase_line_ids.order_id.state')
    def _compute_request(self):
        for rec in self:
            if rec.child_ids:
                rec.request = sum(child.request for child in rec.child_ids)
            else:
                purchase_lines = rec.purchase_line_ids.filtered(
                    lambda l: l.order_id.state in ['purchase', 'done']
                )
                rec.request = sum(purchase_lines.mapped('price_subtotal'))

    @api.depends('child_ids.budget_plan', 'line_ids.subtotal')
    def _compute_budget_plan(self):
        for rec in self:
            if rec.child_ids:
                rec.budget_plan = sum(child.budget_plan for child in rec.child_ids)
            else:
                rec.budget_plan = sum(line.subtotal for line in rec.line_ids)

    @api.depends('budget_plan', 'request', 'child_ids.remaining')
    def _compute_remaining(self):
        for rec in self:
            if rec.child_ids:
                rec.remaining = sum(child.remaining for child in rec.child_ids)
            else:
                rec.remaining = rec.budget_plan - rec.request

    @api.depends('child_ids.actual', 'purchase_line_ids.order_id.invoice_ids.payment_state')
    def _compute_actual(self):
        for rec in self:
            if rec.child_ids:
                # Parent → total actual dari semua child
                rec.actual = sum(child.actual for child in rec.child_ids)
            else:
                # Child → actual dari purchase line yang sudah paid
                paid_purchase_lines = rec.purchase_line_ids.filtered(
                    lambda l: any(inv.payment_state == 'paid' for inv in l.order_id.invoice_ids)
                )
                rec.actual = sum(paid_purchase_lines.mapped('price_subtotal'))

    @api.depends('budget_plan', 'actual', 'child_ids.over_budget')
    def _compute_over_budget(self):
        for rec in self:
            if rec.child_ids:
                # Parent → total over_budget dari child
                rec.over_budget = sum(child.over_budget for child in rec.child_ids)
            else:
                # Child → actual dikurangi budget_plan
                rec.over_budget = max(0, rec.actual - rec.budget_plan)

class BudgetItemLine(models.Model):
    _name = 'budget.item.line'
    _description = 'Budget Item Line'

    item_id = fields.Many2one('budget.item', string="Budget Item", required=True, ondelete="cascade")
    product_id = fields.Many2one('product.product', string="Product")
    name = fields.Char(string="Name")
    uom_id = fields.Many2one('uom.uom', string="Unit of Measure", store=True)
    qty_plan = fields.Float(string="Qty Plan")
    initial_qty_plan = fields.Float(string="Initial Qty Plan")
    unit_price = fields.Float(string="Unit Price", store=True)
    initial_unit_price = fields.Float('Initial Unit Price', readonly=True)
    qty_used = fields.Float(string="Qty Used", compute="_compute_qty_used", store=True)
    qty_remain = fields.Float(string="Qty Remain", compute="_compute_qty_remain", store=True)
    subtotal = fields.Float(string="Subtotal", compute="_compute_subtotal", store=True)
    remark = fields.Char(string="Remark")

    @api.model
    def create(self, vals):
        # Saat create, isi initial_qty_plan = qty_plan
        if 'qty_plan' in vals and 'initial_qty_plan' not in vals:
            vals['initial_qty_plan'] = vals['qty_plan']
        if 'unit_price' in vals and not vals.get('initial_unit_price'):
            vals['initial_unit_price'] = vals['unit_price']
        return super().create(vals)

    @api.depends('product_id', 'item_id.purchase_line_ids.order_id.state', 'item_id.purchase_line_ids.product_qty')
    def _compute_qty_used(self):
        for rec in self:
            qty = 0.0
            if rec.product_id and rec.item_id:
                purchase_lines = rec.item_id.purchase_line_ids.filtered(
                    lambda l: l.product_id.id == rec.product_id.id and l.order_id.state in ['purchase', 'done']
                )
                qty = sum(purchase_lines.mapped('product_qty'))
            rec.qty_used = qty

    @api.depends('qty_plan', 'qty_used')
    def _compute_qty_remain(self):
        for rec in self:
            rec.qty_remain = rec.qty_plan - rec.qty_used

    @api.depends('qty_plan', 'unit_price')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.qty_plan * rec.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for rec in self:
            if rec.product_id:
                rec.name = rec.product_id.display_name
                rec.uom_id = rec.product_id.uom_id.id

                vendors = rec.env['product.supplierinfo'].search([
                    ('product_tmpl_id', '=', rec.product_id.product_tmpl_id.id)
                ])

                if vendors:
                    # cari vendor dengan harga tertinggi
                    vendor = max(vendors, key=lambda v: v.price)
                    price = vendor.price

                    vendor_currency = vendor.currency_id or rec.env.company.currency_id
                    company_currency = rec.env.company.currency_id
                    rec.unit_price = vendor_currency._convert(
                        price, company_currency, rec.env.company, fields.Date.today()
                    )
                else:
                    rec.unit_price = rec.product_id.standard_price
