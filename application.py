from __future__ import print_function
import datetime
from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools


import os
import json

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session, Response
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash
from flask_mail import Mail, Message


from helpers import apology, login_required

# Configure application
app = Flask(__name__)


# Sets up the mail settings so that we can notify users and bars via e-mail.
mail_settings = {
    "MAIL_SERVER": 'smtp.gmail.com',
    "MAIL_PORT": 465,
    "MAIL_USE_TLS": False,
    "MAIL_USE_SSL": True,
    "MAIL_USERNAME": 'helpteam.vamos@gmail.com',
    "MAIL_PASSWORD": 'sonmurroq1907'
}

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config.update(mail_settings)
mail = Mail(app)

# Ensure responses aren't cached


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///eventbar.db")


# Returns VAMOS! Homepage, where users can log in
@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("homepage.html")


# Leads users to index page when they log in. They can see a list and map of the events going on here.
@app.route("/user", methods=["GET", "POST"])
@login_required
def user():
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Render user template with the events based on the user's input (user search)
        typeofevent = request.form.get("typeofevent")
        orderby = request.form.get("orderby")
        startday = request.form.get("startday")
        endday = request.form.get("endday")
        events = search(typeofevent, startday, endday, orderby)

        return render_template("user.html", events=events, eventsjson=json.dumps(events))
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        events = search('', '', '', '')
        return render_template("user.html", events=events, eventsjson=json.dumps(events))


# Helper function to retrieve a list of events and their caracteristics based on some search parameters (user's search criteria)
def search(typeofevent, startday, endday, orderby):
    # creates a query by appending different SQL commands to a general query. If no parameters are given the functions returns all the events in the database.
    if not typeofevent:
        typeofevent = " "
    else:
        typeofevent = "AND events.type= '" + typeofevent + "'"

    # As the user can search by a specific day or by an interval of two days (startday and endday) the query has to change accordingly.
    if not endday:
        if not startday:
            day = " "
        else:
            day = "AND events.date LIKE '" + startday + "%'"
    else:
        day = "AND '"+startday+"' < events.date AND events.date < '"+endday+"'"

    if not orderby:
        orderby = " "
    else:
        orderby = "ORDER BY " + orderby

    query = "SELECT events.name, events.type, events.date, events.capacity, events.description, bars.address, bars.bar_name FROM bars,events WHERE events.id_bar=bars.id " + typeofevent + day + orderby
    events = db.execute(query)
    return events


@app.route("/advancedsearch", methods=["GET"])
@login_required
def advancedsearch():
    return render_template("advancedsearch.html")


# Allows bars to add new events that they will host, save them in the database and include them in a Google calendar
@app.route("/addEvent", methods=["GET", "POST"])
@login_required
def addEvent():
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # List of values of the new event that the bar inputs
        eventName = request.form.get("name")
        eventType = request.form.get("type")
        startdate = request.form.get("startdate") + ":00"
        enddate = request.form.get("enddate") + ":00"
        capacity = request.form.get("capacity")
        description = request.form.get("description")

        # Checks that bar has inputted the neccessary values before saving the new event.
        if not eventName:
            return apology("You must provide an event name", 403)
        if not eventType:
            return apology("You must provide an event type", 403)
        if not startdate:
            return apology("You must provide the date of the event", 403)
        if not enddate:
            return apology("You must provide the end date of the event", 403)
        if not capacity:
            return apology("You must state the capacity of the event", 403)
        if not description:
            return apology("You must give a description of the event", 403)

        # Checks that the start date is before than the end date of the event.
        if enddate < startdate:
            return apology("Your end date must be after your first date", 403)

        # Formating dates for including them in the database
        startdatedb = startdate.replace("T", " ")
        enddatedb = enddate.replace("T", " ")

        # Insert event in database
        db.execute("INSERT INTO events (id_bar, name, type, date, capacity, description,enddate) VALUES (:uId, :name, :eType, :date, :capacity, :description, :enddate)",
                   uId=session["user_id"], name=eventName, eType=eventType, date=startdatedb, capacity=capacity, description=description, enddate=enddatedb)

        # Authenticating to use the google Calendar API by using an access token and credentials stored in the files credentials.json and token.json
        SCOPES = 'https://www.googleapis.com/auth/calendar'
        store = file.Storage('token.json')
        creds = store.get()
        if not creds or creds.invalid:
            flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
            creds = tools.run_flow(flow, store)
        service = build('calendar', 'v3', http=creds.authorize(Http()))

        # Setting the event in the Google Calendar format
        event = {
            'summary': eventName,
            'description': description + "\nType of event: "+eventType + "\nCapacity: "+capacity,
            'start': {
                'dateTime': startdate,
                'timeZone': 'America/New_York',
            },
            'end': {
                'dateTime': enddate,
                'timeZone': 'America/New_York',
            },


            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 120},
                    {'method': 'popup', 'minutes': 60},
                ],
            },
        }
        # Add the event to a google Calendar
        event = service.events().insert(calendarId='college.harvard.edu_0vudnc3sm0evvu7ijdv20op17o@group.calendar.google.com', body=event).execute()

        return redirect("/calendar")
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("addEvent.html")


