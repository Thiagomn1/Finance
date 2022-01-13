import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import sys

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():

    portfolio = db.execute("SELECT * from stocks WHERE user_id = ?", session["user_id"])
    users = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])

    return render_template("index.html", portfolio=portfolio, users=users)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    if request.method == "GET":
        return render_template("buy.html")


    if request.method =="POST":

        userid = session["user_id"]
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        shares = request.form.get("shares")

        if quote == None:
            return apology("This is not a valid Symbol", 400)

        elif not shares.isdigit():
            return apology("Invalid amount", 400)

        balance = db.execute("SELECT cash FROM users WHERE id = ?", userid)
        value = quote['price'] * float(shares)

        if value > float(balance[0]['cash']):
            return apology("You don't have enough balance", 403)

        finalbalance = float(balance[0]['cash']) - value
        db.execute("UPDATE users SET cash = ? WHERE id = ?", finalbalance, userid)

        db.execute("INSERT INTO purchases (user_id, operation, symbol, price, shares) VALUES (?, ?, ?, ?, ?)", userid, 'BUY', quote['symbol'], quote['price'], shares)

        portfolio = db.execute("SELECT * FROM stocks WHERE user_id = ? AND symbol = ? ", userid, symbol)

        if not portfolio:
            db.execute("INSERT INTO stocks (user_id, symbol, shares, value) VALUES (?, ?, ?, ?)", userid, quote['symbol'], shares, value)

        else:
            totalshares = float(shares) + float(portfolio[0]['shares'])
            finalvalue = float(value) + float(portfolio[0]['value'])
            db.execute("UPDATE stocks SET shares = ?, value = ? WHERE symbol = ? AND user_id = ?", totalshares, finalvalue, symbol, userid)

        return redirect("/")


@app.route("/history")
@login_required
def history():

    userid = session["user_id"]

    purchases = db.execute("SELECT operation, symbol, price, shares FROM purchases WHERE user_id = ?", userid)

    return render_template("history.html", purchases=purchases)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")

    if request.method == "POST":
        quote = request.form.get("symbol")
        value = lookup(quote)

        if value == None:
            return apology("This is not a valid Symbol", 400)


        return render_template("quoted.html", value=value)



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide username", 400)

        if not request.form.get("password"):
            return apology("must provide password", 400)

        if not request.form.get("confirmation"):
            return apology("must provide password confirmation", 400)

        username = request.form.get("username")
        confirmation = request.form.get("confirmation")
        password = request.form.get("password")

        if len(password) < 6:
            return apology("password too short", 400)

        if not any(x.isupper() for x in password):
            return apology("password must contain a capital letter", 400)

        if confirmation != password:
            return apology("password do not match", 400)

        usernamedb = db.execute("SELECT username FROM users WHERE username = ?", username)

        if not usernamedb:

            pwhash = generate_password_hash(password)

            rows = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, pwhash)

        else:
            return apology("username already exists", 400)

        return redirect("/")

    if request.method == "GET":
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    if request.method == "POST":
        userid = session["user_id"]
        quote = lookup(request.form.get("symbol"))
        shares = request.form.get("shares")

        if quote == None:
            return apology("This is not a valid Symbol", 400)

        if not shares.isdigit():
            return apology("Invalid amount", 400)

        else:

            sale = quote["price"] * float(shares)
            balance = db.execute("SELECT cash FROM users WHERE id = ?", userid)

            if float(sale) > balance[0]['cash']:
                return apology("You don't have enough balance", 400)

            # Updates the user balance
            finalbalance = float(balance[0]['cash']) + sale
            db.execute("UPDATE users SET cash = ? WHERE id = ?", finalbalance, userid)

            # Updates owned shares in the user portfolio
            owned = db.execute("SELECT shares, value FROM stocks WHERE user_id = ? AND symbol = ?", userid, quote['symbol'])

            if float(shares) > float(owned[0]['shares']):
                return apology("You don't have enough shares", 400)

            if float(shares) == float(owned[0]['shares']):
                db.execute("DELETE from stocks WHERE user_id = ? AND symbol = ?", userid, quote['symbol'])

            else:
                finalshares = float(owned[0]['shares']) - float(shares)
                finalvalue = float(owned[0]['value']) - float(sale)
                db.execute("UPDATE stocks SET shares = ?, value = ? WHERE user_id = ? and symbol = ?", finalshares, finalvalue, userid, quote['symbol'])

            # Add transaction to history
            db.execute("INSERT INTO purchases (user_id, operation, symbol, price, shares) VALUES (?, ?, ?, ?, ?)", userid, 'SELL', quote['symbol'], quote['price'], shares)

        return redirect("/")

    if request.method == "GET":

        stocks = db.execute("SELECT symbol FROM stocks WHERE user_id = ?", session["user_id"])
        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
