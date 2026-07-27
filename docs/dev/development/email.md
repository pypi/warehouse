# Working with E-mails

## Writing e-mails

Find a meaningful name for your email, we'll use
`something-awesome-happened`.

Create those 3 new templates in a folder named like your email:

- `warehouse/templates/email/something-awesome-happened/body.txt`
- `warehouse/templates/email/something-awesome-happened/subject.txt`
- `warehouse/templates/email/something-awesome-happened/subject.html`

Write these templates (as `jinja2` templates), take note of the context
variables you need.

Add a function in `warehouse/emails/__init__.py` that will take `request`
and `user` as well as any number of parameters, and will return the context
for rendering your email:

```python
@_email("something-awesome-happened")
def send_something_awesome_happened_email(
    request, user, *, arbitrary, arguments
):
    return {
        "arbitrary": arbitrary,
        "arguments": arguments,
    }
```

From your code, call that function.

## What it does

Calling a function with the `_email` decorator does the following:

- The email is sent from an asynchronous task, to avoid delaying the HTTP
  response
- A security log is added to the user's account
- The email is sent using Amazon SES (on production environment)
- A metric is sent to Datadog named `warehouse.emails.scheduled` with the tags
  `template_name`, `allow_unverified`, and `repeat_window`. If the email is
  skipped instead (missing email address, unverified address, or a repeat
  send within `repeat_window`), a `warehouse.emails.skipped` metric is sent
  with the same tags plus a `reason` tag.

## Testing e-mails

When an email is sent in the development environment, it's printed in the
console, and sent to the `mailpit` service using SMTP. `mailpit` is a
service defined in `docker-compose.yml` that receives emails, stores them and
lets you read them from a web interface at <http://localhost:1080>. Messages
are stored in a Docker volume so they persist across container recreations.