# When bars log-in, this page shows them a list of the events that they have hosted or that they will host
@app.route("/calendar", methods=["GET"])
@login_required
def calendar():
    # Gets from the database all of the bar's events
    events = db.execute("SELECT * FROM events WHERE id_bar = :checkId ORDER BY date", checkId=session["user_id"])

    # Returns template with list of dictionaries with events' data
    return render_template("calendar.html", events=events)


# Checks that a new username has not already been taken by another user or bar.
@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""

    # Gets the inputted username and whether the user is a bar or a customer
    inputusername = request.args.get("username")
    usertype = request.args.get("usertype")

    # Using the type of user as a variable, returns in JSON format whether ther username is taken or not
    if db.execute("SELECT username FROM :usertype WHERE username=:username", username=inputusername, usertype=usertype) == []:
        return jsonify(True)
    else:
        return jsonify(False)


# When registering a new user, this function checks whether it is a user or a bar who wants to register.
@app.route("/checkType", methods=["GET"])
def checkType():
    """Return true if bar was chosen, else false, in JSON format"""
    chosenType = request.args.get("uType")
    if chosenType == "bars":
        return jsonify(True)
    else:
        return jsonify(False)


# Route is necessary when user wants to "See Bars Information" to send the necessary data to the profile HTML
@app.route("/checkBar", methods=["GET", "POST"])
@login_required
def checkBar():

    # appBars gets all of the bars registered in the applicaiton to display them in the drop-down menu
    appBars = db.execute("SELECT bar_name FROM bars ORDER BY bar_name")
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Gets the name of the chosen bar
        barName = request.form.get("bar")

        # Gets the data from the correspoding bar and shares a dictionary with its information to the profile HTML
        barInfo = db.execute("SELECT * FROM bars WHERE bar_name = :name", name=barName)
        bars = barInfo[0]

        # Because a user is who is looking at the bar's profile, it is redirected to see_bar_profile.html
        return render_template("see_bar_profile.html", bars=bars, barsjson=json.dumps(bars))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("check_bar.html", appBars=appBars)


# This route lets users to access profiles by clicking an href link
@app.route("/linkProfile", methods=["GET"])
@login_required
def linkProfile():

    # Gets in argument form the name of the bar and whether the profile is being accessed by a bar or a user.
    barName = request.args.get("barName")
    userT = request.args.get("userType")

    # Gets list with a dictionary of the data from the respective bar
    barInfo = db.execute("SELECT * FROM bars WHERE bar_name = :name", name=barName)

    # Returns error if there is no bar information to display
    if not barInfo:
        return apology("Could not find bar", 403)
    else:
        # Gets dictionary from list
        bars = barInfo[0]

        # Returns see_bar_profile.html if the profile is being seen by a user and see_my_bar.html if its being seen by a bar
        if userT == "users":
            return render_template("see_bar_profile.html", bars=bars, barsjson=json.dumps(bars))
        else:
            return render_template("see_my_bar.html", bars=bars, barsjson=json.dumps(bars))


