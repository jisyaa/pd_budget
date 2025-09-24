{
    'name': 'Company Budget',
    'version': '1.0',
    'summary': 'Pencatatan Budget Perusahaan',
    'depends': ['base', 'product', 'uom', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'menu.xml',
        'view/budget.xml',
        'view/purchase.xml',
        'view/memo_over_budget.xml',
        'view/budget_template.xml'
    ],
    'installable': True,
    'application': False,
}