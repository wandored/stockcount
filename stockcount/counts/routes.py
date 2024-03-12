"""
count/routes.py is flask routes for counts, purchases, sales and items
"""
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from stockcount import db
from stockcount.counts import blueprint
from stockcount.counts.forms import (
    EnterCountForm,
    EnterPurchasesForm,
    EnterSalesForm,
    NewItemForm,
    UpdateCountForm,
    UpdateItemForm,
    UpdatePurchasesForm,
    UpdateSalesForm,
)
from stockcount.counts.utils import calculate_totals
from stockcount.models import InvCount, InvItems, InvPurchases, InvSales


@blueprint.route("/count/", methods=["GET", "POST"])
@login_required
def count():
    """Enter count for an item"""
    page = request.args.get("page", 1, type=int)
    inv_items = InvCount.query.all()
    group_items = db.session.query(InvCount).group_by(
        InvCount.id, InvCount.trans_date, InvCount.count_time
    )
    ordered_items = group_items.order_by(
        InvCount.trans_date.desc(), InvCount.count_time.desc()
    ).paginate(page=page, per_page=10)
    form = EnterCountForm()
    if form.validate_on_submit():
        items_object = InvItems.query.filter_by(id=form.itemname.data.id).first()

        # Calculate the previous count
        filter_item = InvCount.query.filter(InvCount.item_id == form.itemname.data.id)
        previous_count = filter_item.order_by(InvCount.trans_date.desc()).first()
        if previous_count is None:
            total_previous = 0
        else:
            total_previous = previous_count.count_total

        # Check if count exists for same day and time
        double_count = InvCount.query.filter_by(
            item_id=form.itemname.data.id,
            trans_date=form.transdate.data,
            count_time=form.am_pm.data,
        ).first()
        if double_count is not None:
            flash(
                f"{form.itemname.data.item_name} already has a {form.am_pm.data} count on {form.transdate.data}, please enter a different date or time",
                "warning",
            )
            return redirect(url_for("counts_blueprint.count"))

        # Calculate total purchases
        purchase_item = InvPurchases.query.filter_by(
            item_id=form.itemname.data.id, trans_date=form.transdate.data
        ).first()
        if purchase_item is None:
            total_purchase = 0
        else:
            total_purchase = purchase_item.purchase_total

        # Calculate total sales
        sales_item = InvSales.query.filter_by(
            item_id=form.itemname.data.id, trans_date=form.transdate.data
        ).first()
        if sales_item is None:
            total_sales = 0
        else:
            total_sales = sales_item.sales_total

        inventory = InvCount(
            trans_date=form.transdate.data,
            count_time=form.am_pm.data,
            item_name=form.itemname.data.item_name,
            case_count=form.casecount.data,
            each_count=form.eachcount.data,
            count_total=(
                items_object.case_pack * form.casecount.data + form.eachcount.data
            ),
            previous_total=total_previous,
            theory=(total_previous + total_purchase - total_sales),
            daily_variance=(
                (items_object.case_pack * form.casecount.data + form.eachcount.data)
                - (total_previous + total_purchase - total_sales)
            ),
            item_id=form.itemname.data.id,
        )
        db.session.add(inventory)
        db.session.commit()
        flash(
            f"Count submitted for {form.itemname.data.item_name} on {form.transdate.data}!",
            "success",
        )
        return redirect(url_for("counts_blueprint.count"))

    print(*locals().items(), sep="\n")
    return render_template(
        "counts/count.html",
        title="Enter Count",
        form=form,
        inv_items=inv_items,
        ordered_items=ordered_items,
    )


@blueprint.route("/count/<int:count_id>/update", methods=["GET", "POST"])
@login_required
def update_count(count_id):
    """route for count/id/update"""
    item = InvCount.query.get_or_404(count_id)
    if not item.item_id:
        flash(f"{item.item_name} is not an active product!", "warning")
        return redirect(url_for("counts_blueprint.count"))
    inv_items = InvCount.query.all()
    form = UpdateCountForm()
    if form.validate_on_submit():
        items_object = InvItems.query.filter_by(id=form.item_id.data).first()
        filter_item = InvCount.query.filter(
            InvCount.item_id == form.item_id.data,
            InvCount.trans_date <= form.transdate.data,
        )
        ordered_count = (
            filter_item.order_by(InvCount.trans_date.desc(), InvCount.count_time.desc())
            .offset(1)
            .first()
        )
        if ordered_count is None:
            total_previous = 0
        else:
            total_previous = ordered_count.count_total

        purchase_item = InvPurchases.query.filter_by(
            item_id=form.item_id.data, trans_date=form.transdate.data
        ).first()
        if purchase_item is None:
            total_purchase = 0
        else:
            total_purchase = purchase_item.purchase_total

        sales_item = InvSales.query.filter_by(
            item_id=form.item_id.data, trans_date=form.transdate.data
        ).first()
        if sales_item is None:
            total_sales = 0
        else:
            total_sales = sales_item.sales_total

        item.trans_date = form.transdate.data
        item.count_time = form.am_pm.data
        item.item_name = form.itemname.data
        item.case_count = form.casecount.data
        item.each_count = form.eachcount.data
        item.count_total = (
            items_object.case_pack * form.casecount.data + form.eachcount.data
        )
        item.previous_total = total_previous
        item.theory = total_previous + total_purchase - total_sales
        item.daily_variance = (
            items_object.case_pack * form.casecount.data + form.eachcount.data
        ) - (total_previous + total_purchase - total_sales)
        db.session.commit()
        flash("Item counts have been updated!", "success")
        return redirect(url_for("counts_blueprint.count"))
    if request.method == "GET":
        form.item_id.data = item.item_id
        form.transdate.data = item.trans_date
        form.am_pm.data = item.count_time
        form.itemname.data = item.item_name
        form.casecount.data = item.case_count
        form.eachcount.data = item.each_count
    return render_template(
        "counts/update_count.html",
        title="Update Item Count",
        form=form,
        inv_items=inv_items,
        item=item,
        legend="Update Count",
    )


