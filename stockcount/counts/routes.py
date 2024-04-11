"""
count/routes.py is flask routes for counts, purchases, sales and items
"""
from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from stockcount import db
from stockcount.counts import blueprint
from stockcount.counts.forms import (
    EnterCountForm,
    EnterPurchasesForm,
    EnterSalesForm,
    NewItemForm,
    StoreForm,
    UpdateCountForm,
    UpdateItemForm,
    UpdatePurchasesForm,
    UpdateSalesForm,
)
from stockcount.counts.utils import calculate_totals
from stockcount.main.utils import set_user_access
from stockcount.models import InvCount, InvItems, InvPurchases, InvSales, Restaurants


@blueprint.route("/count/", methods=["GET", "POST"])
@login_required
def count():
    """Enter count for an item"""
    location = Restaurants.query.filter_by(id=session["store"]).first()
    page = request.args.get("page", 1, type=int)
    inv_items = InvCount.query.filter(InvCount.store_id == session["store"]).all()
    print(inv_items)
    group_items = (
        db.session.query(InvCount)
        .filter(InvCount.store_id == session["store"])
        .group_by(InvCount.id, InvCount.trans_date, InvCount.count_time)
    )
    ordered_items = group_items.order_by(
        InvCount.trans_date.desc(), InvCount.count_time.desc()
    ).paginate(page=page, per_page=10)

    # forms
    form = EnterCountForm()
    store_form = StoreForm()

    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.count"))

    if form.validate_on_submit():
        items_object = InvItems.query.filter_by(id=form.itemname.data.id).first()

        # Calculate the previous count
        filter_item = InvCount.query.filter(
            InvCount.store_id == session["store"],
            InvCount.item_id == form.itemname.data.id,
        )
        previous_count = filter_item.order_by(InvCount.trans_date.desc()).first()
        if previous_count is None:
            total_previous = 0
        else:
            total_previous = previous_count.count_total

        # Check if count exists for same day and time
        double_count = InvCount.query.filter_by(
            store_id=session["store"],
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
            store_id=session["store"],
            item_id=form.itemname.data.id,
            trans_date=form.transdate.data,
        ).first()
        if purchase_item is None:
            total_purchase = 0
        else:
            total_purchase = purchase_item.purchase_total

        # Calculate total sales
        sales_item = InvSales.query.filter_by(
            store_id=session["store"],
            item_id=form.itemname.data.id,
            trans_date=form.transdate.data,
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
            store_id=session["store"],
        )
        db.session.add(inventory)
        db.session.commit()
        flash(
            f"Count submitted for {form.itemname.data.item_name} on {form.transdate.data}!",
            "success",
        )
        return redirect(url_for("counts_blueprint.count"))

    return render_template(
        "counts/count.html",
        title="Enter Count",
        **locals(),
    )


@blueprint.route("/count/<int:count_id>/update", methods=["GET", "POST"])
@login_required
def update_count(count_id):
    """route for count/id/update"""
    location = Restaurants.query.filter_by(id=session["store"]).first()
    item = InvCount.query.get_or_404(count_id)
    if not item.item_id:
        flash(f"{item.item_name} is not an active product!", "warning")
        return redirect(url_for("counts_blueprint.count"))
    inv_items = InvCount.query.all()
    form = UpdateCountForm()
    store_form = StoreForm()
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

    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.count"))

    return render_template(
        "counts/update_count.html",
        title="Update Item Count",
        legend="Update Count",
        **locals(),
    )


@blueprint.route("/count/<int:count_id>/delete", methods=["POST"])
@login_required
def delete_count(count_id):
    """Delete an item count"""
    location = Restaurants.query.filter_by(id=session["store"]).first()
    item = InvCount.query.get_or_404(count_id)
    db.session.delete(item)
    db.session.commit()
    flash("Item counts have been deleted!", "success")
    return redirect(url_for("counts_blueprint.count"))


@blueprint.route("/purchases/", methods=["GET", "POST"])
@login_required
def purchases():
    """Enter new purchases"""
    location = Restaurants.query.filter_by(id=session["store"]).first()
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
    store_form = StoreForm()
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

    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.count"))

    return render_template(
        "counts/purchases.html",
        title="Purchases",
        **locals(),
    )


