from gitlab import Gitlab
from anytree import Node, RenderTree
from anytree.exporter import DictExporter, JsonExporter
from anytree.importer import DictImporter
from .git import sync_tree
from .format import PrintFormat
from .method import CloneMethod
import yaml
import io
import globre
import logging
import os
log = logging.getLogger(__name__)


class GitlabTree:

    def __init__(self, url, token, method, includes=[], excludes=[], in_file=None):
        self.includes = includes
        self.excludes = excludes
        self.url = url
        self.root = Node("", root_path="", url=url)
        self.gitlab = Gitlab(url, private_token=token)
        self.method = method
        self.in_file = in_file
        self.repo = []

    def is_included(self, node):
        '''
        returns True if the node should be included
        '''
        if self.includes is not None:
            for include in self.includes:
                if globre.match(include, node.root_path):
                    log.debug(
                        "Matched include path [%s] to node [%s]", include, node.root_path)
                    return True
        else:
            return True

    def is_excluded(self, node):
        '''
        returns True if the node should be excluded
        '''
        if self.excludes is not None:
            for exclude in self.excludes:
                if globre.match(exclude, node.root_path):
                    log.debug(
                        "Matched exclude path [%s] to node [%s]", exclude, node.root_path)
                    return True
        return False

    def filter_tree(self, parent):
        for child in parent.children:
            if not self.is_included(child):
                child.parent = None
            if self.is_excluded(child):
                child.parent = None
            self.filter_tree(child)

    def root_path(self, node):
        return "/".join([str(n.name) for n in node.path])

    def make_node(self, name, parent, url):
        node = Node(name=name, parent=parent, url=url)
        node.root_path = self.root_path(node)
        return node


    def convert_to_node(self):

        for r in self.repo:
            paths = r.path_with_namespace.split('/')
            n = None
            for i, path in enumerate(paths):
                if i == 0:
                    create = True
                    if len(self.root.children) > 0:
                        for node in self.root.children:
                            if node.name == path :
                                create = False
                                n = node
                    if create:
                        n = self.make_node(path, self.root, 'http://')

                if i !=0 and i < len(paths) - 1:
                    create = True
                    if len(n.children) > 0:
                        for node in n.children:
                            if node.name == path:
                                create = False
                                tmp_node = node

                    if create:
                        tmp_node = self.make_node(path, n, '')
                    n = tmp_node

                else:
                    create = True
                    if len(n.children) > 0:
                        for node in n.children:
                            if node.name == path:
                                create = False
                                tmp_node = node

                    if create:
                        tmp_node = self.make_node(path, n, r.http_url_to_repo)


    def get_projects(self, project):
        self.repo.append(project)


    def load_gitlab_tree(self, project_filter=None):
        projects = self.gitlab.projects.list(as_list=False)
        for project in projects:
            add = False
            if project_filter is not None:
                if project_filter == project.path_with_namespace.split('/')[0]:
                    add = True
            else:
                add = True
            if add:
                log.info(project.web_url)
                self.get_projects(project)

    def load_file_tree(self):
        with open(self.in_file, 'r') as stream:
            dct = yaml.safe_load(stream)
            self.root = DictImporter().import_(dct)

    def load_tree(self, project_filter=None):
        if self.in_file:
            log.debug("Loading tree from file [%s]", self.in_file)
            self.load_file_tree()
        else:
            log.info("Loading tree gitlab server [%s]", self.url)
            self.load_gitlab_tree(project_filter)

        log.debug("Fetched root node with [%d] projects" % len(
            self.root.leaves))
        self.filter_tree(self.root)

    def print_tree(self, format=PrintFormat.TREE):
        if format is PrintFormat.TREE:
            self.print_tree_native()
        elif format is PrintFormat.YAML:
            self.print_tree_yaml()
        elif format is PrintFormat.JSON:
            self.print_tree_json()
        else:
            log.error("Invalid print format [%s]", format)

    def print_tree_native(self):
        for pre, _, node in RenderTree(self.root):
            if node.is_root:
                print("%s%s [%s]" % (pre, "root", self.url))
            else:
                print("%s%s [%s]" % (pre, node.name, node.root_path))

    def print_tree_yaml(self):
        dct = DictExporter().export(self.root)
        print(yaml.dump(dct, default_flow_style=False))

    def print_tree_json(self):
        exporter = JsonExporter(indent=2, sort_keys=True)
        print(exporter.export(self.root))

    def sync_tree(self, dest):
        log.debug("Going to clone/pull [%s] groups and [%s] projects" %
                  (len(self.root.descendants) - len(self.root.leaves), len(self.root.leaves)))
        sync_tree(self.root, dest)

    def is_empty(self):
        return self.root.height < 1
