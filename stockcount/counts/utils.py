""" Calculation functions """
from flask import flash

from stockcount import db
from stockcount.models import InvCount, InvItems, InvPurchases, InvSales


def calculate_totals(item_id):
    """Run the variance calculations for each item"""
    unit = InvItems.query.get_or_404(item_id)
    filter_item = InvCount.query.filter(InvCount.item_id == unit.id)
    ordered_count = filter_item.order_by(
        InvCount.trans_date.desc(), InvCount.count_time.desc()
    ).first()

    if ordered_count is not None:
        purchase_item = InvPurchases.query.filter_by(
            item_id=unit.id, trans_date=ordered_count.trans_date
        ).first()
        if purchase_item is None:
            total_purchase = 0
        else:
            total_purchase = purchase_item.purchase_total

        sales_item = InvSales.query.filter_by(
            item_id=unit.id, trans_date=ordered_count.trans_date
        ).first()
        if sales_item is None:
            total_sales = 0
        else:
            total_sales = sales_item.sales_total

        ordered_count.theory = (
            ordered_count.previous_total + total_purchase - total_sales
        )
        ordered_count.daily_variance = (
            unit.case_pack * ordered_count.case_count + ordered_count.each_count
        ) - (ordered_count.previous_total + total_purchase - total_sales)
        db.session.commit()
        flash("Variances have been recalculated!", "success")