@blueprint.route("/purchases/<int:purchase_id>/update", methods=["GET", "POST"])
@login_required
def update_purchases(purchase_id):
    location = Restaurants.query.filter_by(id=session["store"]).first()
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
        legend="Update Purchases",
        **locals(),
    )


@blueprint.route("/purchases/<int:purchase_id>/delete", methods=["POST"])
@login_required
def delete_purchases(purchase_id):
    location = Restaurants.query.filter_by(id=session["store"]).first()
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
    location = Restaurants.query.filter_by(id=session["store"]).first()
    page = request.args.get("page", 1, type=int)
    sales_items = InvSales.query.all()
    group_sales = db.session.query(InvSales).group_by(InvSales.id, InvSales.trans_date)
    ordered_sales = group_sales.order_by(InvSales.trans_date.desc()).paginate(
        page=page, per_page=10
    )
    form = EnterSalesForm()
    store_form = StoreForm()

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

    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.count"))

    return render_template(
        "counts/sales.html",
        title="Sales",
        **locals(),
    )


@blueprint.route("/sales/<int:sales_id>/update", methods=["GET", "POST"])
@login_required
def update_sales(sales_id):
    """Update sales items"""
    location = Restaurants.query.filter_by(id=session["store"]).first()
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
        legend="Update Sales",
        **locals(),
    )


@blueprint.route("/sales/<int:sales_id>/delete", methods=["POST"])
@login_required
def delete_sales(sales_id):
    """Delete sales items"""
    location = Restaurants.query.filter_by(id=session["store"]).first()
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
    print(session["store"])
    location = Restaurants.query.filter_by(id=session["store"]).first()
    inv_items = InvItems.query.filter(InvItems.store_id == session["store"]).all()
    form = NewItemForm()
    store_form = StoreForm()

    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.new_item"))

    if form.validate_on_submit():
        item = InvItems(
                item_name=form.itemname.data.name,
                case_pack=form.casepack.data,
                store_id=session["store"],
                        )
        db.session.add(item)
        db.session.commit()
        flash(f"{form.itemname.data.name} has been added to your stockcount items list!", "success")
        return redirect(url_for("counts_blueprint.new_item"))
    
    return render_template(
        "counts/new_item.html",
        title="New Inventory Item",
        legend="Enter New Item",
        **locals(),
    )


@blueprint.route("/item/<int:item_id>/update", methods=["GET", "POST"])
@login_required
def update_item(item_id):
    """Update current inventory items"""
    location = Restaurants.query.filter_by(id=session["store"]).first()
    inv_items = InvItems.query.filter(InvItems.store_id == session["store"]).all()
    item = InvItems.query.get_or_404(item_id)
    form = UpdateItemForm()
    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.new_item"))

    if form.validate_on_submit():
        item.item_name = form.itemname.data
        item.case_pack = form.casepack.data
        db.session.commit()
        flash(f"{item.item_name} has been updated!", "success")
        return redirect(url_for("counts_blueprint.new_item"))
    elif request.method == "GET":
        form.itemname.data = item.item_name
        form.casepack.data = item.case_pack

    return render_template(
        "counts/update_item.html",
        title="Update Inventory Item",
        legend="Update Case Pack for ",
        **locals(),
    )


@blueprint.route("/item/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    """Delete current items"""
    #TODO: method to delete all counts for an item
    location = Restaurants.query.filter_by(id=session["store"]).first()
    inv_items = InvItems.query.filter(InvItems.store_id == session["store"]).all()
    item = InvItems.query.get_or_404(item_id)
    counts = InvCount.query.filter_by(item_id=item.id).first()
    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.new_item"))

    if counts is not None:
        flash(f'you must delete {item.item_name} from all counts before deleting', 'warning')
        return redirect(url_for('counts_blueprint.new_item'))

    db.session.delete(item)
    db.session.commit()
    flash("Product has been 86'd!", "success")
    return redirect(url_for("counts_blueprint.new_item"))
