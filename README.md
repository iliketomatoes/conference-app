App Engine application for the Udacity training course.

## Products
- [App Engine][1]

## Language
- [Python][2]

## APIs
- [Google Cloud Endpoints][3]

## Setup Instructions
1. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
1. Update the values at the top of `settings.py` to
   reflect the respective client IDs you have registered in the
   [Developer Console][4].
1. Update the value of CLIENT_ID in `static/js/app.js` to the Web client ID
1. (Optional) Mark the configuration files as unchanged as follows:
   `$ git update-index --assume-unchanged app.yaml settings.py static/js/app.js`
1. Run the app with the devserver using `dev_appserver.py DIR`, and ensure it's running by visiting
   your local server's address (by default [localhost:8080][5].)
1. Generate your client library(ies) with [the endpoints tool][6].
1. Deploy your application.


[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool

## Task 1

### Session and Speaker implementation:

Two models have been implemented to meet the Task-1 goals: Session and Speaker.
A structured property named SessionSpeaker has been used inside the Session's model.

Each Session object is stored as a Conference object's child. The only required property to
define when creating a new Session object is the *name* property.

When you decide to add a speaker to the Session object you are about to create, you are demanded to insert the speaker's *e-mail* at least. Speaker's name is not a required field.
**The speaker's email represent the Speaker entity key name and it must be unique.**

For clarity's sake let's say we want to add a Session called *Beer and cheese* to whatever conference. The speaker's name is *Mario Rossi* and his e-mail is *mariorossi@gmail.com*. 

When this kind of request makes it to our server, 3 different steps are performed:

1. We allocate a new Session ID for *Beer and cheese*, and we get its key.

2. We check if *mariorossi@gmail.com* inside the request body has a corresponding Speaker entity in our datastore. If not, we create a new Speaker entity with the given e-mail as the key name. Furthermore, we add the *Beer and cheese*'s websafe key to the *sessionKeysToAttend* Speaker's property. 

3. We also store some speaker's info directly into the *Beer and cheese* Session object, which has a SessionSpeaker structured property for doing that. Inside that property we store: the speaker's e-mail, *mariorossi@gmail.com*; the speaker's name (remember it's an optional field though), 'Mario Rossi'; the corresponding websafe Speaker key. 

This design let us store sessions and speakers as decoupled entities. This is because they have a many-to-many relationship. A session can have many speakers. A single speaker can attend many sessions. Since no *pivot tables* are meant to exist in a NoSQL database we have to store some speaker's info inside Session objects. Doing that is a virtue of necessity which allows us to reduce the reading operations from the datastore.  


## Task 3

Only one inequality filter per query is supported. Encountered both sessionType and startTime.