# Route allows users and bars to login
@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Checks whether a useror a bar is logging in
        uType = request.form.get("userType")

        # Checks that a user type was given. Else, it returns an error message
        if not uType:
            return apology("must select customer or bar", 403)

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        searchU = "SELECT * FROM " + uType + " WHERE username = :username"

        # Query database for username
        rows = db.execute(searchU, username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        if (uType == "users"):
            return redirect("/user")
        else:
            return redirect("/calendar")

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


@app.route("/getUserData", methods=["GET"])
@login_required
def getUserData():
    """Return a dictionary with the elements of the bar"""

    # Gets the current information of the bar to display it when the bar wants to see its profile.
    bars = db.execute("SELECT * FROM bars WHERE id = :checkId", checkId=session["user_id"])
    barsDict = bars[0]

    return jsonify(barsDict)


@app.route("/editProfile", methods=["GET", "POST"])
@login_required
def editProfile():

    barInfo = db.execute("SELECT bar_name FROM bars WHERE id = :barId", barId=session["user_id"])
    bars = barInfo[0]

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        website = request.form.get("website")
        phone = request.form.get("phone")
        openTime = request.form.get("oTime")
        closeTime = request.form.get("cTime")
        street = request.form.get("street")
        city = request.form.get("city")
        state = request.form.get("state")
        zipCode = request.form.get("zip")
        picLink = request.form.get("picLink")

        # We only check for the elements that must be necessarily included.
        if not name:
            return apology("You must provide a name", 403)
        if not street:
            return apology("You must provide a street", 403)
        if not city:
            return apology("You must provide a city", 403)
        if not state:
            return apology("You must provide a state", 403)
        if not zipCode:
            return apology("You must provide a zip code", 403)

        # Give NULL value to unsubmitted information
        if not phone:
            phone = "NULL"
        if not email:
            email = "NULL"
        if not website:
            website = "NULL"
        if not phone:
            phone = "NULL"

        # Adds time and hour to opening/closing time or sets it NULL.
        if not openTime:
            openTime = "NULL"
        if not closeTime:
            closeTime = "NULL"

        # Puts address together
        address = street + ", " + city + ", " + state + " " + zipCode

        # Updates database
        db.execute("UPDATE bars SET bar_name = :name, address = :address, email = :email, phone = :phone, website =:website, " +
                   "picLink =:picLink, street =:street, city =:city, state =:state, zipCode =:zipCode, openHour = :openHour, " +
                   "closeHour = :closeHour WHERE id = :checkId", name=name, address=address, email=email, street=street, city=city,
                   state=state, zipCode=zipCode, phone=phone, website=website, picLink=picLink, openHour=openTime, closeHour=closeTime, checkId=session["user_id"])

        return render_template("bar_profile.html", bars=bars)

    else:
        return render_template("bar_profile.html", bars=bars)


# Registers a new user: bar or customer
@app.route("/register", methods=["GET", "POST"])
def register():
    "Register a bar or user"

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Check whether a bar or user is registering
        userType = request.form.get("userType")

        # Gets user data inputted when registering
        username = request.form.get("username")
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        passwordconfirm = request.form.get("confirmation")

        street = request.form.get("street")
        city = request.form.get("city")
        state = request.form.get("state")
        zipCode = request.form.get("zip")

        phone = request.form.get("phone")
        website = request.form.get("website")

        # Checks that the chosen username is available
        checkUser = "SELECT username FROM " + userType + " WHERE username=:username"
        if db.execute(checkUser, username=username) != []:
            return apology("This username is already taken", 403)

        # Ensures that necessary data was inputted
        if not username:
            return apology("You must provide a username", 403)
        if not email:
            return apology("You must provide an email", 403)
        if not password:
            return apology("You must provide a password", 403)
        if not passwordconfirm:
            return apology("You must provide a password confirmation", 403)
        if not street:
            return apology("You must provide a street", 403)
        if not city:
            return apology("You must provide a city", 403)
        if not state:
            return apology("You must provide a state", 403)
        if not zipCode:
            return apology("You must provide a zip code", 403)

        # Checks that the input password and the passwword confirmation are the same
        if password != passwordconfirm:
            return apology("The two passwords don't match", 403)
        hashpassword = generate_password_hash(password)

        # Gets user_type as a variable to either search for "name" or "bar_name," which are the different ways of saving the name
        # of bars in the users and bars tables
        if userType == "bars":
            user_type = "bar_name"
        else:
            user_type = "name"

        # Gets user's address by adding all the elements together.
        address = street + ", " + city + ", " + state + " " + zipCode

        # Makes string of command where the table that will be modified depends on the variable userType and thus, the name of the
        # bar name column also depends on the variable, user_type
        exeCommand = "INSERT INTO " + userType + " (username, hash, " + user_type + ", address, email, street, city, state, zipCode"

        # Executes different commands depending on whether a bar or a user is registering. The difference is that for bars, the
        # website and phone information is also saved.
        if userType == "bars":
            exeCommand += ", website, phone) VALUES (:username, :hashpassword, :name, :address, :email, :street, :city, :state, :zipCode, :website, :phone)"

            # References the editted executio strings to include them in the actual command to the database.
            # Remember which user has logged in
            session["user_id"] = db.execute(exeCommand, username=username, hashpassword=hashpassword, name=name, address=address,
                                            email=email, street=street, city=city, state=state, zipCode=zipCode, website=website, phone=phone)
        else:
            exeCommand += ") VALUES (:username, :hashpassword, :name, :address, :email, :street, :city, :state, :zipCode)"

            # Remember which user has logged in
            session["user_id"] = db.execute(exeCommand, username=username, hashpassword=hashpassword, name=name, address=address,
                                            email=email, street=street, city=city, state=state, zipCode=zipCode)

        # Redirects users to different pages, depending on whether they are customers or bars
        if userType == "bars":
            return redirect("/calendar")
        else:
            return redirect("/user")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/makereservation", methods=["GET", "POST"])
@login_required
def makereservation():
    # Allows users to make reservations for the events that the bars are hosting.

    # Selecting the events and grouping them by bar name so that we have a list of every bar hosting an event. Grouping by bar name prevents the repetition of a bar in the list.
    events = db.execute(
        "SELECT events.name, bars.bar_name, events.id, events.id_bar FROM bars,events WHERE bars.id = events.id_bar GROUP BY bar_name")

    if request.method == "GET":
        # Rendering makereservation page with the events list so that in the select menu, we can present all the bars hosting an event.
        return render_template("makereservation.html", events=events)

    if request.method == "POST":

        # Store the event the user selected in a variable.
        event = request.form.get("event")

        # Storing the capacity of the event selected in a variable.
        capacity = db.execute("SELECT capacity FROM events WHERE id =:id", id=event)

        # This code outputs the amount of rows having a specific event id that exists in the reservation table. This way we can calculate the number of people registered for an event.
        registeredcount = db.execute("SELECT Count(*) FROM reservations WHERE event_id =:id", id=event)

        capacity = capacity[0]["capacity"]
        registeredcount = registeredcount[0]["Count(*)"]

        # Checking if the capacity is higher than the people that have already registered for the event. In other words, checking if space is available for an event.
        if capacity > registeredcount:

            # If the user has already registered for an event, return an apology. This is checked by looking at the reservations database: if there is a row that stores both the specific id of the user and the event, the apology is returned.
            alreadyregistered = db.execute(
                "SELECT * FROM reservations WHERE user_id =:user_id AND event_id =:event_id", user_id=session["user_id"], event_id=event)
            if not alreadyregistered == []:
                return apology("You've already registered for this event!")

            # Insert the reservation details into the reservations list.
            reservationmade = db.execute("INSERT INTO reservations (user_id, event_id) VALUES(:user_id, :event_id)",
                                         user_id=session["user_id"], event_id=event)
            if not reservationmade:
                return apology("There was an error in the reservation process!")

            # Selecting and storing relevant information about the reservation so that the information could be used when sending out an e-mail.
            eventinfo = db.execute("SELECT name, date, id_bar FROM events WHERE id =:id", id=event)
            usersemail = db.execute("SELECT email FROM users WHERE id =:id", id=session["user_id"])
            barinfo = db.execute("SELECT bar_name, email FROM bars WHERE id =:id", id=eventinfo[0]["id_bar"])
            eventname = str(eventinfo[0]["name"])
            eventdate = str(eventinfo[0]["date"])
            barname = str(barinfo[0]["bar_name"])

            # Sends an e-mail to the user, confirming their reservation. The sender is the global variable defined up in application.py which is our e-mail address. The recipient is selected in the previous section according to the user_id. Subject linen and body includes certain placeholders for the details of the event.
            with app.app_context():
                msg = Message(subject="Reservation Confirmation for " + eventname + " | Vamos",
                              sender=app.config.get("MAIL_USERNAME"),
                              recipients=[str(usersemail[0]["email"])],
                              body="This mail is to notify you that you have reserved a space for the event " + eventname + " at " + barname + ". The event will take place at " + eventdate + ". You have to arrive 20 minutes before the event starts; otherwise, the bar has the right to withdraw your reservation.")
            mail.send(msg)

            # Adding one to the number of people who have already registered for the event.
            registeredcount += 1

            # If the capacity is reached after this specific registration, send an e-mail to the bar, letting that know that the capacity has been reached for their event.
            if registeredcount == capacity:
                with app.app_context():
                    msg = Message(subject="Event Capacity Reached for " + eventname + " | Vamos",
                                  sender=app.config.get("MAIL_USERNAME"),
                                  recipients=[str(barinfo[0]["email"])],
                                  body="This mail is to notify you that the capacity is reached for the event " + eventname + ".")
                mail.send(msg)

        else:
            return apology("There are no spaces left for this event! Sorry.")

        return render_template("successregistration.html")


@app.route("/eventlister")
@login_required
def eventlister():
    # This function listens for the bar the user chooses in the select and according the the chosen bar, sends out a list of events that the bar is hosting through jsonify.
    bar = request.args.get("bar")
    events = db.execute(
        "SELECT events.name, events.id FROM events, bars WHERE bars.id = events.id_bar AND bars.id=:bar", bar=bar)
    return jsonify(events)


@app.route("/myevents", methods=["GET", "POST"])
@login_required
def myevents():
    # Presents the events that the bar is hosting in a table.

    events = db.execute(
        "SELECT name, id FROM events WHERE events.id_bar=:id", id=session["user_id"])

    if request.method == "GET":
        # Return the events of the specific bar in an html that uses ginga to represent the events in a table.
        return render_template("myevents.html", events=events)

    # This part of the code is used if the bar wants to get an e-mail that shows the list of names attending their event.
    if request.method == "POST":

        # Get the selected event from the select menu.
        event = request.form.get("event")

        # Store the relevant information about the event so that they can be used while sending an e-mail to the bar.
        eventinfo = db.execute("SELECT name, date, id_bar FROM events WHERE id =:id", id=event)
        barinfo = db.execute("SELECT bar_name, email FROM bars WHERE id =:id", id=eventinfo[0]["id_bar"])
        registrantsinfo = db.execute(
            "SELECT users.name, users.email FROM reservations, users WHERE reservations.user_id = users.id AND reservations.event_id=:event", event=event)
        eventname = str(eventinfo[0]["name"])
        eventdate = str(eventinfo[0]["date"])
        barname = str(barinfo[0]["bar_name"])

        # Create a string called list of names and iterate through the registrantsinfo list in order to fill the string with the list of people attending the event.
        listofnames = "Here is the list of users who have made a reservation for your event: \n\n"
        for user in registrantsinfo:
            listofnames += "Name: " + str(user["name"]) + " | E-mail: " + str(user["email"]) + "\n"
        listofnames += "\n You have the right to withdraw the reservations of users who don't arrive earlier than 20 minutes. We hope everything goes well. Vamos!"

        # Send an e-mail to the bar that includes a list of people who are attending the event they've selected.
        with app.app_context():
            msg = Message(subject="List of Registrants for " + eventname + " | Vamos",
                          sender=app.config.get("MAIL_USERNAME"),
                          recipients=[str(barinfo[0]["email"])],
                          body=listofnames)
        mail.send(msg)

        return render_template("successsendmail.html")


@app.route("/eventtablelister")
@login_required
def eventtablelister():
    # This function listens for the event the user chooses in the select and according the the chosen event, sends out a list of users who have registered for the event through jsonify.
    event = request.args.get("event")
    events = db.execute(
        "SELECT users.name, users.email FROM reservations, users WHERE reservations.user_id = users.id AND reservations.event_id=:event", event=event)
    return jsonify(events)


@app.route("/newsFeed", methods=["GET"])
@login_required
def newsFeed():
    "Returns HTML of newsFeed"
    return render_template("newsFeed.html")


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
