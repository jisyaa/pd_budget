from odoo import models, fields, api

class BudgetTemplate(models.Model):
    _name = 'budget.template'
    _description = 'Budget'

    name = fields.Char(string="Template Name", required=True)
    type = fields.Selection([
        ('project', 'Project'),
        ('maintenance', 'Maintenance'),
        ('ict', 'ICT'),
        ('investment', 'Investment'),
        ('department', 'Department')
    ], string="Type of Budget")

    detail_ids = fields.One2many('template.detail', 'template_id', string="Details")

class TemplateDetail(models.Model):
    _name = 'template.detail'
    _description = 'Template Detail'
    _order = 'sequence'

    template_id = fields.Many2one('budget.template', string="Budget Template",  ondelete="cascade")
    sequence = fields.Char(string="Sequence", default='New', readonly=True)
    name = fields.Char(string="Template Detail", required=True)
    type = fields.Char(string="Type", required=True)
    parent_id = fields.Many2one('template.detail', string="Parent", domain="[('parent_id', '=', False), ('template_id', '=', template_id)]", ondelete="cascade")
    child_ids = fields.One2many('template.detail', 'parent_id', string="Children")
    check_detail = fields.Boolean('Check Detail', default=False)
    is_parent = fields.Boolean(compute="_compute_is_parent", store=True)

    @api.depends('parent_id')
    def _compute_is_parent(self):
        for rec in self:
            rec.is_parent = not bool(rec.parent_id)

    @api.model
    def create(self, vals):
        if vals.get('sequence', 'New') == 'New':
            if not vals.get('parent_id'):
                last_parent = self.search([
                    ('parent_id', '=', False)
                ], order='sequence desc', limit=1)

                if last_parent and last_parent.sequence:
                    try:
                        last_num = int(last_parent.sequence.split('-')[-1])
                    except ValueError:
                        last_num = 0
                    new_num = last_num + 100
                else:
                    new_num = 100

                vals['sequence'] = f"{new_num:04d}"
            else:
                parent = self.env['template.detail'].browse(vals['parent_id'])
                last_child = self.search([('parent_id', '=', parent.id)], order='sequence desc', limit=1)

                if last_child and last_child.sequence:
                    try:
                        last_num = int(last_child.sequence.split('-')[-1])
                    except ValueError:
                        last_num = int(parent.sequence.split('-')[-1])
                    new_num = last_num + 1
                else:
                    new_num = int(parent.sequence.split('-')[-1]) + 1

                vals['sequence'] = f"{new_num:04d}"

        return super().create(vals)