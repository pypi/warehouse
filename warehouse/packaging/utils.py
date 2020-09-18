import hashlib
import os.path

from jinja2 import Environment, FileSystemLoader

import warehouse

from warehouse.legacy.api.simple import _simple_detail


def render_simple_detail(project, request, store=False):
    context = _simple_detail(project, request)

    #  TODO: use pyramid_jinja2 "get_jinja2_environment" method instead:
    #  https://docs.pylonsproject.org/projects/pyramid_jinja2/en/latest/api.html#pyramid_jinja2.get_jinja2_environment
    dir_name = os.path.join(os.path.dirname(warehouse.__file__), "templates")
    env = Environment(
        loader=FileSystemLoader(dir_name),
        extensions=[],
        cache_size=0,
    )

    template = env.get_template("legacy/api/simple/detail.html")
    content = template.render(**context, request=request)

    content_hasher = hashlib.blake2b(digest_size=256 // 8)
    content_hasher.update(content.encode("utf-8"))
    content_hash = content_hasher.hexdigest().lower()
    simple_detail_path = f"/simple/{project.normalized_name}/{content_hash}/"

    if store:
        #  TODO: Store generated file in FileStorage
        #        We should probably configure a new FileStorage for a new simple-files bucket in GCS
        pass

    return (content_hash, simple_detail_path)
