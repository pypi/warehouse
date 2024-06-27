# System Architecture

Using the [C4 Model](https://c4model.com/) approach in [Mermaid syntax](https://mermaid.js.org/syntax/c4c.html).

_**Note**: These diagrams are best viewed in [light mode](https://github.com/mermaid-js/mermaid/issues/4906)._

## System Context Diagram

Represent items that **users** are most likely to interact with.
Some specifics have been omitted from the visual diagrams for clarity.
Items like: Kubernetes, Amazon Web Storage, deployment tooling, etc.

```{mermaid}
C4Context
  title System Context Diagram: Warehouse
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")

  Person_Ext(endUser, "End User", "human or machine")

  Enterprise_Boundary(b0, "External Services") {
    System_Ext(fastly, "Fastly", "Content Delivery Network")
    System_Ext(b2, "Backblaze B2", "Object store (cache)")
    System_Ext(s3, "AWS S3", "Object store (archive)")

    %% User's browser interacts with HIBP and GitHub - worth representing?
    %% System_Ext(hibp, "Have I Been Pwned", "breached username/password lookup")
    %% System_Ext(github_api, "GitHub API", "project stats lookup")

    Rel(fastly, b2, "fetch and cache response")
    Rel(fastly, s3, "fallback when B2 is either down or missing file")
    UpdateRelStyle(fastly, s3, $offsetX="-50", $offsetY="40")
  }

  Enterprise_Boundary(b1, "Warehouse Ecosystem") {
    System(warehouse, "Warehouse", "Multiple components")
  }

  BiRel(endUser, fastly, "Uses Web or API", "HTTPS")
  UpdateRelStyle(endUser, fastly, $offsetY="-30")
  Rel(fastly, warehouse, "proxies traffic to origin")
  UpdateRelStyle(fastly, warehouse, $offsetX="10", $offsetY="-20")

  BiRel(endUser, warehouse, "Uploads bypass Fastly", "HTTPS")
  UpdateRelStyle(endUser, warehouse, $offsetX="-80", $offsetY="-130")
```

Generally speaking, end users interact with the Warehouse ecosystem via Fastly,
which proxies traffic to the origin Warehouse instance.
Warehouse stores package files in Backblaze B2 and AWS S3.
Files are fetched and cached by Fastly.

B2 is used as primary storage for cost savings over S3 for egress,
as Backblaze has an agreement with Fastly to waive egress fees.

When a user uploads to warehouse, Fastly is bypassed
and the upload goes directly to the origin Warehouse instance.

## Warehouse Container Diagrams

_**Note**: A [Container diagram](https://c4model.com/#ContainerDiagram) is not a Docker container._

Let's dig into what makes up the Warehouse.
We'll split between the "web" and "worker" classes of services for clarity.

### Web Container Diagrams

On the web side, we run two types - the main web app, and the web uploads app.
The main difference between them is their `gunicorn` settings,
allowing the uploads app to handle larger file sizes and longer timeouts.

#### Web Container Diagram - `web`

On this diagram, we will only display a single web instance.
This serves the majority of end-user requests
and interactions with the web site & APIs.

We do not show the interactions with storage systems (B2, S3),
as responses will direct clients to the storage system directly
via URLs prefixed with: `https://files.pythonhosted.org/packages/...`
which are served by Fastly and cached.

```{mermaid}
C4Container
  title Container Diagram: Warehouse - Web 
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")

  Person_Ext(endUser, "End User", "human or machine")
  System_Ext(fastly, "Fastly", "Content Delivery Network")

  Container_Boundary(c1, "Warehouse & Supporting Systems") {
    Container(camo, "Camo", "image proxy")
    Container(web_app, "Web", "Python (Pyramid, SQLAlchemy)", "Delivers HTML and API content")
    SystemQueue(sqs, "AWS SQS", "task broker")
    SystemDb(opensearch, "OpenSearch", "Index of projects, packages, metadata")
    SystemDb(db, "Postgres Database", "Store project, package metadata, user details")
    SystemDb(redis, "Redis", "Store short-term cache data")

    Rel(web_app, sqs, "queue tasks")
    Rel(web_app, opensearch, "search for projects")
    Rel(web_app, db, "store/retrieve most data")
    Rel(web_app, redis, "cache data")
  }

  Rel(endUser, camo, "load images from project descriptions", "HTTPS")
  Rel(endUser, fastly, "Uses", "HTTPS")
  Rel(fastly, web_app, "proxies traffic to", "HTTPS")
```

#### Web Container Diagram - `web_uploads`

Here we show how a user might upload a file to the Warehouse.

```{mermaid}
C4Container
  title Container Diagram: Warehouse - Web Uploads
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")

  Person_Ext(endUser, "Client app", "e.g. twine, flit")

  Container_Boundary(c1, "Warehouse") {
    SystemDb(db, "Postgres Database", "Store project, package metadata, user details")
    Rel(web_app, db, "store/retrieve most data")

    Container(web_app, "Web", "Python (Pyramid, SQLAlchemy)", "Delivers HTML and API content")

    System(s3, "AWS S3", "Object store (archive)")
    Rel(web_app, s3, "stores package files")

    SystemQueue(sqs, "AWS SQS", "task broker")
    Rel(web_app, sqs, "queue sync to cache task")

    SystemDb(redis, "Redis", "Store short-term cache data")
    Rel(web_app, redis, "get/set rate limits and cache data")
  }

  Rel(endUser, web_app, "POST files and metadata", "HTTPS")
```

### Worker Container Diagram

Our workers use Celery to run tasks.
We run a single worker type, feeding off multiple queues.
We also use Celery Beat to schedule tasks.

We currently use AWS SQS as the queue,
and Redis as the result backend and schedule storage.

```{mermaid}
C4Container
  Container(worker_beat, "Worker - Beat", "Python, Celery", "keeps time, schedules tasks")
  Container(worker, "Worker", "Python, Celery", "runs tasks")

  Container_Boundary(c1, "Supporting Systems") {
    SystemDb(redis, "Redis", "Store short-term cache data")
    SystemQueue(sqs, "AWS SQS", "task broker")
    SystemDb(opensearch, "OpenSearch", "Index of projects, packages, metadata")
    SystemDb(db, "Postgres Database", "Store project, package metadata, user details")
    System(ses, "AWS SES", "Simple Email Service")
  }

  System_Ext(fastly, "Fastly", "Content Delivery Network")

  BiRel(worker, sqs, "get next task/ack")
  BiRel(worker, redis, "store task results")
  BiRel(worker, db, "interact with models")
  BiRel(worker, opensearch, "update search index")
  Rel(worker, fastly, "purge URLs")
  Rel(worker, ses, "send emails")

  BiRel(worker_beat, redis, "fetch/store task schedules")
  Rel(worker_beat, sqs, "schedule tasks")
```
