from odoo import models, fields, api
from odoo.exceptions import ValidationError

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    budget_item_id = fields.Many2one(
        'budget.item',
        string="Budget Item",
        domain="[('parent_id', '!=', False)]"
    )
    over_budget = fields.Boolean(string="Over Budget", compute="_compute_over_budget", store=True)

    @api.depends('product_qty', 'price_unit', 'budget_item_id')
    def _compute_over_budget(self):
        for line in self:
            over = False
            if line.budget_item_id and line.product_id:
                budget_lines = line.budget_item_id.line_ids.filtered(
                    lambda l: l.product_id == line.product_id
                )
                if budget_lines:
                    total_remain = sum(budget_lines.mapped('qty_remain'))
                    max_budget_price = max(budget_lines.mapped('unit_price'))
                    if line.product_qty > total_remain or line.price_unit > max_budget_price:
                        over = True
            line.over_budget = over

    @api.constrains('product_id', 'budget_item_id')
    def _check_product_in_budget_item(self):
        """Cegah save kalau produk tidak ada di budget item line."""
        for line in self:
            if line.budget_item_id and line.product_id:
                budget_lines = line.budget_item_id.line_ids.filtered(
                    lambda l: l.product_id == line.product_id
                )
                if not budget_lines:
                    raise ValidationError(
                        f"Produk '{line.product_id.display_name}' "
                        f"tidak tersedia pada Budget Item '{line.budget_item_id.name}'."
                    )

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    has_over_budget = fields.Boolean(string="Has Over Budget", compute="_compute_has_over_budget", store=True)
    memo_over_budget_done = fields.Boolean(string="Memo Over Budget Done", default=False)
    memo_over_budget_id = fields.Many2one('memo.over.budget', string="Budget Revision", readonly=True)

    @api.depends('order_line.over_budget')
    def _compute_has_over_budget(self):
        for order in self:
            order.has_over_budget = any(line.over_budget for line in order.order_line)

    def action_memo_over_budget(self):
        self.ensure_one()
        memo = self.env['memo.over.budget'].search([
            ('purchase_order_id', '=', self.id)
        ], limit=1)

        if not memo:
            memo = self.env['memo.over.budget'].create({
                'purchase_order_id': self.id,
                'reason': '',
            })

            for pol in self.order_line.filtered(lambda l: l.over_budget):
                budget_lines = pol.budget_item_id.line_ids.filtered(
                    lambda l: l.product_id == pol.product_id
                )
                budget_qty = sum(budget_lines.mapped('qty_remain')) if budget_lines else 0.0
                budget_price = max(budget_lines.mapped('unit_price')) if budget_lines else 0.0
                budget_amount = sum(budget_lines.mapped(
                    'subtotal')) if 'subtotal' in budget_lines._fields else budget_qty * budget_price

                posisi_over = False
                if pol.product_qty > budget_qty and pol.price_unit > budget_price:
                    posisi_over = 'both'
                elif pol.product_qty > budget_qty:
                    posisi_over = 'amount'
                elif pol.price_unit > budget_price:
                    posisi_over = 'price'

                self.env['memo.over.budget.line'].create({
                    'memo_id': memo.id,
                    'description': '',
                    'product_id': pol.product_id.id,
                    'budget_item_id': pol.budget_item_id.id,
                    'request_qty': pol.product_qty,
                    'budget_qty': budget_qty,
                    'request_price': pol.price_unit,
                    'budget_price': budget_price,
                    'request_amount': pol.price_subtotal,
                    'budget_amount': budget_amount,
                    'posisi_over': posisi_over,
                })

        self.memo_over_budget_id = memo.id

        return {
            'type': 'ir.actions.act_window',
            'name': 'Memo Over Budget',
            'res_model': 'memo.over.budget',
            'view_mode': 'form',
            'target': 'new',
            'res_id': memo.id,
        }

    def button_confirm(self):
        """Cek Memo Over Budget + Update qty_plan sesuai qty PO jika over."""
        for order in self:
            # 1. Validasi memo over budget terlebih dahulu
            if order.has_over_budget and not order.memo_over_budget_done:
                raise ValidationError(
                    "Purchase Order ini Over Budget. Buat & simpan Memo Over Budget terlebih dahulu."
                )

        # 2. Kalau lolos validasi, confirm PO dulu
        res = super(PurchaseOrder, self).button_confirm()

        # 3. Setelah PO dikonfirmasi → update qty_plan di budget item line
        for order in self:
            for line in order.order_line:
                if line.budget_item_id and line.product_id:
                    # Cari budget.item.line yg sesuai dgn product_id
                    budget_lines = line.budget_item_id.line_ids.filtered(
                        lambda l: l.product_id == line.product_id
                    )
                    for bl in budget_lines:
                        # Hitung total qty purchase yg sudah confirm untuk product ini
                        total_po_qty = self.env['purchase.order.line'].search([
                            ('budget_item_id', '=', line.budget_item_id.id),
                            ('product_id', '=', line.product_id.id),
                            ('order_id.state', 'in', ['purchase', 'done'])  # hanya yg sudah confirm
                        ]).mapped('product_qty')
                        total_po_qty = sum(total_po_qty)

                        # Kalau total realisasi lebih besar daripada plan → update plan
                        if total_po_qty > bl.qty_plan:
                            bl.qty_plan = total_po_qty
        return res

    def unlink(self):
        """Kalau PO dihapus, kembalikan qty_plan ke nilai sebelumnya."""
        # Cari semua budget item line yang terdampak
        for order in self:
            for line in order.order_line:
                if line.budget_item_id and line.product_id:
                    budget_lines = line.budget_item_id.line_ids.filtered(
                        lambda l: l.product_id == line.product_id
                    )
                    for bl in budget_lines:
                        # Hitung total qty purchase lainnya yang masih ada
                        total_po_qty = self.env['purchase.order.line'].search([
                            ('budget_item_id', '=', line.budget_item_id.id),
                            ('product_id', '=', line.product_id.id),
                            ('order_id.state', 'in', ['purchase', 'done']),
                            ('order_id', 'not in', self.ids)  # kecuali PO ini
                        ]).mapped('product_qty')
                        total_po_qty = sum(total_po_qty)

                        # Kembalikan qty_plan sesuai baseline atau total PO lain
                        if total_po_qty > bl.initial_qty_plan:
                            bl.qty_plan = total_po_qty
                        else:
                            bl.qty_plan = bl.initial_qty_plan
        return super(PurchaseOrder, self).unlink()