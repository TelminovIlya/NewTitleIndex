from trac.core import *
from trac.wiki.macros import WikiMacroBase
from trac.wiki.formatter import system_message
from trac.wiki.api import parse_args

from trac.config import Option

from genshi.builder import Element
from fnmatch import fnmatchcase
from itertools import groupby
import fnmatch
import inspect
import io
import os
import re

from trac.core import *
from trac.resource import (
    Resource, ResourceNotFound, get_resource_name, get_resource_summary,
    get_resource_url
)
from trac.util import as_int
from trac.util.datefmt import format_date, from_utimestamp, user_time
from trac.util.html import Markup, escape, find_element, tag
from trac.util.presentation import separated
from trac.util.text import unicode_quote, to_unicode, stripws
from trac.util.translation import _, dgettext, cleandoc_, tag_
from trac.web.chrome import chrome_resource_path
from trac.wiki.api import IWikiMacroProvider, WikiSystem, parse_args
from trac.wiki.formatter import (
    MacroError, OutlineFormatter, ProcessorError, extract_link, format_to_html,
    format_to_oneliner, system_message
)  # ProcessorError unused, but imported for plugin use.
from trac.wiki.interwiki import InterWikiMap


class NewTitleIndexMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Insert an alphabetic list of all wiki pages into the output.

    Accepts a prefix string as parameter: if provided, only pages with names
    that start with the prefix are included in the resulting list. If this
    parameter is omitted, all pages are listed. If the prefix is specified,
    a second argument of value `hideprefix` can be given as well, in order
    to remove that prefix from the output.

    The prefix string supports the standard relative-path notation ''when
    using the macro in a wiki page''. A prefix string starting with `./`
    will be relative to the current page, and parent pages can be
    specified using `../`.

    Several named parameters can be specified:
     - `format=compact`: The pages are displayed as comma-separated links.
     - `format=group`: The list of pages will be structured in groups
       according to common prefix. This format also supports a `min=n`
       argument, where `n` is the minimal number of pages for a group.
     - `format=hierarchy`: The list of pages will be structured according
       to the page name path hierarchy. This format also supports a `min=n`
       argument, where higher `n` flatten the display hierarchy
     - `depth=n`: limit the depth of the pages to list. If set to 0,
       only toplevel pages will be shown, if set to 1, only immediate
       children pages will be shown, etc. If not set, or set to -1,
       all pages in the hierarchy will be shown.
     - `include=page1:page*2`: include only pages that match an item in the
       colon-separated list of pages. If the list is empty, or if no `include`
       argument is given, include all pages.
     - `exclude=page1:page*2`: exclude pages that match an item in the colon-
       separated list of pages.

    The `include` and `exclude` lists accept shell-style patterns.
    """)

    tags = ('newtitleindex')
    SPLIT_RE = re.compile(r"(/| )")
    NUM_SPLIT_RE = re.compile(r"([0-9.]+)")

    def expand_macro(self, formatter, name, content):
        args, kw = parse_args(content)
        prefix = args[0].strip() if args else None
        hideprefix = args and len(args) > 1 and args[1].strip() == 'hideprefix'
        minsize = _arg_as_int(kw.get('min', 1), 'min', min=1)
        minsize_group = max(minsize, 2)
        depth = _arg_as_int(kw.get('depth', -1), 'depth', min=-1)
        format = kw.get('format', '')

        def parse_list(name):
            return [inc.strip() for inc in kw.get(name, '').split(':')
                    if inc.strip()]

        includes = parse_list('include') or ['*']
        excludes = parse_list('exclude')

        wiki = formatter.wiki
        resource = formatter.resource
        if prefix and resource and resource.realm == 'wiki':
            prefix = wiki.resolve_relative_name(prefix, resource.id)

        start = prefix.count('/') if prefix else 0

        if hideprefix:
            omitprefix = lambda page: page[len(prefix):]
        else:
            omitprefix = lambda page: page

        pages = sorted(page for page in wiki.get_pages(prefix)
                       if (depth < 0 or depth >= page.count('/') - start)
                       and 'WIKI_VIEW' in formatter.perm('wiki', page)
                       and any(fnmatchcase(page, inc) for inc in includes)
                       and not any(fnmatchcase(page, exc) for exc in excludes))

        if format == 'compact':
            return tag(
                separated((tag.a(wiki.format_page_name(omitprefix(p)),
                                 href=formatter.href.wiki(p)) for p in pages),
                          ', '))

        # the function definitions for the different format styles

        # the different page split formats, each corresponding to its rendering
        def split_pages_group(pages):
            """Return a list of (path elements, page_name) pairs,
            where path elements correspond to the page name (without prefix)
            splitted at Camel Case word boundaries, numbers and '/'.
            """
            page_paths = []
            for page in pages:
                path = [elt.strip() for elt in self.SPLIT_RE.split(
                        self.NUM_SPLIT_RE.sub(r" \1 ",
                        wiki.format_page_name(omitprefix(page), split=True)))]
                page_paths.append(([elt for elt in path if elt], page))
            return page_paths

        def split_pages_hierarchy(pages):
            """Return a list of (path elements, page_name) pairs,
            where path elements correspond to the page name (without prefix)
            splitted according to the '/' hierarchy.
            """
            return [(wiki.format_page_name(omitprefix(page)).split("/"), page)
                    for page in pages]

        # the different tree structures, each corresponding to its rendering
        def tree_group(entries):
            """Transform a flat list of entries into a tree structure.

            `entries` is a list of `(path_elements, page_name)` pairs

            Return a list organized in a tree structure, in which:
              - a leaf is a page name
              - a node is a `(key, nodes)` pairs, where:
                - `key` is the leftmost of the path elements, common to the
                  grouped (path element, page_name) entries
                - `nodes` is a list of nodes or leaves
            """
            def keyfn(args):
                elts, name = args
                return elts[0] if elts else ''
            groups = []

            for key, grouper in groupby(entries, keyfn):
                # remove key from path_elements in grouped entries for further
                # grouping
                grouped_entries = [(path_elements[1:], page_name)
                                   for path_elements, page_name in grouper]

                if key and len(grouped_entries) >= minsize_group:
                    subnodes = tree_group(sorted(grouped_entries))
                    if len(subnodes) == 1:
                        subkey, subnodes = subnodes[0]
                        node = (key + subkey, subnodes)
                        groups.append(node)
                    elif self.SPLIT_RE.match(key):
                        for elt in subnodes:
                            if isinstance(elt, tuple):
                                subkey, subnodes = elt
                                elt = (key + subkey, subnodes)
                            groups.append(elt)
                    else:
                        node = (key, subnodes)
                        groups.append(node)
                else:
                    for path_elements, page_name in grouped_entries:
                        groups.append(page_name)
            return groups

        def tree_hierarchy(entries):
            """Transform a flat list of entries into a tree structure.

            `entries` is a list of `(path_elements, page_name)` pairs

            Return a list organized in a tree structure, in which:
              - a leaf is a `(rest, page)` pair, where:
                - `rest` is the rest of the path to be shown
                - `page` is a page name
              - a node is a `(key, nodes, page)` pair, where:
                - `key` is the leftmost of the path elements, common to the
                  grouped (path element, page_name) entries
                - `page` is a page name (if one exists for that node)
                - `nodes` is a list of nodes or leaves
            """
            def keyfn(args):
                elts, name = args
                return elts[0] if elts else ''
            groups = []

            for key, grouper in groupby(entries, keyfn):
                grouped_entries = [e for e in grouper]
                sub_entries = [e for e in grouped_entries if len(e[0]) > 1]
                key_entries = [e for e in grouped_entries if len(e[0]) == 1]
                key_entry = key_entries[0] if key_entries else None
                key_page = key_entry[1] if key_entries else None

                if key and len(sub_entries) >= minsize:
                    # remove key from path_elements in grouped entries for
                    # further grouping
                    sub_entries = [(path_elements[1:], page)
                                   for path_elements, page in sub_entries]

                    subnodes = tree_hierarchy(sorted(sub_entries))
                    node = (key, key_page, subnodes)
                    groups.append(node)
                else:
                    if key_entry:
                        groups.append(key_entry)
                    groups.extend(sub_entries)
            return groups

        # the different rendering formats
        def render_group(group):
            return tag.ul(
                tag.li(tag(tag.strong(elt[0].strip('/')), render_group(elt[1]))
                       if isinstance(elt, tuple) else
                       tag.a(wiki.format_page_name(omitprefix(elt)),
                             href=formatter.href.wiki(elt)))
                for elt in group)

        def render_hierarchy(group):
            return tag.ul(
                tag.li(tag(tag.a(elt[0], href=formatter.href.wiki(elt[1]))
                           if elt[1] else tag(elt[0]),
                           render_hierarchy(elt[2]))
                       if len(elt) == 3 else
                       tag.a('/'.join(elt[0]),
                             href=formatter.href.wiki(elt[1])))
                for elt in group)

        transform = {
            'group': lambda p: render_group(tree_group(split_pages_group(p))),
            'hierarchy': lambda p: render_hierarchy(
                                    tree_hierarchy(split_pages_hierarchy(p))),
            }.get(format)

        if transform:
            titleindex = transform(pages)
        else:
            titleindex = tag.ul(
                tag.li(tag.a(wiki.format_page_name(omitprefix(page)),
                             href=formatter.href.wiki(page)))
                for page in pages)

        return tag.div(titleindex, class_='titleindex')