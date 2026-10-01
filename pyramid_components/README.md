# pyramid_components

Reusable HTML/CSS/JS components for Pyramid + Jinja2 applications, inspired by
[django-components](https://github.com/django-components/django-components).

> v1 status: experimental. HTML + Python components only. On the roadmap: slots
> (block content via `{% component %}...{% endcomponent %}`) and a per-component
> JS/CSS dependency manager.

## Import convention

Always import the package namespaced as `pc`:

```python
import pyramid_components as pc
```

House style: `register` is an easy name to collide with, and the `pc` prefix keeps
component code greppable.

## Defining a component

```python
from dataclasses import field

import pyramid_components as pc


@pc.register("admin.stat_card")
class StatCard(pc.Component):
    template = "myapp.admin:components/stat_card/stat_card.html"

    class Props(pc.Props):
        color: str
        value: str
        icon: str = "fa-box"
        sublines: list[str] = field(default_factory=list)
        description: str | None = None
        footer_url: str | None = None
        footer_text: str = "View All"
        tooltip: str | None = None
```

`Props` becomes a dataclass automatically. `pc.Props` is a `dataclass_transform` marker
carrying no runtime behavior; inheriting it is what lets a type checker see that
conversion, so `StatCard.Props(color=..., value=...)` type-checks and a misspelled prop
is a checker error. A bare `class Props:` still works, but a checker then reads it as a
zero-argument constructor and flags every genuine call site.

Override `get_context` (a classmethod) only when a component needs to derive or reshape
data; the default exposes each prop to the template.

Namespace registration names by owner (`admin.stat_card`, not `stat_card`): all
components in a process share one registry, and a prefix keeps a second consumer from
colliding.

## Wiring into Pyramid

```python
config.add_jinja2_renderer(".html")   # must already exist; see below
config.include("pyramid_components")  # registers the {% component %} tag
```

The tag is registered on the renderer named by the `pyramid_components.renderer_name`
setting (default `.html`), via pyramid_jinja2's `add_jinja2_extension` directive.

That renderer has to be registered *before* the include. `config.include("pyramid_jinja2")`
on its own only registers `.jinja2`, so on a bare Configurator the include fails with
`AttributeError: 'NoneType' object has no attribute 'add_extension'`, which is
pyramid_jinja2 looking up an environment that was never built. Either call
`add_jinja2_renderer` for the name you want first (as above), or set
`pyramid_components.renderer_name = .jinja2` to use the renderer pyramid_jinja2
registers by default.

Under Pyramid, prefer asset-spec template paths (`myapp.admin:components/...`) as shown
above. pyramid_jinja2 resolves them directly, so no search path is needed and component
templates can't collide with (or leak into) the app's template roots. Under plain Jinja2,
`template` is resolved by whatever loader the environment has, so relative paths plus a
search root work too.

Component templates render with an isolated context: only what `get_context` returns.
pyramid_jinja2's per-render variables (`request`, `context`) are not available inside
component templates — evaluate request-dependent expressions (URLs, permissions) at the
call site and pass the results in as props.

Because that context holds nothing but props, component templates render under
`StrictUndefined`: a name that is not a prop raises `UndefinedError` instead of rendering
empty, so a renamed prop or a typo'd `{% if %}` gate fails instead of taking its false
branch. The host application's own environment keeps Jinja's lenient default.

## Using a component in a template

```jinja
{% component "admin.stat_card", color="bg-gradient-info", value="42 Approved" %}
```
