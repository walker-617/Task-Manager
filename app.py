from flask import Flask, render_template, request, url_for, redirect, flash, session, json, jsonify, abort, Response
import pymongo

import os
from datetime import timedelta
from authlib.integrations.flask_client import OAuth
import operator

from bson import ObjectId
from bson.binary import Binary

from datetime import datetime

import gridfs

client = pymongo.MongoClient(
    "Your mongodb link here")
db = client["HOD-Portal"]

fs = gridfs.GridFS(db)

app = Flask(__name__)

global client_id
global client_secret

HOD_Email = "manjusha@nitc.ac.in"
HOD_Password = "manjusha_617"

client_id = "client id here"
client_secret = "client secret here"

# Session config
app.secret_key = "walker"
app.config['SESSION_COOKIE_NAME'] = 'google-login-session'
# ======================================================================

# oAuth Setup
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=client_id,
    client_secret=client_secret,
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
    client_kwargs={'scope': 'email profile'},
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
)


def isLoggedIN():
    try:
        user = dict(session).get('profile', None)
        if user:
            return True
        else:
            return False
    except Exception as e:
        return False


def isHODLoggedIN():
    if "user_id" in session:
        return True
    return False


@app.route('/login')
def login():
    google = oauth.create_client('google')  # create the google oauth client
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/authorize')
def authorize():
    google = oauth.create_client('google')  # create the google oauth client
    # Access token from google (needed to get user info)
    token = google.authorize_access_token()
    # userinfo contains stuff u specificed in the scrope
    resp = google.get('userinfo')
    user_info = resp.json()
    user = oauth.google.userinfo()  # uses openid endpoint to fetch user info
    session['profile'] = user_info
    # make the session permanant so it keeps existing after broweser gets closed
    session.permanent = True
    user = dict(session).get('profile', None)
    email = user["email"]
    coll = db["faculty"]
    x = list(coll.find({"email": email}))
    if len(x):
        return redirect(url_for('faculty', user=user))
    return redirect('/')


@app.route('/logout')
def logout():
    for key in list(session.keys()):
        session.pop(key)
    return redirect('/')


@app.route('/', methods=["POST", "GET"])
def login_page():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if email == HOD_Email or password == HOD_Password:
            session['user_id'] = email
            return redirect("/HOD")
    return render_template("login.html")


@app.route('/HOD', methods=["POST", "GET"])
def index():
    if not isHODLoggedIN():
        return redirect('/')
    arch_title = request.args.get("arch_title")
    del_title = request.args.get("del_title")
    coll = db["created_tasks"]
    arch_rec = list(coll.find({"title": arch_title}))
    del_rec = list(coll.find({"title": del_title}))
    if len(arch_rec):
        coll.delete_one({"title": arch_title})
        x = arch_rec[0]["faculty"]
        for faculty in x:
            coll = db["faculty"]
            tasks = coll.find_one({"name": faculty})["tasks"]
            tasks.remove(arch_title)
            coll.update_one({"name": faculty}, {"$set": {"tasks": tasks}})
        coll = db["archives"]
        coll.insert_one(arch_rec[0])
    if len(del_rec):
        x = coll.find_one({"title": del_title})["faculty"]
        for faculty in x:
            coll = db["faculty"]
            tasks = list(coll.find({"name": faculty}))[0]["tasks"]
            tasks.remove(del_title)
            coll.update_one({"name": faculty}, {"$set": {"tasks": tasks}})
        coll = db["created_tasks"]
        coll.delete_one({"title": del_title})
        coll = db["reports"]
        coll.delete_many({"title": del_title})
    coll = db["created_tasks"]
    data = list(coll.find({}))
    for task in data:
        task["faculty"] = json.dumps(task["faculty"])
    return render_template("HOD.html", data=data)


