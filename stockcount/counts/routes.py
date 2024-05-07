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
    CountForm,
    PurchasesForm,
    SalesForm,
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

from icecream import ic


@blueprint.route("/count/", methods=["GET", "POST"])
@login_required
def count():
    """Enter count for an item"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    page = request.args.get("page", 1, type=int)
    inv_items = InvCount.query.filter(InvCount.store_id == session["store"]).all()
    count_dates = (
        db.session.query(
            InvCount.trans_date,
            InvCount.count_time,
        )
        .filter(InvCount.store_id == session["store"])
        .group_by(InvCount.trans_date, InvCount.count_time)
    )
    ordered_items = count_dates.order_by(InvCount.trans_date.desc(), InvCount.count_time.desc()).paginate(
        page=page, per_page=10
    )

    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            if x.id in session["access"]:
                session["store"] = x.id
                flash(f"Store changed to {x.name}", "success")
            else:
                flash("You do not have access to that store!", "danger")
        return redirect(url_for("counts_blueprint.count"))

    item_list = db.session.query(InvItems.id, InvItems.item_name).filter(InvItems.store_id == session["store"]).all()
    if(item_list == []):
        flash("You must add items to your inventory before you can count them!", "warning")
        return redirect(url_for("counts_blueprint.new_item")
        )
        
    multi_form = CountForm(counts=item_list)
    index = 0

    for form in multi_form.counts:
        form.itemname.data = item_list[index].item_name
        form.item_id.data = item_list[index].id
        index += 1

    del index
    
    # on form submission
    if multi_form.submit.data:
        # Check if count exists for same day and time
        #for each count entry, check if it already exists
        for count_entry in multi_form.counts.data:
            double_count = InvCount.query.filter_by(
                item_id=count_entry["item_id"],
                trans_date=multi_form.transdate.data,
                count_time=multi_form.am_pm.data,
            ).first()
            ic(double_count)
            if double_count is not None:
                flash(
                    f"{count_entry['itemname']} already has a count on {multi_form.transdate.data}, please enter a different date or time",
                    "warning",
                )
                return redirect(url_for("counts_blueprint.count"))
        
        # get previous count
        for count_entry in multi_form.counts.data:
            items_object = InvItems.query.filter_by(id=count_entry["item_id"]).first()
            filter_item = InvCount.query.filter(
                InvCount.store_id == session["store"],
                InvCount.item_id == count_entry["item_id"],
            )
            previous_count = filter_item.order_by(InvCount.trans_date.desc()).first()
            if previous_count is None:
                total_previous = 0
            else:
                total_previous = previous_count.count_total
                
            # Calculate total purchases
            purchase_item = InvPurchases.query.filter_by(
                store_id=session["store"],
                item_id=count_entry["item_id"],
                trans_date=multi_form.transdate.data,
            ).first()
            if purchase_item is None:
                total_purchase = 0
            else:
                total_purchase = purchase_item.purchase_total
                
            # Calculate total sales
            sales_item = InvSales.query.filter_by(
                store_id=session["store"],
                item_id=count_entry["item_id"],
                trans_date=multi_form.transdate.data,
            ).first()
            if sales_item is None:
                total_sales = 0
            else:
                total_sales = sales_item.sales_total
            
            for count_entry in multi_form.counts.data:
                items_object = InvItems.query.filter_by(id=count_entry["item_id"]).first()
                
                inventory = InvCount(
                    trans_date=multi_form.transdate.data,
                    count_time=multi_form.am_pm.data,
                    item_name=count_entry["itemname"],
                    case_count=count_entry["casecount"],
                    each_count=count_entry["eachcount"],
                    count_total=(
                        items_object.case_pack * count_entry["casecount"] + count_entry["eachcount"]
                    ),
                    previous_total=total_previous,
                    theory=(total_previous + total_purchase - total_sales),
                    daily_variance=(
                        (items_object.case_pack * count_entry["casecount"] + count_entry["eachcount"])
                        - (total_previous + total_purchase - total_sales)
                    ),
                    item_id=count_entry["item_id"],
                    store_id=session["store"],
                )
                db.session.add(inventory)
            db.session.commit()
            # flash(
            #     f"Count submitted for {count_entry['itemname ']} on {multi_form.transdate.data}!",
            #     "success",
            # )
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
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    item = InvCount.query.get_or_404(count_id)
    if not item.item_id:
        flash(f"{item.item_name} is not an active product!", "warning")
        return redirect(url_for("counts_blueprint.count"))
    inv_items = InvCount.query.all()
    form = UpdateCountForm()
    store_form = StoreForm()

    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.count"))

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
        legend="Update Count",
        **locals(),
    )


@blueprint.route("/count/<int:count_id>/delete", methods=["POST"])
@login_required
def delete_count(count_id):
    """Delete an item count"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    item = InvCount.query.get_or_404(count_id)
    db.session.delete(item)
    db.session.commit()
    flash("Item counts have been deleted!", "success")
    return redirect(url_for("counts_blueprint.count"))


