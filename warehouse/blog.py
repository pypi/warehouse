# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import glob
import os.path
import pathlib

import html5lib
import jinja2
import mistune

import warehouse

DEFAULT_BLOG_DIRECTORY = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(warehouse.__file__)), "blog")
)
DEFAULT_BLOG_TITLE = "The PyPI Blog"


class BlogPost:
    def __init__(self, filepath):
        with open(filepath, "r", encoding="utf8") as fp:
            unrendered = fp.read()

        rendered = mistune.markdown(unrendered)
        html = html5lib.parse(rendered, namespaceHTMLElements=False, treebuilder="lxml")

        self.slug = pathlib.Path(filepath).stem
        self.title = html.find("//h1[1]").text
        self.date = html.find("//em[1]").text
        self.summary = html.find("//p[2]").text
        self.html = jinja2.Markup(rendered)


class BlogPostFactory:
    def __init__(self, request):
        self.request = request

    def __getitem__(self, slug):
        directory = self.request.registry.settings.get(
            "blog.directory", DEFAULT_BLOG_DIRECTORY
        )
        filepath = os.path.join(directory, slug + ".md")
        try:
            return BlogPost(filepath)
        except FileNotFoundError:
            raise KeyError from None


def blog_post_view(blog_post, request):
    return {"post": blog_post}


def blog_index_view(request):
    directory = request.registry.settings.get("blog.directory", DEFAULT_BLOG_DIRECTORY)
    title = request.registry.settings.get("blog.title", DEFAULT_BLOG_TITLE)
    posts = [
        BlogPost(filepath)
        for filepath in sorted(glob.glob(directory + "/*.md"), reverse=True)
    ]

    return {"title": title, "posts": posts}


def includeme(config):
    if config.get_settings().get("warehouse.domain") != "test.pypi.org":
        config.add_route("blog.index", "/blog/")
        config.add_view(
            blog_index_view,
            route_name="blog.index",
            renderer="blog/index.html",
            has_translations=True,
        )
        config.add_route(
            "blog.post",
            "/blog/{slug}",
            factory=BlogPostFactory,
            traverse="/{slug}",
        )
        config.add_view(
            blog_post_view,
            route_name="blog.post",
            renderer="blog/post.html",
            has_translations=True,
        )