@blueprint.route("/count/<int:count_id>/delete", methods=["POST"])
@login_required
def delete_count(count_id):
    """Delete an item count"""
    item = InvCount.query.get_or_404(count_id)
    db.session.delete(item)
    db.session.commit()
    flash("Item counts have been deleted!", "success")
    return redirect(url_for("counts_blueprint.count"))


@blueprint.route("/purchases/", methods=["GET", "POST"])
@login_required
def purchases():
    """Enter new purchases"""
    purchase_items = InvPurchases.query.all()
    inv_items = InvItems.query.all()

    # Pagination
    page = request.args.get("page", 1, type=int)
    group_purchases = db.session.query(InvPurchases).group_by(
        InvPurchases.id, InvPurchases.trans_date
    )
    ordered_purchases = group_purchases.order_by(
        InvPurchases.trans_date.desc()
    ).paginate(page=page, per_page=10)

    form = EnterPurchasesForm()
    if form.validate_on_submit():
        items_object = InvItems.query.filter_by(id=form.itemname.data.id).first()

        # Check if purchase exists for same day and time
        double_purchase = InvPurchases.query.filter_by(
            item_id=form.itemname.data.id, trans_date=form.transdate.data
        ).first()
        if double_purchase is not None:
            flash(
                f"{form.itemname.data.item_name} already has a purchase on {form.transdate.data}, please enter a different date or edit the existing purchase!",
                "warning",
            )
            return redirect(url_for("counts_blueprint.purchases"))

        purchase = InvPurchases(
            trans_date=form.transdate.data,
            count_time="PM",
            item_name=form.itemname.data.item_name,
            case_count=form.casecount.data,
            each_count=form.eachcount.data,
            purchase_total=(
                items_object.case_pack * form.casecount.data + form.eachcount.data
            ),
            item_id=form.itemname.data.id,
        )
        db.session.add(purchase)
        db.session.commit()
        flash(
            f"Purchases submitted for {form.itemname.data.item_name} on {form.transdate.data}!",
            "success",
        )
        calculate_totals(items_object.id)
        return redirect(url_for("counts_blueprint.purchases"))
    return render_template(
        "counts/purchases.html",
        title="Purchases",
        form=form,
        purchase_items=purchase_items,
        inv_items=inv_items,
        ordered_purchases=ordered_purchases,
    )


@blueprint.route("/purchases/<int:purchase_id>/update", methods=["GET", "POST"])
@login_required
def update_purchases(purchase_id):
    item = InvPurchases.query.get_or_404(purchase_id)
    if not item.item_id:
        flash(f"{item.item_name} is not an active product!", "warning")
        return redirect(url_for("counts_blueprint.purchases"))
    inv_items = InvPurchases.query.all()
    form = UpdatePurchasesForm()
    if form.validate_on_submit():
        items_object = InvItems.query.filter_by(id=form.item_id.data).first()
        item.trans_date = form.transdate.data
        item.item_name = form.itemname.data
        item.case_count = form.casecount.data
        item.each_count = form.eachcount.data
        item.purchase_total = (
            items_object.case_pack * form.casecount.data + form.eachcount.data
        )
        db.session.commit()
        flash("Item purchases have been updated!", "success")
        calculate_totals(items_object.id)
        return redirect(url_for("counts_blueprint.purchases"))
    elif request.method == "GET":
        form.transdate.data = item.trans_date
        form.itemname.data = item.item_name
        form.casecount.data = item.case_count
        form.eachcount.data = item.each_count
        form.item_id.data = item.item_id
    return render_template(
        "counts/update_purchases.html",
        title="Update Item Purchases",
        form=form,
        inv_items=inv_items,
        item=item,
        legend="Update Purchases",
    )


@blueprint.route("/purchases/<int:purchase_id>/delete", methods=["POST"])
@login_required
def delete_purchases(purchase_id):
    item = InvPurchases.query.get_or_404(purchase_id)
    unit = InvItems.query.filter_by(id=item.item_id).first()
    db.session.delete(item)
    db.session.commit()
    flash("Item purchases have been deleted!", "success")
    calculate_totals(unit.id)
    return redirect(url_for("counts_blueprint.purchases"))