@blueprint.route("/purchases/", methods=["GET", "POST"])
@login_required
def purchases():
    """Enter new purchases"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    
    page = request.args.get("page", 1, type=int)
    purchase_items = InvPurchases.query.filter(InvPurchases.store_id == session["store"]).all()
    purchase_dates = (
        db.session.query(InvPurchases.trans_date)
        .filter_by(store_id=session["store"])
        .group_by(InvPurchases.trans_date)
    )
    ordered_purchases = purchase_dates.order_by(InvPurchases.trans_date.desc()).paginate(
        page=page, per_page=10
    )

    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.purchases"))

    item_list = db.session.query(InvItems.id, InvItems.item_name).filter(InvItems.store_id == session["store"]).all()
    if(item_list == []):
        flash("You must add items to your inventory before you can count them!", "warning")
        return redirect(url_for("counts_blueprint.new_item")
        )
    
    multi_form = PurchasesForm(purchases=item_list)
    index = 0
    for form in multi_form.purchases:
        form.itemname.data = item_list[index].item_name
        form.item_id.data = item_list[index].id
        index += 1
        
    del index
    
    if multi_form.validate_on_submit():
        # Check if sales exists for same day and time
        #for each sales entry, check if it already exists
        for purchase_entry in multi_form.purchases.data:
            double_purchase = InvPurchases.query.filter_by(
                item_id=purchase_entry["item_id"],
                trans_date=multi_form.transdate.data,
            ).first()
            ic(double_purchase)
            if double_purchase is not None:
                flash(
                    f"{purchase_entry['itemname']} already has a purchase on {multi_form.transdate.data}, please enter a different date or edit the existing purchase!",
                    "warning",
                )
                return redirect(url_for("counts_blueprint.purchases"))
        
        for purchase_entry in multi_form.purchases.data:
            items_object = InvItems.query.filter_by(id=purchase_entry["item_id"]).first()
            ic(items_object.case_pack)
            purchase_item = InvPurchases(
                trans_date=multi_form.transdate.data,
                item_name=purchase_entry["itemname"],
                case_count=purchase_entry["casecount"],
                each_count=purchase_entry["eachcount"],
                purchase_total=(
                    items_object.case_pack * purchase_entry["casecount"] + purchase_entry["eachcount"]
                ),
                item_id=purchase_entry["item_id"],
                store_id=session["store"],
            )
            
            db.session.add(purchase_item)
        db.session.commit()
        # flash(
        #         f"Sales of {sales_form.eachcount.data + sales_form.waste.data} {sales_form.itemname.data.item_name} submitted on {multi_form.transdate.data}!",
        #         "success",
        #         )
        items_object = InvItems.query.filter_by(id=purchase_entry['item_id']).all()
        for item in items_object:
            calculate_totals(item.id)
        return redirect(url_for("counts_blueprint.purchases"))
    return render_template(
        "counts/purchases.html",
        title="Purchases",
        **locals(),
    )


@blueprint.route("/purchases/<int:purchase_id>/update", methods=["GET", "POST"])
@login_required
def update_purchases(purchase_id):
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    item = InvPurchases.query.get_or_404(purchase_id)
    if not item.item_id:
        flash(f"{item.item_name} is not an active product!", "warning")
        return redirect(url_for("counts_blueprint.purchases"))
    inv_items = InvPurchases.query.filter(
        InvPurchases.store_id == session["store"]
    ).all()

    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.purchases"))

    form = UpdatePurchasesForm()
    if form.validate_on_submit():
        items_object = InvItems.query.filter_by(id=form.item_id.data).first()
        ic(items_object)
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
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
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
    current_location = Restaurants.query.filter_by(id=session["store"]).first()

    # crate list of daily sales
    page = request.args.get("page", 1, type=int)
    sales_list = InvSales.query.filter(InvSales.store_id == session["store"]).all()
    sales_dates = (
        db.session.query(InvSales.trans_date)
        .filter_by(store_id=session["store"])
        .group_by(InvSales.trans_date)
    )
    ordered_sales = sales_dates.order_by(InvSales.trans_date.desc()).paginate(
        page=page, per_page=10
    )

    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.sales"))

    # create sales form for input
    item_list = db.session.query(InvItems.id, InvItems.item_name).filter(InvItems.store_id == session["store"]).all()
    if(item_list == []):
        flash("You must add items to your inventory before you can count them!", "warning")
        return redirect(url_for("counts_blueprint.new_item")
        )

    multi_form = SalesForm(sales=item_list)
    index = 0
    for form in multi_form.sales:
            form.itemname.data = item_list[index].item_name
            form.item_id.data = item_list[index].id
            index += 1
            
    del index

    if multi_form.validate_on_submit():
        # Check if sales exists for same day and time
        #for each sales entry, check if it already exists
        for sales_entry in multi_form.sales.data:
            double_sales = InvSales.query.filter_by(
                item_id=sales_entry["item_id"],
                trans_date=multi_form.transdate.data,
            ).first()
            ic(double_sales)
            if double_sales is not None:
                flash(
                    f"{sales_entry['itemname']} already has a sales on {multi_form.transdate.data}, please enter a different date or edit the existing sales!",
                    "warning",
                )
                return redirect(url_for("counts_blueprint.sales"))
        
        for sales_entry in multi_form.sales.data:
            ic(sales_entry.items())
            sale_item = InvSales(
                trans_date=multi_form.transdate.data,
                item_name=sales_entry["itemname"],
                each_count=sales_entry["eachcount"],
                waste=sales_entry["waste"],
                sales_total=(sales_entry["eachcount"] + sales_entry["waste"]),
                item_id=sales_entry["item_id"],
                store_id=session["store"],
            )
            # ic(sale_item.item_id, sale_item.item_name, sale_item.sales_total)
            db.session.add(sale_item)
        db.session.commit()
        # flash(
        #         f"Sales of {sales_form.eachcount.data + sales_form.waste.data} {sales_form.itemname.data.item_name} submitted on {multi_form.transdate.data}!",
        #         "success",
        #         )
        unit = InvItems.query.filter_by(id=sales_entry['item_id']).all()
        for item in unit:
            calculate_totals(item.id)
        return redirect(url_for("counts_blueprint.sales"))

    ic(multi_form.errors)
    return render_template(
        "counts/sales.html",
        title="Sales",
        **locals(),
    )


@blueprint.route("/sales/<int:sales_id>/update", methods=["GET", "POST"])
@login_required
def update_sales(sales_id):
    """Update sales items"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    item = InvSales.query.get_or_404(sales_id)
    if not item.item_id:
        flash(f"{item.item_name} is not an active product!", "warning")
        return redirect(url_for("counts_blueprint.sales"))
    inv_items = InvSales.query.all()
    form = UpdateSalesForm()
    store_form = StoreForm()

    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.sales"))

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
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
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
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
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
        flash(
            f"{form.itemname.data.name} has been added to your stockcount items list!",
            "success",
        )
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
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
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
    # TODO: method to delete all counts for an item
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    inv_items = InvItems.query.filter(InvItems.store_id == session["store"]).all()
    item = InvItems.query.get_or_404(item_id)
    counts = InvCount.query.filter_by(item_id=item.id).all()
    store_form = StoreForm()

    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.new_item"))

    if counts is not None:
        for count in counts:
            db.session.delete(count)
        
        db.session.commit()

    db.session.delete(item)
    db.session.commit()
    flash("Product has been 86'd!", "success")
    return redirect(url_for("counts_blueprint.new_item"))
