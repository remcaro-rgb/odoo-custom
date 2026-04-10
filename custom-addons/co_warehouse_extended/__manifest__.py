{
    'name': 'Colombia - Warehouse Extended',
    'version': '19.0.1.0.0',
    'summary': 'Extended warehouse, inventory & purchase features for Colombian businesses',
    'description': (
        'Purchase requests with approval workflow, enhanced goods receipt, '
        'inventory valuation formulas, supplier payment tracking, '
        'reorder point enhancements, warehouse classification, '
        'and inter-warehouse transfer wizard.'
    ),
    'category': 'Inventory/Inventory',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'purchase',
        'purchase_requisition',
        'account',
        'hr',
        'mail',
    ],
    'data': [
        # security first
        'security/co_warehouse_security.xml',
        'security/ir.model.access.csv',
        # data
        'data/sequences.xml',
        'data/product_request_sequence.xml',
        # views
        'views/co_product_request_views.xml',
        'views/co_purchase_request_views.xml',
        'views/co_inventory_formula_views.xml',
        'views/stock_warehouse_views.xml',
        'views/stock_warehouse_orderpoint_views.xml',
        'views/stock_picking_views.xml',
        'views/purchase_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/co_supplier_score_views.xml',
        'views/co_quotation_comparison_views.xml',
        'views/co_purchase_approval_level_views.xml',
        'views/co_menus.xml',
        # wizard
        'wizard/co_warehouse_transfer_wizard_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
