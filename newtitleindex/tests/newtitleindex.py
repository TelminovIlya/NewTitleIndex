import functools
import unittest

from trac.test import EnvironmentStub, Mock, MockPerm
from trac.web.chrome import web_context
from trac.web.href import Href
from trac.wiki.formatter import format_to_oneliner
from trac.wiki.model import WikiPage
from newtitleindex.macro import NewTitleIndexMacro


class NewTitleIndexTestCase(unittest.TestCase):

    
    def setUp(self):
        self.env = EnvironmentStub(enable=[NewTitleIndexMacro])
        page = WikiPage(self.env)
        page.name = 'NewTitleIndexMacroDefinitions'
        page.save('admin', 'NewTitleIndexMacro definitions')

    def tearDown(self):
        self.env.reset_db()