""" error handler page """
from flask import render_template
from stockcount.authentication import blueprint


@blueprint.errorhandler(404)
def error_404(error):
    return render_template("errors/404.html"), 404


@blueprint.errorhandler(403)
def error_403(error):
    return render_template("errors/404.html"), 403


@blueprint.errorhandler(500)
def error_500(error):
    return render_template("errors/404.html"), 500