@app.route('/edit_task', methods=["POST", "GET"])
def edit_task():
    if not isHODLoggedIN():
        return redirect('/')
    x = request.args.get("edit_data")
    if x:
        edit_data = json.loads(x)
        org_title = edit_data["org_title"]
        coll = db["created_tasks"]
        coll.delete_one({"title": org_title})
        org_faculty = edit_data["org_faculty"]
        coll = db["faculty"]
        for x in org_faculty:
            tasks = list(coll.find({"name": x}))[0]["tasks"]
            tasks.remove(org_title)
            coll.update_one({"name": x}, {"$set": {"tasks": tasks}})
        edit_data.pop("org_title")
        edit_data.pop("org_faculty")
        coll = db["created_tasks"]
        coll.insert_one(edit_data)
        coll = db["faculty"]
        faculty = edit_data["faculty"]
        for x in faculty:
            tasks = list(coll.find({"name": x}))[0]["tasks"]
            tasks.append(edit_data["title"])
            coll.update_one({"name": x}, {"$set": {"tasks": tasks}})
        return redirect(url_for("index"))
    title = request.args.get("edit_title")
    coll = db["created_tasks"]
    data = list(coll.find({"title": title}))[0]
    sel_faculty = list(data["faculty"].keys())
    coll = db["faculty"]
    cur = coll.find({}, {"_id": 0, "name": 1})
    all_faculty = [doc['name'] for doc in cur]
    avail_faculty = []
    for x in all_faculty:
        if x not in sel_faculty:
            avail_faculty.append(x)
    data["all_faculty"] = all_faculty
    data["sel_faculty"] = sel_faculty
    return render_template("edit_task.html", data=data)


@app.route('/create_task', methods=["POST", "GET"])
def create_task():
    if not isHODLoggedIN():
        return redirect('/')
    x = request.args.get("data")
    if x:
        data = json.loads(x)
        coll = db["created_tasks"]
        coll.insert_one(data)
        faculty = data["faculty"]
        coll = db["faculty"]
        for x in faculty:
            tasks = list(coll.find({"name": x}))[0]["tasks"]
            tasks.append(data["title"])
            coll.update_one({"name": x}, {"$set": {"tasks": tasks}})
        return redirect(url_for("create_task"))
    coll = db["faculty"]
    cur = coll.find({"avail": "y"})
    data = []
    for doc in cur:
        data.append({"name": doc['name'], "tasks": len(doc["tasks"])})
    data.sort(key=operator.itemgetter("tasks"))
    print(data)
    return render_template("create_task.html", data=data)


@app.route('/create_faculty', methods=["POST", "GET"])
def create_faculty():
    if not isHODLoggedIN():
        return redirect('/')
    if request.method == "POST":
        rec = request.form.to_dict()
        rec["avail"] = "y"
        rec["tasks"] = []
        coll = db["faculty"]
        coll.insert_one(rec)
        return redirect(url_for("create_faculty"))
    return render_template("create_faculty.html")


@app.route('/archives', methods=["POST", "GET"])
def archives():
    if not isHODLoggedIN():
        return redirect('/')
    coll = db["archives"]
    data = list(coll.find({}))
    for task in data:
        task["faculty"] = json.dumps(task["faculty"])
    return render_template("archives.html", data=data)


@app.route('/re_assign', methods=["POST", "GET"])
def re_assign():
    if not isHODLoggedIN():
        return redirect('/')
    x = request.args.get("re_ass_data")
    if x:
        re_ass_data = json.loads(x)
        title = re_ass_data["title"]
        coll = db["archives"]
        coll.delete_one({"title": title})
        coll = db["faculty"]
        re_ass_data.pop("org_faculty")
        faculty = re_ass_data["faculty"]
        coll = db["created_tasks"]
        coll.insert_one(re_ass_data)
        coll = db["faculty"]
        for x in faculty:
            tasks = list(coll.find({"name": x}))[0]["tasks"]
            tasks.append(re_ass_data["title"])
            coll.update_one({"name": x}, {"$set": {"tasks": tasks}})
        return redirect(url_for("archives"))
    title = request.args.get("re_ass_title")
    coll = db["archives"]
    data = list(coll.find({"title": title}))[0]
    sel_faculty = list(data["faculty"].keys())
    coll = db["faculty"]
    cur = coll.find({"avail": "y"}, {"_id": 0, "name": 1})
    all_faculty = [doc['name'] for doc in cur]
    avail_faculty = []
    for x in all_faculty:
        if x not in sel_faculty:
            avail_faculty.append(x)
    data["all_faculty"] = all_faculty
    data["sel_faculty"] = sel_faculty
    return render_template("re_assign.html", data=data)


@app.route('/view_reports', methods=["POST", "GET"])
def view_reports():
    if not isHODLoggedIN():
        return redirect('/')
    title = request.args.get("rep_title")
    coll = db["reports"]
    reports = list(coll.find({"title": title}))
    reports.reverse()
    data = {}
    data["title"] = title
    data["reports"] = reports
    return render_template("view_reports.html", data=data)