@blueprint.route("/sales/", methods=["GET", "POST"])
@login_required
def sales():
    """Enter new sales for item"""
    page = request.args.get("page", 1, type=int)
    sales_items = InvSales.query.all()
    group_sales = db.session.query(InvSales).group_by(InvSales.id, InvSales.trans_date)
    ordered_sales = group_sales.order_by(InvSales.trans_date.desc()).paginate(
        page=page, per_page=10
    )
    form = EnterSalesForm()
    if form.validate_on_submit():
        unit = InvItems.query.filter_by(id=form.itemname.data.id).first()

        # Check if sales exists for same day and time
        double_sales = InvSales.query.filter_by(
            item_id=form.itemname.data.id, trans_date=form.transdate.data
        ).first()
        if double_sales is not None:
            flash(
                f"{form.itemname.data.item_name} already has Sales on {form.transdate.data}, please enter a different date or edit the existing sale!",
                "warning",
            )
            return redirect(url_for("counts_blueprint.sales"))

        sale = InvSales(
            trans_date=form.transdate.data,
            count_time="PM",
            item_name=form.itemname.data.item_name,
            each_count=form.eachcount.data,
            waste=form.waste.data,
            sales_total=(form.eachcount.data + form.waste.data),
            item_id=form.itemname.data.id,
        )
        db.session.add(sale)
        db.session.commit()
        flash(
            f"Sales of {form.eachcount.data + form.waste.data} {form.itemname.data.item_name} submitted on {form.transdate.data}!",
            "success",
        )
        calculate_totals(unit.id)
        return redirect(url_for("counts_blueprint.sales"))
    return render_template(
        "counts/sales.html",
        title="Sales",
        form=form,
        sales_items=sales_items,
        ordered_sales=ordered_sales,
    )


@blueprint.route("/sales/<int:sales_id>/update", methods=["GET", "POST"])
@login_required
def update_sales(sales_id):
    """Update sales items"""
    item = InvSales.query.get_or_404(sales_id)
    if not item.item_id:
        flash(f"{item.item_name} is not an active product!", "warning")
        return redirect(url_for("counts_blueprint.sales"))
    inv_items = InvSales.query.all()
    form = UpdateSalesForm()
    if form.validate_on_submit():
        unit = InvItems.query.filter_by(id=form.item_id.data).first()
        item.trans_date = form.transdate.data
        item.item_name = form.itemname.data
        item.each_count = form.eachcount.data
        item.waste = form.waste.data
        item.sales_total = form.eachcount.data + form.waste.data
        db.session.commit()
        flash("Item Sales have been updated!", "success")
        calculate_totals(unit.id)
        return redirect(url_for("counts_blueprint.sales"))
    elif request.method == "GET":
        form.transdate.data = item.trans_date
        form.itemname.data = item.item_name
        form.eachcount.data = item.each_count
        form.waste.data = item.waste
        form.item_id.data = item.item_id
    return render_template(
        "counts/update_sales.html",
        title="Update Item Sales",
        form=form,
        inv_items=inv_items,
        item=item,
        legend="Update Sales",
    )


@blueprint.route("/sales/<int:sales_id>/delete", methods=["POST"])
@login_required
def delete_sales(sales_id):
    """Delete sales items"""
    item = InvSales.query.get_or_404(sales_id)
    unit = InvItems.query.filter_by(id=item.item_id).first()
    db.session.delete(item)
    db.session.commit()
    flash("Item Sales have been deleted!", "success")
    calculate_totals(unit.id)
    return redirect(url_for("counts_blueprint.sales"))


@blueprint.route("/item/new", methods=["GET", "POST"])
@login_required
def new_item():
    """Create new inventory items"""
    inv_items = InvItems.query.all()
    form = NewItemForm()
    if form.validate_on_submit():
        item = InvItems(item_name=form.itemname.data, casepack=form.casepack.data)
        db.session.add(item)
        db.session.commit()
        flash(f"New item created for {form.itemname.data}!", "success")
        return redirect(url_for("counts_blueprint.new_item"))
    return render_template(
        "counts/new_item.html",
        title="New Inventory Item",
        form=form,
        inv_items=inv_items,
        legend="Enter New Item",
    )


@blueprint.route("/item/<int:item_id>/update", methods=["GET", "POST"])
@login_required
def update_item(item_id):
    """Update current inventory items"""
    item = InvItems.query.get_or_404(item_id)
    inv_items = InvItems.query.all()
    form = UpdateItemForm()
    if form.validate_on_submit():
        item.item_name = form.itemname.data
        item.casepack = form.casepack.data
        db.session.commit()
        flash(f"{item.item_name} has been updated!", "success")
        return redirect(url_for("counts_blueprint.new_item"))
    elif request.method == "GET":
        form.itemname.data = item.item_name
        form.casepack.data = item.casepack
    return render_template(
        "counts/update_item.html",
        title="Update Inventory Item",
        form=form,
        inv_items=inv_items,
        item=item,
        legend="Update Case Pack for ",
    )


@blueprint.route("/item/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    """Delete current items"""
    item = InvItems.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Product has been 86'd!", "success")
    return redirect(url_for("counts_blueprint.new_item"))
