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

This is house style: `register` is a commonly overloaded name, and the `pc` prefix keeps
component code unambiguous and greppable.

## Defining a component

```python
from dataclasses import field

import pyramid_components as pc


@pc.register("admin.stat_card")
class StatCard(pc.Component):
    template = "myapp.admin:components/stat_card/stat_card.html"

    class Props:
        color: str
        value: str
        icon: str = "fa-box"
        sublines: list[str] = field(default_factory=list)
        description: str | None = None
        footer_url: str | None = None
        footer_text: str = "View All"
        tooltip: str | None = None
```

`Props` becomes a dataclass automatically. Override `get_context` (a classmethod) only
when a component needs to derive or reshape data; the default exposes each prop to the
template.

Namespace registration names by owner (`admin.stat_card`, not `stat_card`): all
components in a process share one registry, and a prefix keeps a second consumer from
colliding.

## Wiring into Pyramid

```python
config.include("pyramid_components")  # registers the {% component %} tag
```

The tag is registered on the renderer named by the `pyramid_components.renderer_name`
setting (default `.html`), via pyramid_jinja2's `add_jinja2_extension` directive.

Under Pyramid, prefer asset-spec template paths (`myapp.admin:components/...`) as shown
above — pyramid_jinja2 resolves them directly, so no search path is needed and component
templates can't collide with (or leak into) the app's template roots. Under plain Jinja2,
`template` is resolved by whatever loader the environment has, so relative paths plus a
search root work too.

Component templates render with an isolated context: only what `get_context` returns.
pyramid_jinja2's per-render variables (`request`, `context`) are not available inside
component templates — evaluate request-dependent expressions (URLs, permissions) at the
call site and pass the results in as props.

## Using a component in a template

```jinja
{% component "admin.stat_card", color="bg-gradient-info", value="42 Approved" %}
```