@app.route('/view')
def view():
    if not isHODLoggedIN():
        return redirect('/')
    file_id = request.args.get("file_id")
    file = fs.get(ObjectId(file_id))
    return Response(file, mimetype='application/pdf')


@app.route('/HOD_notifications', methods=["POST", "GET"])
def HOD_notifications():
    if not isHODLoggedIN():
        return redirect('/')
    return render_template("HOD_notifications.html")


@app.route('/FACULTY_notifications', methods=["POST", "GET"])
def FACULTY_notifications():
    if not isLoggedIN():
        return redirect('/')
    data = {}
    user = dict(session).get('profile', None)
    data["picture"] = user["picture"]
    return render_template("FACULTY_notifications.html", data=data)


@app.route('/faculty_info', methods=["POST", "GET"])
def faculty_info():
    if not isHODLoggedIN():
        return redirect('/')
    avail = "y"
    if "avail" in request.args:
        avail = request.args["avail"]
    coll = db["faculty"]
    data = list(coll.find({"avail": avail}))
    return render_template("faculty_info.html", data=data, avail=avail)


@app.route('/make_unavail')
def make_unavail():
    if not isHODLoggedIN():
        return redirect('/')
    faculty = request.args["faculty"]
    coll = db["faculty"]
    coll.update_one({"name": faculty}, {"$set": {"avail": "n"}})
    return redirect(url_for('faculty_info', avail="y"))


@app.route('/make_avail')
def make_avail():
    if not isHODLoggedIN():
        return redirect('/')
    faculty = request.args["faculty"]
    coll = db["faculty"]
    coll.update_one({"name": faculty}, {"$set": {"avail": "y"}})
    return redirect(url_for('faculty_info', avail="n"))


@app.route('/faculty', methods=["POST", "GET"])
def faculty():
    if not isLoggedIN():
        return redirect('/')
    user = dict(session).get('profile', None)
    picture = user["picture"]
    email = user["email"]
    coll = db["faculty"]
    x = coll.find_one({"email": email})
    coll = db["created_tasks"]
    tasks = []
    objs = []
    for task in x["tasks"]:
        k = coll.find_one({"title": task})
        tasks.append(k)
        objs.append(k["faculty"][x["name"]])
    data = {}
    data["name"] = x["name"]
    data["tasks"] = tasks
    data["objs"] = objs
    data["picture"] = picture
    return render_template("FACULTY.html", data=data)


@app.route('/view_details')
def view_details():
    if not isLoggedIN():
        return redirect('/')
    user = dict(session).get('profile', None)
    email = user["email"]
    coll = db["faculty"]
    data = coll.find_one({"email": email})
    data["picture"] = user["picture"]
    return render_template("view_details.html", data=data)


@app.route('/edit_details', methods=["POST", "GET"])
def edit_details():
    if not isLoggedIN():
        return redirect('/')
    user = dict(session).get('profile', None)
    email = user["email"]
    if request.method == "POST":
        dob = request.form.get("dob")
        phone = request.form.get("phone")
        gender = request.form.get("gender")
        if not gender:
            gender = "prefer not to say"
        coll = db["faculty"]
        coll.update_one({"email": email}, {
                        "$set": {"dob": dob, "phone": phone, "gender": gender}})
        coll = db["created_tasks"]
        return redirect(url_for("view_details"))
    coll = db["faculty"]
    data = coll.find_one({"email": email})
    data["picture"] = user["picture"]
    return render_template("edit_details.html", data=data)


@app.route('/report', methods=["POST", "GET"])
def report():
    if not isLoggedIN():
        return redirect('/')
    x = request.args.get("data")
    data = json.loads(x)
    title = data["title"]
    name = data["name"]
    coll = db["created_tasks"]
    task = coll.find_one({"title": title})
    data = {}
    data["task"] = task
    data["name"] = name
    if request.method == "POST":
        x = request.files["report"]
        file_id = fs.put(x.read(), filename="report")
        coll = db["reports"]
        now = datetime.now()
        date_time = now.strftime("%d/%m/%Y %H:%M:%S")
        coll.insert_one({"title": title, "name": name,
                        "file_id": file_id, "time": date_time})
        return redirect(url_for("faculty"))
    user = dict(session).get('profile', None)
    data["picture"] = user["picture"]
    return render_template("report.html", data=data)


if __name__ == "__main__":
    app.run(debug='True')
